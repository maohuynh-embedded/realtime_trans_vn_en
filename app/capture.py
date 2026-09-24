"""Buoc [1] Audio Capture. Hai nguon tuy chieu dich:

  - LoopbackCapture: bat am thanh cuoc hop dang phat ra loa - dung cho chieu
    Anh -> Viet. Cai dat phu thuoc he dieu hanh (windows/audio.py: WASAPI
    loopback; macos/audio.py: Core Audio tap), chon boi app/platform_impl.py.
  - MicCapture: bat mic that cua ban (sounddevice) - dung cho chieu Viet -> Anh.
    Chay nhu nhau tren moi nen tang.

Ca hai deu chay o che do stream/callback (khong ghi ca file roi moi xu ly) va
callback CHI day du lieu vao mot queue - khong xu ly nang o day, de tranh
lam nghen luong callback cua PortAudio.

Giao dien chung cua moi nguon: sample_rate, channels, out_queue, start(), stop(),
is_running().
"""
import queue
import threading

import sounddevice as sd

from app.audio_types import InputDevice
from app.platform_impl import audio as _platform

LoopbackCapture = _platform.LoopbackCapture

# So frame moi lan callback (~30ms o 48kHz danh cho VAD 30ms sau khi resample)
_CHUNK_MS = 30


class MicCapture:
    """Bat mic that cua ban bang sounddevice - nguon cho chieu Viet -> Anh."""

    def __init__(self, device: InputDevice, out_queue: "queue.Queue | None" = None):
        self.device = device
        self.out_queue: queue.Queue = out_queue if out_queue is not None else queue.Queue()
        self._stream: sd.InputStream | None = None
        self._running = threading.Event()

    @property
    def sample_rate(self) -> int:
        return self.device.sample_rate

    @property
    def channels(self) -> int:
        return min(self.device.channels, 2)

    def _callback(self, indata, frames, time_info, status):
        try:
            self.out_queue.put_nowait(indata.copy())
        except queue.Full:
            pass

    def start(self) -> None:
        chunk_frames = int(self.sample_rate * _CHUNK_MS / 1000)
        self._stream = sd.InputStream(
            device=self.device.index,
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            blocksize=chunk_frames,
            callback=self._callback,
        )
        self._stream.start()
        self._running.set()

    def stop(self) -> None:
        self._running.clear()
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def is_running(self) -> bool:
        return self._running.is_set()
