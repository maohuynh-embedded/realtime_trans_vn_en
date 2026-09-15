"""Resample 48kHz stereo (dinh dang loopback) -> 16kHz mono (dinh dang VAD/Whisper can).

Day la buoc khac biet quan trong nhat so voi huong dung VB-CABLE (VB-CABLE co the
cau hinh san 16kHz mono). Quen buoc nay la nguyen nhan pho bien nhat khien
Whisper nhan dang sai/nhieu (xem muc 8 trong HUONG_DAN_XAY_DUNG.md).
"""
import numpy as np
from scipy import signal


def downmix_to_mono(audio: np.ndarray) -> np.ndarray:
    """audio: float32 array shape (n_frames, n_channels) hoac (n_frames,)."""
    if audio.ndim == 1:
        return audio
    return audio.mean(axis=1).astype(np.float32)


def resample_audio(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Resample 1-D float32 audio tu src_rate sang dst_rate bang scipy.signal.resample_poly."""
    if src_rate == dst_rate:
        return audio.astype(np.float32)
    gcd = np.gcd(src_rate, dst_rate)
    up = dst_rate // gcd
    down = src_rate // gcd
    out = signal.resample_poly(audio, up, down)
    return out.astype(np.float32)


def to_int16_bytes(audio_float32: np.ndarray) -> bytes:
    """Chuyen float32 [-1, 1] sang PCM16 bytes - dinh dang webrtcvad can."""
    clipped = np.clip(audio_float32, -1.0, 1.0)
    pcm16 = (clipped * 32767.0).astype(np.int16)
    return pcm16.tobytes()


def prepare_for_vad(raw_audio: np.ndarray, src_rate: int, dst_rate: int = 16000) -> bytes:
    """Pipeline day du: downmix -> resample -> PCM16 bytes."""
    mono = downmix_to_mono(raw_audio)
    resampled = resample_audio(mono, src_rate, dst_rate)
    return to_int16_bytes(resampled)
