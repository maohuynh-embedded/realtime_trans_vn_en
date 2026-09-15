"""Buoc [5] Text-to-Speech bang Piper.

  - Tieng Viet: vi_VN-vais1000-medium  (cho chieu Anh -> Viet)
  - Tieng Anh : en_US-lessac-medium    (cho chieu Viet -> Anh)

Tai file .onnx + .onnx.json tu kho rhasspy/piper-voices tren Hugging Face,
dat vao models/piper/ (xem README.md).

API Piper 1.8 nhan tham so qua SynthesisConfig va tra audio theo generator cac
chunk (audio_int16_bytes, sample_rate, sample_channels) - ghep lai thanh 1 mang PCM.
"""
import os

import numpy as np
from piper import PiperVoice, SynthesisConfig


class TextToSpeech:
    def __init__(self, onnx_path: str, json_path: str, length_scale: float = 1.0):
        if not os.path.exists(onnx_path):
            raise FileNotFoundError(
                f"Khong tim thay file giong Piper: {onnx_path}\n"
                "Tai file .onnx + .onnx.json tuong ung tu "
                "https://huggingface.co/rhasspy/piper-voices va dat vao models/piper/."
            )
        self.voice = PiperVoice.load(onnx_path, config_path=json_path)
        self.syn_config = SynthesisConfig(length_scale=length_scale)

    def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        """Tra ve (pcm_int16 numpy array mono, sample_rate)."""
        if not text.strip():
            return np.zeros(0, dtype=np.int16), self.voice.config.sample_rate

        chunks = []
        sample_rate = self.voice.config.sample_rate
        for audio_chunk in self.voice.synthesize(text, syn_config=self.syn_config):
            pcm = np.frombuffer(audio_chunk.audio_int16_bytes, dtype=np.int16)
            if audio_chunk.sample_channels > 1:
                pcm = pcm.reshape(-1, audio_chunk.sample_channels).mean(axis=1).astype(np.int16)
            chunks.append(pcm)
            sample_rate = audio_chunk.sample_rate

        if not chunks:
            return np.zeros(0, dtype=np.int16), sample_rate
        return np.concatenate(chunks), sample_rate
