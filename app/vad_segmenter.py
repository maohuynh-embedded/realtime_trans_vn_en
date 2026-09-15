"""Buoc [2] VAD: cat luong audio 16kHz mono lien tuc thanh tung 'cau' (utterance).

Thuat toan collector 2 trang thai theo muc 3.2 cua HUONG_DAN_XAY_DUNG.md:
  - CHUA_BAT_DAU: dung ring buffer ngan (~150-300ms), da so frame co tieng noi -> bat dau cau.
  - DANG_TRONG_CAU: dung ring buffer khac (~500-700ms), da so frame im lang -> ket thuc cau.
  - Co them nguong cat cuong buc de tranh doi tac noi lien tuc lam do tre don qua lon.

Day la buoc quan trong nhat quyet dinh "cam giac real-time": cat qua som se dich
sai ngu canh, cat qua muon se tang do tre.
"""
import collections
import time
from dataclasses import dataclass

import webrtcvad

from app.config import AudioConfig


@dataclass
class Utterance:
    """Mot cau audio da cat xong, dinh dang PCM16 mono 16kHz, san sang dua vao STT."""
    pcm16_bytes: bytes
    duration_s: float
    captured_at: float = 0.0
    """Thoi diem cau duoc cat xong (time.monotonic()).

    Dung de do do TRE THUC TE ma nguoi dung cam nhan = luc nghe thay ban dich
    tru di luc doi tac dut cau, va de phat hien queue dang bi don u.
    """


class VadSegmenter:
    """Nhan frame PCM16 30ms lien tuc (feed()), tra ve Utterance khi cat duoc 1 cau."""

    def __init__(self, cfg: AudioConfig):
        self.cfg = cfg
        self.vad = webrtcvad.Vad(cfg.vad_aggressiveness)
        self.frame_bytes = int(cfg.target_sample_rate * cfg.vad_frame_ms / 1000) * 2  # PCM16 = 2 bytes/sample

        start_ring_len = max(1, cfg.start_ring_ms // cfg.vad_frame_ms)
        end_ring_len = max(1, cfg.end_ring_ms // cfg.vad_frame_ms)
        self._start_ring: collections.deque = collections.deque(maxlen=start_ring_len)
        self._end_ring: collections.deque = collections.deque(maxlen=end_ring_len)

        self._in_utterance = False
        self._voiced_frames: list[bytes] = []
        self._leading_frames: list[bytes] = []  # giu lai vai frame truoc luc bat dau, tranh cat mat dau tu

        self._max_frames = int(cfg.max_segment_s * 1000 / cfg.vad_frame_ms)

    def _is_speech(self, frame: bytes) -> bool:
        return self.vad.is_speech(frame, self.cfg.target_sample_rate)

    def feed(self, frame: bytes) -> "Utterance | None":
        """Nap 1 frame PCM16 (dung do dai self.frame_bytes). Tra ve Utterance neu vua cat xong 1 cau."""
        if len(frame) != self.frame_bytes:
            return None  # bo qua frame sai kich thuoc (vd. cuoi stream)

        is_speech = self._is_speech(frame)

        if not self._in_utterance:
            self._start_ring.append((frame, is_speech))
            self._leading_frames.append(frame)
            if len(self._leading_frames) > self._start_ring.maxlen:
                self._leading_frames.pop(0)

            voiced_count = sum(1 for _, sp in self._start_ring if sp)
            if len(self._start_ring) == self._start_ring.maxlen and (
                voiced_count / len(self._start_ring) >= self.cfg.start_trigger_ratio
            ):
                # bat dau cau: lay ca cac frame "dem" truoc do de khong mat dau tu
                self._in_utterance = True
                self._voiced_frames = list(self._leading_frames)
                self._start_ring.clear()
                self._end_ring.clear()
            return None

        # dang trong cau
        self._voiced_frames.append(frame)
        self._end_ring.append((frame, is_speech))

        force_cut = len(self._voiced_frames) >= self._max_frames
        silence_cut = False
        if len(self._end_ring) == self._end_ring.maxlen:
            silence_count = sum(1 for _, sp in self._end_ring if not sp)
            silence_cut = (silence_count / len(self._end_ring)) >= self.cfg.end_trigger_ratio

        if force_cut or silence_cut:
            pcm_bytes = b"".join(self._voiced_frames)
            duration_s = len(self._voiced_frames) * self.cfg.vad_frame_ms / 1000
            self._reset()
            return Utterance(pcm16_bytes=pcm_bytes, duration_s=duration_s, captured_at=time.monotonic())

        return None

    def _reset(self) -> None:
        self._in_utterance = False
        self._voiced_frames = []
        self._leading_frames = []
        self._start_ring.clear()
        self._end_ring.clear()

    def flush(self) -> "Utterance | None":
        """Goi khi dung app: xuat not cau dang do dang (neu co)."""
        if self._in_utterance and self._voiced_frames:
            pcm_bytes = b"".join(self._voiced_frames)
            duration_s = len(self._voiced_frames) * self.cfg.vad_frame_ms / 1000
            self._reset()
            return Utterance(pcm16_bytes=pcm_bytes, duration_s=duration_s, captured_at=time.monotonic())
        return None
