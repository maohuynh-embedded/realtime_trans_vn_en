"""Buoc [1] Audio Capture. Hai nguon tuy chieu dich:

  - LoopbackCapture: bat am thanh cuoc hop dang phat ra loa (WASAPI loopback,
    PyAudioWPatch) - dung cho chieu Anh -> Viet.
  - MicCapture: bat mic that cua ban (sounddevice) - dung cho chieu Viet -> Anh.

Ca hai deu chay o che do stream/callback (khong ghi ca file roi moi xu ly) va
callback CHI day du lieu vao mot queue - khong xu ly nang o day, de tranh
lam nghen luong callback cua PortAudio.
"""
import queue
import threading

import numpy as np
import pyaudiowpatch as pyaudio
import sounddevice as sd

from app.audio_devices import InputDevice, LoopbackDevice, get_default_loopback_device

# So frame moi lan callback (~30ms o 48kHz danh cho VAD 30ms sau khi resample)
_CHUNK_MS = 30


class LoopbackCapture:
    """Mo mot WASAPI loopback stream va day audio thu duoc (float32 numpy) vao queue."""

    def __init__(self, device: LoopbackDevice | None = None, out_queue: "queue.Queue | None" = None):
        self.device = device or get_default_loopback_device()
        self.out_queue: queue.Queue = out_queue if out_queue is not None else queue.Queue()
        self._pa: pyaudio.PyAudio | None = None
        self._stream = None
        self._running = threading.Event()

    @property
    def sample_rate(self) -> int:
        return self.device.sample_rate

    @property
    def channels(self) -> int:
        return self.device.channels

    def _callback(self, in_data, frame_count, time_info, status):
        audio = np.frombuffer(in_data, dtype=np.float32)
        if self.channels > 1:
            audio = audio.reshape(-1, self.channels)
        try:
            self.out_queue.put_nowait(audio.copy())
        except queue.Full:
            pass  # bo qua frame neu queue day, tranh chan callback
        return (None, pyaudio.paContinue)

    def start(self) -> None:
        self._pa = pyaudio.PyAudio()
        chunk_frames = int(self.sample_rate * _CHUNK_MS / 1000)
        self._stream = self._pa.open(
            format=pyaudio.paFloat32,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            input_device_index=self.device.index,
            frames_per_buffer=chunk_frames,
            stream_callback=self._callback,
        )
        self._stream.start_stream()
        self._running.set()

    def stop(self) -> None:
        self._running.clear()
        if self._stream is not None:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        if self._pa is not None:
            self._pa.terminate()
            self._pa = None

    def is_running(self) -> bool:
        return self._running.is_set()


class MicCapture:
    """Bat mic that cua ban bang sounddevice - nguon cho chieu Viet -> Anh.

    Cung giao dien voi LoopbackCapture (sample_rate / channels / out_queue /
    start / stop) de pipeline dung chung duoc ca hai.
    """

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
