"""Kho mau giong theo tung nguoi noi - nguon mau cho TTS sao chep giong.

Moi cau nguoi noi vua noi (tieng nguon) duoc them vao kho cua chinh nguoi do. Khi du
mau thi DUNG LAI (dong bang): mau on dinh giup TTS cache duoc dieu kien giong, va giong
khong troi qua lai giua cac cau.

Nguyen tac chon mau:
  - can toi thieu MIN_S giay moi dung duoc (ngan hon thi model doc lung tung -
    do thuc te: mau nam 5s ra rac voi MOSS-Nano)
  - gom cac cau LIEN TIEP cho toi khi du TARGET_S giay roi dong bang
  - khong bao gio vuot MAX_S giay (Chatterbox chi dung toi ~10s)
Chi them cau da qua STT va bo loc ao giac (co loi noi that), khong them nhieu/im lang.
"""
import threading
from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 16000


@dataclass(frozen=True)
class VoiceSample:
    audio: np.ndarray      # float32 mono 16kHz trong [-1, 1]
    version: int           # tang moi lan mau thay doi -> dung lam khoa cache


class VoiceBank:
    MIN_S = 3.0
    TARGET_S = 8.0
    MAX_S = 12.0

    def __init__(self) -> None:
        self._clips: dict[str, list[np.ndarray]] = {}
        self._version: dict[str, int] = {}
        self._frozen: set[str] = set()
        self._lock = threading.Lock()

    @staticmethod
    def _total_s(clips: list[np.ndarray]) -> float:
        return sum(len(c) for c in clips) / SAMPLE_RATE

    def add(self, key: str, pcm16_bytes: bytes) -> None:
        """Them mot cau cua nguoi noi `key` (PCM16 mono 16kHz)."""
        audio = np.frombuffer(pcm16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if audio.size == 0:
            return
        with self._lock:
            if key in self._frozen:
                return
            clips = self._clips.setdefault(key, [])
            clips.append(audio)
            while self._total_s(clips) > self.MAX_S and len(clips) > 1:
                clips.pop(0)
            if self._total_s(clips) > self.MAX_S:   # mot cau don le dai hon MAX_S
                clips[0] = clips[0][-int(self.MAX_S * SAMPLE_RATE):]
            self._version[key] = self._version.get(key, 0) + 1
            if self._total_s(clips) >= self.TARGET_S:
                self._frozen.add(key)

    def get(self, key: str) -> "VoiceSample | None":
        """Mau cua `key`, hoac None neu chua du MIN_S giay."""
        with self._lock:
            clips = self._clips.get(key)
            if not clips or self._total_s(clips) < self.MIN_S:
                return None
            return VoiceSample(np.concatenate(clips), self._version[key])

    def seconds(self, key: str) -> float:
        with self._lock:
            return self._total_s(self._clips.get(key, []))

    def reset(self) -> None:
        with self._lock:
            self._clips.clear()
            self._version.clear()
            self._frozen.clear()
