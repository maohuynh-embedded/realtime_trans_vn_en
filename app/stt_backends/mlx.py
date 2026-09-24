"""Backend MLX-Whisper: chay tren GPU Apple (Metal), bo nho hop nhat.

MLX gan luong tinh toan (stream) voi THREAD tao ra no. Pipeline nap model o mot
thread (GUI/loader) roi goi STT tu thread khac, nen moi loi goi MLX phai di qua
MOT thread rieng duy nhat, neu khong se gap 'no Stream(gpu) in current thread'.
"""
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from app.config import SttConfig
from app.stt_backends.base import RawTranscript

# Ten repo Hugging Face cua model Whisper da chuyen sang MLX (mlx-community)
MLX_REPOS = {
    "tiny": "mlx-community/whisper-tiny-mlx",
    "base": "mlx-community/whisper-base-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
}


class MlxBackend:
    name = "mlx"
    device = "gpu"
    compute_type = "float16"

    def __init__(self, cfg: SttConfig, model_ref: str | None = None):
        self._repo = model_ref or MLX_REPOS.get(cfg.model_size)
        if self._repo is None:
            raise ValueError(f"Chua co ban MLX cho model '{cfg.model_size}'")
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mlx")
        self._pool.submit(self._load).result()

    def _load(self) -> None:
        import mlx.core as mx
        from mlx_whisper.transcribe import ModelHolder
        self._mx = mx
        self._model = ModelHolder.get_model(self._repo, mx.float16)

    def _transcribe(self, audio: np.ndarray, language: str, prompt: str | None) -> RawTranscript:
        import mlx_whisper
        result = mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=self._repo,
            language=language,
            initial_prompt=prompt,
            condition_on_previous_text=False,
            temperature=0.0,          # khong thu lai o nhiet do cao: do tre on dinh
            verbose=None,
        )
        segs = result.get("segments") or []
        if not segs:
            return RawTranscript("", 0.0, 0.0, empty=True)
        return RawTranscript(
            text=" ".join(s["text"].strip() for s in segs).strip(),
            avg_logprob=float(np.mean([s["avg_logprob"] for s in segs])),
            no_speech_prob=float(np.mean([s["no_speech_prob"] for s in segs])),
        )

    def _detect(self, audio: np.ndarray) -> dict[str, float]:
        from mlx_whisper.audio import N_FRAMES, N_SAMPLES, log_mel_spectrogram, pad_or_trim
        mel = log_mel_spectrogram(audio, n_mels=self._model.dims.n_mels, padding=N_SAMPLES)
        segment = pad_or_trim(mel, N_FRAMES, axis=-2).astype(self._mx.float16)
        _tokens, probs = self._model.detect_language(segment)
        return probs

    def transcribe(self, audio_f32: np.ndarray, language: str,
                   initial_prompt: str | None) -> RawTranscript:
        return self._pool.submit(self._transcribe, audio_f32, language, initial_prompt).result()

    def detect_language(self, audio_f32: np.ndarray) -> dict[str, float]:
        return self._pool.submit(self._detect, audio_f32).result()

    def warmup(self) -> None:
        # Lan goi dau cua MLX bien dich kernel Metal (~2.5s); lam truoc de cau that
        # dau tien khong bi tre. Am thanh la nhieu nhe de di het duong giai ma.
        noise = (np.random.default_rng(0).standard_normal(16000) * 0.01).astype(np.float32)
        self._transcribe(noise, "en", None)
        self._detect(noise)
