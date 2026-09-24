"""Backend STT cam duoc: chon theo SttConfig.backend (do app/accel.py quyet dinh)."""
from app.accel import BACKEND_FASTER_WHISPER, BACKEND_MLX
from app.config import SttConfig
from app.offline import local_model_path
from app.stt_backends.base import RawTranscript, SttBackend


def create_backend(cfg: SttConfig) -> SttBackend:
    if cfg.backend == BACKEND_MLX:
        from app.stt_backends.mlx import MlxBackend
        return MlxBackend(cfg, local_model_path(f"whisper-mlx-{cfg.model_size}"))
    if cfg.backend == BACKEND_FASTER_WHISPER:
        from app.stt_backends.faster_whisper import FasterWhisperBackend
        # faster-whisper nhan ca ten co ("small") lan duong dan thu muc model
        model_ref = local_model_path(f"whisper-{cfg.model_size}") or cfg.model_size
        return FasterWhisperBackend(cfg, model_ref)
    raise ValueError(f"Backend STT khong hop le: {cfg.backend!r}")


__all__ = ["create_backend", "RawTranscript", "SttBackend"]
