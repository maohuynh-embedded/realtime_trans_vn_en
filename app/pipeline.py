"""Ghep pipeline bang thread + queue (muc 4 cua HUONG_DAN_XAY_DUNG.md):

  [Audio callback] -> raw_queue -> [VAD thread] -> utterance_queue
      -> [STT thread: nhan dien nguoi noi + Whisper] -> recognized_queue
      -> [MT+TTS thread: dich + doc + phat] -> result_queue (GUI/console doc)

BA giai doan tach rieng (khong phai hai) - day la diem quan trong: neu STT va
MT+TTS dung CHUNG 1 thread thi trong luc dang dich/doc cau N, Whisper CHUA HE
bat dau nghe cau N+1 - do tre MT+TTS cong don thang vao do tre cam nhan, khong
duoc "giau" di. Tach STT ra rieng thi trong luc thread MT+TTS dang ban voi cau
N, thread STT co the da nghe xong cau N+1 va co san trong recognized_queue -
do tre MT+TTS phan lon duoc giau sau do tre STT cua cau tiep theo.

Moi CHIEU dich la mot DirectionPipeline rieng; hai chieu chay song song va dung
chung ModelHub (1 model Whisper cho ca hai).
"""
import queue
import threading
import time
from dataclasses import dataclass

import numpy as np

from app.audio_devices import InputDevice, LoopbackDevice, OutputDevice
from app.capture import LoopbackCapture, MicCapture
from app.config import AudioConfig, DirectionConfig
from app.models import ModelHub
from app.playback import Player
from app.resample import prepare_for_vad, resample_audio
from app.speaker import SpeakerTracker
from app.vad_segmenter import VadSegmenter
from app.voice_bank import VoiceBank


@dataclass
class _Recognized:
    """Ket qua giai doan STT - dau vao cua giai doan MT+TTS.

    Giu lai captured_at cua utterance goc de tinh dung do tre tu luc dut cau,
    khong phai tu luc STT xong.
    """
    source_text: str
    detected_lang: str
    speaker_label: str
    duration_s: float
    captured_at: float
    t_stt: float
    dropped: int = 0   # so utterance bi bo qua TRUOC KHI toi duoc STT
    speaker_key: str = ""   # khoa nguoi noi cho kho mau giong ("" neu khong biet)


_SENTENCE_END = (".", "!", "?", "...", "。", "！", "？", "…")

# Bao lau toi da cho mot cau CHUA ket thuc bang dau cau truoc khi dich cuong
# buc phan da co. Bao ve khoi treo vo han neu Whisper khong bao gio xuat dau
# cau (vd. noi lien tuc khong nghi).
_MAX_BUFFER_WAIT_S = 4.0
_MAX_BUFFER_PARTS = 4


@dataclass
class _PendingBuffer:
    """Gom nhieu _Recognized LIEN TIEP thanh 1 cau hoan chinh truoc khi dich.

    Ly do can cai nay (phat hien tu log that): VAD hay cat giua mau, sinh ra
    cac doan nhu "...which was why I chose to follow this" + "career path."
    rieng le. Dich TUNG DOAN mot khien NLLB phai doan mo phan con thieu ("theo
    doi" thay vi "theo duoi"), hoac lam mat han noi dung ("What are your
    weaknesses?" bi rot mat khi dich rieng). Gop van ban GOC lai truoc khi dich
    thi NLLB co du ngu canh de dich dung, dung "chap va" ban dich sau khi da
    dich rieng (khong lam duoc vi khong can duoc tu voi tu giua 2 ban dich).
    """
    text: str
    detected_lang: str
    speaker_label: str
    duration_s: float
    captured_at: float     # cua MANH DAU TIEN - de tinh dung do tre tu luc dut cau
    t_stt: float            # cong don ca cac manh
    dropped: int            # cong don ca cac manh
    started_at: float       # gio (monotonic) mo buffer - cho kiem tra timeout
    n_parts: int = 1
    speaker_key: str = ""

    def append(self, rec: "_Recognized", extra_dropped: int = 0) -> None:
        self.text = f"{self.text} {rec.source_text}".strip()
        self.duration_s += rec.duration_s
        self.t_stt += rec.t_stt
        self.dropped += rec.dropped + extra_dropped
        self.n_parts += 1

    @property
    def is_complete(self) -> bool:
        """Da ket thuc bang dau cau, hoac da cho/gom qua nguong an toan."""
        if self.text.rstrip().endswith(_SENTENCE_END):
            return True
        if self.n_parts >= _MAX_BUFFER_PARTS:
            return True
        return (time.monotonic() - self.started_at) > _MAX_BUFFER_WAIT_S


