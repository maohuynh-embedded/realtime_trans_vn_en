"""Ghep pipeline bang thread + queue (muc 4 cua HUONG_DAN_XAY_DUNG.md):

  [Audio callback] -> raw_queue -> [VAD thread] -> utterance_queue
      -> [Worker thread: STT -> MT -> TTS -> play] -> result_queue (GUI/console doc)

Moi buoc toc do khac nhau nen tach thread, khong xu ly tuan tu trong 1 vong lap -
neu khong audio capture se bi nghen trong luc Whisper dang chay.

Moi CHIEU dich la mot DirectionPipeline rieng; hai chieu chay song song va dung
chung ModelHub (1 model Whisper cho ca hai).
"""
import queue
import threading
import time
from dataclasses import dataclass

from app.audio_devices import InputDevice, LoopbackDevice, OutputDevice
from app.capture import LoopbackCapture, MicCapture
from app.config import AudioConfig, DirectionConfig
from app.models import ModelHub
from app.playback import Player
from app.resample import prepare_for_vad
from app.speaker import SpeakerTracker
from app.vad_segmenter import VadSegmenter


@dataclass
class TranslationResult:
    direction_key: str
    source_text: str
    translated_text: str
    duration_s: float
    speaker_label: str = ""   # vd. "Nguoi 1 (nam)" - de biet ai dang noi
    lag_s: float = 0.0        # tu luc dut cau den luc bat dau nghe ban dich
    t_stt: float = 0.0
    t_mt: float = 0.0
    t_tts: float = 0.0
    dropped: int = 0          # so cau bi bo qua do xu ly khong kip


