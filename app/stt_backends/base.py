"""Giao dien chung cua moi backend nhan dang giong noi (STT)."""
from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass
class RawTranscript:
    """Ket qua tho cua backend - chua qua bo loc ao giac."""
    text: str
    avg_logprob: float
    no_speech_prob: float
    empty: bool = False      # backend khong tra ve doan nao


class SttBackend(Protocol):
    name: str
    device: str
    compute_type: str

    def transcribe(self, audio_f32: np.ndarray, language: str,
                   initial_prompt: str | None) -> RawTranscript:
        """audio_f32: mono 16kHz float32 trong [-1, 1]."""

    def detect_language(self, audio_f32: np.ndarray) -> dict[str, float]:
        """Xac suat cho tung ma ngon ngu ('en', 'vi', ...)."""

    def warmup(self) -> None:
        """Chay thu 1 lan de bien dich kernel/nap bo nho truoc cau that dau tien."""