@dataclass
class TranslationResult:
    direction_key: str
    source_text: str
    translated_text: str
    duration_s: float
    speaker_label: str = ""   # vd. "Nguoi 1 (nam)" - de biet ai dang noi
    detected_lang: str = ""   # ngon ngu doan duoc (che do tu nhan dien)
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
        self._recognized_queue: "queue.Queue[_Recognized]" = queue.Queue()

        self._capture = None
        self._stop_event = threading.Event()
        self._paused = threading.Event()   # tam dung dich ma khong tat han stream
        self._player: Player | None = None

        # Co doc ban dich thanh tieng khong (tat = chi hien text tren GUI)
        self.speak = threading.Event()
        if direction.speak:
            self.speak.set()

        # CHE DO: "giao tiep binh thuong" (mac dinh, TAT) hay "chuyen nganh
        # embedded/SW/HW" (BAT). Dieu khien ca STT (initial_prompt, dat rieng
        # tren cfg.stt) LAN MT (glossary bao ve thuat ngu).
        #
        # Vi sao KHONG duoc de glossary luon bat: no bao ve nhung tu nhu "bus",
        # "plane", "thread", "driver", "host", "frame" vi mang nghia KY THUAT
        # khac han nghia thong thuong - nhung trong hoi thoai BINH THUONG,
        # chinh cac tu do lai mang dung nghia thong thuong ("I missed the bus"
        # = "toi lo xe buyt", KHONG phai duong truyen du lieu). Luon bat
        # glossary se dich SAI theo huong nguoc lai cho hoi thoai thuong -
        # giu nguyen "bus" tieng Anh thay vi "xe buyt". App khong tu doan duoc
        # dang hoi thoai nao, nen bat buoc nguoi dung tu chon qua GUI/--tech.
        self.tech_mode = threading.Event()

        # Dang phat ban dich -> tam ngung thu, de KHONG bat lai chinh giong minh
        # vua doc ra. Nho co nay ma may chi co 1 loa duy nhat van dung duoc:
        # loa vua phat tieng Viet vua la nguon bi loopback bat, nhung trong luc
        # phat thi ta khong thu, nen khong bi dich chong dich.
        self._playing = threading.Event()

        # Tat tieng goc cua nguon loopback (chi nghe ban dich). Doc luc start();
        # chi co tac dung tren nen tang ho tro (macOS).
        self.mute_original: bool = False

        # Doc ban dich bang GIONG CUA NGUOI NOI (sao chep giong; chi khi dich sang tieng Anh).
        # Tut lai qua clone_max_lag_s thi lui ve giong Piper de duoi kip.
        self.clone_voice: bool = False
        self.clone_max_lag_s: float = 5.0
        self.voice_bank = VoiceBank()
        self._clone = None

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
        self.hub.ensure_translator_for(self.direction)
        # TTS (Piper) chi nap khi THAT SU can doc thanh tieng - checkbox "Doc
        # thanh tieng" tat (vd. --watch mac dinh, hoac nguoi dung tu tat) thi
        # khong dung toi Piper mot chut nao, tranh ton RAM/VRAM va thoi gian
        # khoi dong vo ich. Neu can, no se duoc nap tre hoan trong _process().
        if self.direction.speak:
            self.hub.ensure_tts(self.direction)
        self.hub.warm_up(self.direction)
        self._load_clone_tts()
        self._player = Player(self.output_device, status_cb=self._set_status)

    def start(self) -> None:
        if self._player is None:
            self.load_models()

        self._stop_event.clear()
        self.voice_bank.reset()
        if self.direction.source == "loopback":
            self._capture = LoopbackCapture(device=self.source_device, out_queue=self._raw_queue,
                                            status_cb=self._set_status,
                                            mute_original=self.mute_original)
        else:
            self._capture = MicCapture(device=self.source_device, out_queue=self._raw_queue)
        self._capture.start()

        threading.Thread(target=self._vad_loop, daemon=True).start()
        threading.Thread(target=self._stt_loop, daemon=True).start()
        threading.Thread(target=self._translate_loop, daemon=True).start()
        self._set_status("Dang nghe...")

    def stop(self) -> None:
        self._stop_event.set()
        if self._capture is not None:
            self._capture.stop()
            self._capture = None
        # Cat ngang tieng dang doc, neu khong luong phat se giu tien trinh song
        if self._player is not None:
            self._player.abort()
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

    def _skip_backlog(self, item, src_queue: queue.Queue, kind: str):
        """Neu queue dang don u, bo cac muc CU va chi giu muc MOI NHAT.

        Dung chung cho ca 2 diem vao (truoc STT va truoc MT+TTS): khi may xu ly
        cham hon toc do noi, cac muc xep hang va do tre tang dan vo han - nghe
        ban dich cua chuyen da xay ra 30 giay truoc thi vo nghia. Tha bo vai muc
        con hon tre don. Chi lam khi thuc su tut lai (max_lag_s), tat han bang
        drop_when_behind. `item` phai co thuoc tinh `captured_at`.
        """
        dropped = 0
        if not self.drop_when_behind:
            return item, 0

        while (time.monotonic() - item.captured_at) > self.max_lag_s:
            try:
                newer = src_queue.get_nowait()
            except queue.Empty:
                break
            dropped += 1
            item = newer

        if dropped:
            self._set_status(f"Tut lai ({kind}) -> bo qua {dropped} cau cu de duoi kip")
        return item, dropped

    # ---- Giai doan 2: STT (+ nhan dien nguoi noi) ----

    def _stt_loop(self) -> None:
        """Rieng mot thread: chi lam STT, khong dung cham gi den MT/TTS.

        Tach khoi giai doan dich/doc de trong luc giai doan sau dang ban voi
        cau N, thread nay van nghe tiep duoc cau N+1 - giau bot do tre MT+TTS
        thay vi cong don tuan tu.
        """
        stt = self.hub.ensure_stt()

        while not self._stop_event.is_set():
            try:
                utt = self._utterance_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if utt.duration_s < 0.2 or self._paused.is_set():
                continue  # bo qua cau qua ngan (nhieu / tieng dong)

            utt, dropped = self._skip_backlog(utt, self._utterance_queue, "truoc STT")

            try:
                self._run_stt(utt, stt, dropped)
            except Exception as exc:
                self._set_status(f"Loi khi nhan dang: {exc}")

    def _run_stt(self, utt, stt, dropped: int) -> None:
        # Nhan dien nguoi noi TRUOC khi STT (chay tren audio goc, rat nhanh)
        speaker_label = ""
        # Nguon mic luon la chinh ban; nguon loopback thi lay theo nhan dien nguoi noi
        speaker_key = "" if self.identify_speakers else "me"
        if self.identify_speakers:
            try:
                info = self._speaker_tracker.identify(
                    utt.pcm16_bytes, self.audio_cfg.target_sample_rate
                )
                speaker_label = info.label
                speaker_key = f"spk{info.speaker_id}"
            except Exception:
                pass   # khong nhan dien duoc thi van tiep tuc binh thuong

        self._set_status("Dang nhan dang (STT)...")
        t0 = time.monotonic()

        # Bo loc ao giac co the loai bo cau. Phai BAO RO ly do, neu khong nguoi
        # dung chi thay app im lang ma khong biet tai sao (da gap dung loi nay).
        reasons: list[str] = []
        detected_lang = self.direction.stt_language

        if self.direction.stt_language == "auto":
            source_text, detected_lang = stt.transcribe_auto(
                utt.pcm16_bytes,
                candidates=("en", "vi"),
                sample_rate=self.audio_cfg.target_sample_rate,
                reject_cb=reasons.append,
            )
        else:
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

        # Cau da co loi noi that (qua bo loc ao giac) -> them vao kho mau giong cua nguoi do
        if self.clone_voice and speaker_key:
            self.voice_bank.add(speaker_key, utt.pcm16_bytes)

        self._recognized_queue.put(
            _Recognized(
                source_text=source_text,
                detected_lang=detected_lang,
                speaker_label=speaker_label,
                duration_s=utt.duration_s,
                captured_at=utt.captured_at,
                t_stt=t_stt,
                dropped=dropped,
                speaker_key=speaker_key,
            )
        )

    # ---- Giai doan 3: MT + TTS + phat ----

    def _translate_loop(self) -> None:
        translator = self.hub.ensure_translator_for(self.direction)
        pending: "_PendingBuffer | None" = None

        while not self._stop_event.is_set():
            try:
                rec = self._recognized_queue.get(timeout=0.3)
            except queue.Empty:
                # Khong co gi moi, nhung buffer dang cho co the da qua han -
                # phai tu kiem tra timeout o day, khong the cho mai cau tiep theo.
                if pending is not None and pending.is_complete:
                    self._flush_pending(pending, translator)
                    pending = None
                continue

            if self._paused.is_set():
                continue

            rec, extra_dropped = self._skip_backlog(rec, self._recognized_queue, "truoc dich")
            total_dropped = rec.dropped + extra_dropped

            # Neu doi ngon ngu nguon giua chung (che do tu nhan dien) thi khong
            # gop chung voi buffer dang do - xuat het phan cu roi bat dau moi.
            # Doi ngon ngu nguon HOAC (khi sao chep giong) doi nguoi noi thi khong gop chung:
            # moi cau phai doc bang dung giong cua nguoi noi no.
            if pending is not None and (
                pending.detected_lang != rec.detected_lang
                or (self.clone_voice and pending.speaker_key != rec.speaker_key)
            ):
                self._flush_pending(pending, translator)
                pending = None

            if pending is None:
                pending = _PendingBuffer(
                    text=rec.source_text,
                    detected_lang=rec.detected_lang,
                    speaker_label=rec.speaker_label,
                    duration_s=rec.duration_s,
                    captured_at=rec.captured_at,
                    t_stt=rec.t_stt,
                    dropped=total_dropped,
                    started_at=time.monotonic(),
                    speaker_key=rec.speaker_key,
                )
            else:
                pending.append(rec, extra_dropped)

            if pending.is_complete:
                try:
                    self._flush_pending(pending, translator)
                except Exception as exc:
                    # Mot cau loi khong duoc lam chet ca pipeline - bao roi di tiep
                    self._set_status(f"Loi khi dich: {exc}")
                pending = None

        # Dung app trong luc dang co buffer do dang - xuat not, dung de mat.
        if pending is not None:
            try:
                self._flush_pending(pending, translator)
            except Exception:
                pass

    def _flush_pending(self, pending: "_PendingBuffer", translator) -> None:
        rec = _Recognized(
            source_text=pending.text,
            detected_lang=pending.detected_lang,
            speaker_label=pending.speaker_label,
            duration_s=pending.duration_s,
            captured_at=pending.captured_at,
            t_stt=pending.t_stt,
            dropped=pending.dropped,
            speaker_key=pending.speaker_key,
        )
        self._translate_and_speak(rec, translator, pending.dropped)

    def _load_clone_tts(self) -> None:
        """Nap TTS sao chep giong neu duoc bat (chi khi dich sang tieng Anh)."""
        if not (self.clone_voice and self.direction.tgt_language == "en"):
            self._clone = None
            return
        try:
            self._clone = self.hub.ensure_clone_tts()
            # Lam nong bang mot cau Piper: giong nguoi that hon tieng on / im lang
            pcm, sr = self.hub.ensure_tts(self.direction).synthesize(
                "This is a short sentence to warm up the voice model."
            )
            self._clone.warmup(resample_audio(pcm.astype(np.float32) / 32768.0, sr, 16000))
        except Exception as exc:   # thieu mlx-audio, khong du bo nho, ...
            self._clone = None
            self._set_status(
                f"Khong bat duoc sao chep giong ({type(exc).__name__}: {str(exc)[:60]}) "
                "- dung giong mac dinh."
            )

    def _synthesize(self, text: str, rec: _Recognized):
        """Doc `text`: bang giong nguoi noi neu co the, khong thi bang giong Piper mac dinh."""
        if self._clone is not None and self.clone_voice and rec.speaker_key:
            sample = self.voice_bank.get(rec.speaker_key)
            lag = time.monotonic() - rec.captured_at
            if sample is None:
                self._set_status("Chua du mau giong nguoi noi -> dung giong mac dinh.")
            elif lag > self.clone_max_lag_s:
                self._set_status(f"Tre {lag:.1f}s -> dung giong mac dinh de duoi kip.")
            else:
                try:
                    return self._clone.synthesize(text, sample.audio, rec.speaker_key, sample.version)
                except Exception as exc:
                    self._set_status(f"Sao chep giong loi ({type(exc).__name__}) -> dung giong mac dinh.")
        return self.hub.ensure_tts(self.direction).synthesize(text)

    def _translate_and_speak(self, rec: _Recognized, translator, dropped: int) -> None:
        t0 = time.monotonic()
        if rec.detected_lang == self.direction.tgt_language:
            # Cau nay da dung ngon ngu dich roi -> khong dich lai, chi hien nguyen van.
            # Tiet kiem thoi gian va tranh dich vong vo nghia (Viet -> Viet).
            translated = ""
            self._set_status(f"Nghe tieng {rec.detected_lang} (khong can dich)")
        elif self.direction.stt_language == "auto":
            self._set_status(f"Dang dich {rec.detected_lang} -> {self.direction.tgt_language}...")
            translated = self.hub.ensure_translator(
                rec.detected_lang, self.direction.tgt_language
            ).translate(rec.source_text, use_glossary=self.tech_mode.is_set())
        else:
            self._set_status("Dang dich...")
            translated = translator.translate(rec.source_text, use_glossary=self.tech_mode.is_set())
        t_mt = time.monotonic() - t0

        t_tts = 0.0
        if self.speak.is_set() and translated:
            # Nap Piper tai day neu chua co - lan doc dau tien se cham hon mot
            # chut (vai giay) nhung chi xay ra dung mot lan.
            self._set_status("Dang doc ban dich...")
            t0 = time.monotonic()
            pcm, sr = self._synthesize(translated, rec)
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
                source_text=rec.source_text,
                translated_text=translated,
                duration_s=rec.duration_s,
                speaker_label=rec.speaker_label,
                detected_lang=rec.detected_lang,
                lag_s=time.monotonic() - rec.captured_at,
                t_stt=rec.t_stt,
                t_mt=t_mt,
                t_tts=t_tts,
                dropped=dropped,
            )
        )
        self._set_status("Dang nghe...")