class DirectionPipeline:
    """Mot chieu dich hoan chinh: capture -> VAD -> STT -> MT -> TTS -> phat."""

    def __init__(
        self,
        direction: DirectionConfig,
        audio_cfg: AudioConfig,
        hub: ModelHub,
        source_device: "LoopbackDevice | InputDevice",
        output_device: OutputDevice,
        result_queue: "queue.Queue[TranslationResult] | None" = None,
        status_queue: "queue.Queue[str] | None" = None,
    ):
        self.direction = direction
        self.audio_cfg = audio_cfg
        self.hub = hub
        self.source_device = source_device
        self.output_device = output_device

        self.result_queue = result_queue if result_queue is not None else queue.Queue()
        self.status_queue = status_queue if status_queue is not None else queue.Queue()

        self._raw_queue: queue.Queue = queue.Queue()
        self._utterance_queue: queue.Queue = queue.Queue()

        self._capture = None
        self._stop_event = threading.Event()
        self._paused = threading.Event()   # tam dung dich ma khong tat han stream
        self._player: Player | None = None

        # Co doc ban dich thanh tieng khong (tat = chi hien text tren GUI)
        self.speak = threading.Event()
        if direction.speak:
            self.speak.set()

        # Dang phat ban dich -> tam ngung thu, de KHONG bat lai chinh giong minh
        # vua doc ra. Nho co nay ma may chi co 1 loa duy nhat van dung duoc:
        # loa vua phat tieng Viet vua la nguon bi loopback bat, nhung trong luc
        # phat thi ta khong thu, nen khong bi dich chong dich.
        self._playing = threading.Event()

        # Chong do tre don: neu tut lai qua max_lag_s thi bo cac cau cu.
        self.drop_when_behind: bool = True
        self.max_lag_s: float = 6.0

        # Dem so cau bi bo loc ao giac loai bo, de hien len GUI
        self.rejected_count = 0
        self.last_reject_reason = ""

        # Nhan dien nguoi noi + gioi tinh (chi co y nghia voi nguon loopback,
        # vi nguon mic thi luon la chinh ban).
        self.identify_speakers: bool = direction.source == "loopback"
        self._speaker_tracker = SpeakerTracker()

    def _set_status(self, msg: str) -> None:
        self.status_queue.put(f"[{self.direction.key}] {msg}")

    # ---- Dieu khien ----

    def load_models(self) -> None:
        self.hub.ensure_stt()
        self.hub.ensure_direction(self.direction)
        self.hub.warm_up(self.direction)
        self._player = Player(self.output_device, status_cb=self._set_status)

    def start(self) -> None:
        if self._player is None:
            self.load_models()

        self._stop_event.clear()
        if self.direction.source == "loopback":
            self._capture = LoopbackCapture(device=self.source_device, out_queue=self._raw_queue)
        else:
            self._capture = MicCapture(device=self.source_device, out_queue=self._raw_queue)
        self._capture.start()

        threading.Thread(target=self._vad_loop, daemon=True).start()
        threading.Thread(target=self._worker_loop, daemon=True).start()
        self._set_status("Dang nghe...")

    def stop(self) -> None:
        self._stop_event.set()
        if self._capture is not None:
            self._capture.stop()
            self._capture = None
        self._set_status("Da dung.")

    def pause(self) -> None:
        """Tam ngung dich (vd. ban dang noi chuyen rieng, khong muon doi tac nghe)."""
        self._paused.set()
        self._set_status("Tam dung.")

    def resume(self) -> None:
        self._paused.clear()
        self._set_status("Dang nghe...")

    def is_paused(self) -> bool:
        return self._paused.is_set()

    def is_running(self) -> bool:
        return self._capture is not None and not self._stop_event.is_set()

    # ---- Threads ----

    def _vad_loop(self) -> None:
        segmenter = VadSegmenter(self.audio_cfg)
        frame_bytes = segmenter.frame_bytes
        pending = b""
        src_rate = self._capture.sample_rate

        while not self._stop_event.is_set():
            try:
                raw_chunk = self._raw_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if self._paused.is_set() or self._playing.is_set():
                # Van doc queue de khong don u, nhung bo qua khong xu ly.
                # _playing: dang phat ban dich -> bo qua de khong thu lai chinh no.
                continue

            pending += prepare_for_vad(raw_chunk, src_rate, self.audio_cfg.target_sample_rate)

            while len(pending) >= frame_bytes:
                frame, pending = pending[:frame_bytes], pending[frame_bytes:]
                utt = segmenter.feed(frame)
                if utt is not None:
                    self._utterance_queue.put(utt)

        final_utt = segmenter.flush()
        if final_utt is not None:
            self._utterance_queue.put(final_utt)

    def _worker_loop(self) -> None:
        stt = self.hub.ensure_stt()
        translator, tts = self.hub.ensure_direction(self.direction)

        while not self._stop_event.is_set():
            try:
                utt = self._utterance_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if utt.duration_s < 0.2 or self._paused.is_set():
                continue  # bo qua cau qua ngan (nhieu / tieng dong)

            utt, dropped = self._skip_backlog(utt)

            try:
                self._process(utt, stt, translator, tts, dropped)
            except Exception as exc:
                # Mot cau loi khong duoc lam chet ca pipeline - bao roi di tiep
                self._set_status(f"Loi khi xu ly cau: {exc}")

    def _skip_backlog(self, utt):
        """Neu queue dang don u, bo cac cau CU va chi giu cau MOI NHAT.

        Khi may xu ly cham hon toc do noi, cac cau xep hang trong queue va do tre
        tang dan vo han - nghe ban dich cua chuyen da xay ra 30 giay truoc thi vo
        nghia. Tha bo vai cau con hon tre don. Chi lam khi thuc su tut lai
        (max_lag_s), va tat han duoc bang drop_when_behind.
        """
        dropped = 0
        if not self.drop_when_behind:
            return utt, 0

        while (time.monotonic() - utt.captured_at) > self.max_lag_s:
            try:
                newer = self._utterance_queue.get_nowait()
            except queue.Empty:
                break
            dropped += 1
            utt = newer

        if dropped:
            self._set_status(f"Tut lai -> bo qua {dropped} cau cu de duoi kip")
        return utt, dropped

    def _process(self, utt, stt, translator, tts, dropped: int = 0) -> None:
        """Xu ly 1 cau: STT -> MT -> TTS -> phat."""
        # Nhan dien nguoi noi TRUOC khi dich (chay tren audio goc, rat nhanh)
        speaker_label = ""
        if self.identify_speakers:
            try:
                info = self._speaker_tracker.identify(
                    utt.pcm16_bytes, self.audio_cfg.target_sample_rate
                )
                speaker_label = info.label
            except Exception:
                pass   # khong nhan dien duoc thi van dich binh thuong

        self._set_status("Dang nhan dang (STT)...")
        t0 = time.monotonic()

        # Bo loc ao giac co the loai bo cau. Phai BAO RO ly do, neu khong nguoi
        # dung chi thay app im lang ma khong biet tai sao (da gap dung loi nay).
        reasons: list[str] = []
        source_text = stt.transcribe_pcm16(
            utt.pcm16_bytes,
            self.direction.stt_language,
            self.audio_cfg.target_sample_rate,
            reject_cb=reasons.append,
        )
        t_stt = time.monotonic() - t0

        if not source_text.strip():
            self.rejected_count += 1
            reason = reasons[0] if reasons else "khong nghe ra gi"
            self.last_reject_reason = reason
            self._set_status(f"Bo qua ({self.rejected_count}): {reason}")
            return

        self._set_status("Dang dich...")
        t0 = time.monotonic()
        translated = translator.translate(source_text)
        t_mt = time.monotonic() - t0

        t_tts = 0.0
        if self.speak.is_set():
            self._set_status("Dang doc ban dich...")
            t0 = time.monotonic()
            pcm, sr = tts.synthesize(translated)
            t_tts = time.monotonic() - t0
            if not self._paused.is_set():
                self._playing.set()
                try:
                    self._player.play_blocking(pcm, sr)
                finally:
                    # Cho them mot chut cho audio thoat het khoi buffer cua thiet bi
                    # truoc khi thu lai, tranh bat duoc phan duoi cua chinh ban dich.
                    time.sleep(0.25)
                    self._playing.clear()

        self.result_queue.put(
            TranslationResult(
                direction_key=self.direction.key,
                source_text=source_text,
                translated_text=translated,
                duration_s=utt.duration_s,
                speaker_label=speaker_label,
                lag_s=time.monotonic() - utt.captured_at,
                t_stt=t_stt,
                t_mt=t_mt,
                t_tts=t_tts,
                dropped=dropped,
            )
        )
        self._set_status("Dang nghe...")
