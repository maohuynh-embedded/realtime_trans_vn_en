"""Buoc [3] Speech-to-Text bang faster-whisper (CTranslate2, CPU int8).

Mot instance dung chung cho ca 2 chieu - ngon ngu truyen vao tung lan goi,
tiet kiem RAM va thoi gian load so voi load 2 model rieng.
"""
from dataclasses import replace

import numpy as np
from faster_whisper import WhisperModel

from app.config import SttConfig
from app.cuda_setup import ensure_cuda_dlls


class SpeechToText:
    def __init__(self, cfg: SttConfig):
        self.cfg = cfg
        if cfg.device == "cuda":
            ensure_cuda_dlls()
        try:
            self.model = WhisperModel(
                cfg.model_size,
                device=cfg.device,
                compute_type=cfg.compute_type,
            )
        except Exception:
            if cfg.device != "cuda":
                raise
            # GPU khong dung duoc (thieu driver/DLL) -> lui ve CPU thay vi chet han
            self.cfg = replace(cfg, device="cpu", compute_type="int8")
            self.model = WhisperModel(
                self.cfg.model_size,
                device="cpu",
                compute_type="int8",
            )

    def transcribe_pcm16(self, pcm16_bytes: bytes, language: str, sample_rate: int = 16000) -> str:
        """Nhan PCM16 mono bytes (dau ra cua VAD), tra ve text o ngon ngu `language`.

        Co dinh `language` (khong de Whisper tu doan) de giam tre va tang do chinh xac.
        """
        audio_f32 = np.frombuffer(pcm16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _info = self.model.transcribe(
            audio_f32,
            language=language,
            beam_size=self.cfg.beam_size,
            vad_filter=self.cfg.vad_filter,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()
