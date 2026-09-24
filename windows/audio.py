"""Nen tang Windows: bat am thanh he thong bang WASAPI loopback (PyAudioWPatch).

Khong can VB-CABLE, driver hay quyen admin.

Giao dien ma app/ mong doi tu goi nen tang (macos/audio.py cung cap y het):
  HOST_APIS, GENERIC_ALIASES, PREFER_DEFAULT_OUTPUT
  list_loopback_devices(), get_default_loopback_device()
  is_same_physical_device(loopback, output)
  class LoopbackCapture
"""
import queue
import threading

import numpy as np
import pyaudiowpatch as pyaudio

from app.audio_types import LoopbackDevice

# Chi giu host API on dinh nhat; WDM-KS hay bao 'Invalid device' khi jack dang trong.
HOST_APIS = ("WASAPI", "DirectSound")

# "Thiet bi" ao Windows tao ra, tro toi thiet bi mac dinh chu khong phai phan cung that.
GENERIC_ALIASES = (
    "primary sound driver",
    "primary sound capture driver",
    "microsoft sound mapper",
)

# Windows can chon output KHAC thiet bi dang loopback de tranh vong lap dich chong dich.
PREFER_DEFAULT_OUTPUT = False

# Mic ao de dua tieng Anh vao Zoom/Teams (chieu Viet -> Anh)
VIRTUAL_MIC_HINTS = ("stereo mix", "cable output", "vb-audio", "line in", "what u hear", "wave out")
VIRTUAL_MIC_SETUP = (
    "1. Nhan Win+R, go:  mmsys.cpl   roi Enter",
    "2. Sang tab Recording",
    "3. Chuot phai vao vung trong > tich 'Show Disabled Devices'",
    "4. Chuot phai 'Stereo Mix' > Enable",
    "5. Chay lai lenh nay",
)
VIRTUAL_MIC_SETUP_NOTE = (
    "(Neu may bi khoa khong bat duoc Stereo Mix, dung 1 soi cap 3.5mm noi "
    "lo tai nghe vao lo mic - xem muc 1 trong README.md)"
)
VIRTUAL_MIC_TODO = (
    "Bat Stereo Mix: Win+R > mmsys.cpl > tab Recording > chuot phai > "
    "Show Disabled Devices > chuot phai Stereo Mix > Enable"
)
VIRTUAL_MIC_TROUBLE = (
    "Kiem tra Stereo Mix da Enable chua, va am luong cua no > 0.",
    "Kiem tra thiet bi phat da chon dung chua (Stereo Mix chi bat "
    "am thanh cua thiet bi phat MAC DINH cua Windows).",
)
NO_LOOPBACK_TODO = "Kiem tra thiet bi phat mac dinh trong Windows Sound settings"

_CHUNK_MS = 30


def list_loopback_devices() -> list[LoopbackDevice]:
    """Tra ve danh sach cac WASAPI loopback device hien co."""
    devices = []
    with pyaudio.PyAudio() as p:
        for dev in p.get_loopback_device_info_generator():
            devices.append(
                LoopbackDevice(
                    index=dev["index"],
                    name=dev["name"],
                    sample_rate=int(dev["defaultSampleRate"]),
                    channels=int(dev["maxInputChannels"]),
                )
            )
    return devices


def get_default_loopback_device() -> LoopbackDevice:
    """Loopback device tuong ung voi thiet bi PHAT mac dinh cua Windows."""
    with pyaudio.PyAudio() as p:
        default_speakers = p.get_default_wasapi_loopback()
        return LoopbackDevice(
            index=default_speakers["index"],
            name=default_speakers["name"],
            sample_rate=int(default_speakers["defaultSampleRate"]),
            channels=int(default_speakers["maxInputChannels"]),
        )


def _normalize_device_name(name: str) -> str:
    return name.replace("[Loopback]", "").strip().lower()


def is_same_physical_device(loopback: LoopbackDevice, output) -> bool:
    """True neu output device chinh la thiet bi dang bi loopback bat.

    Neu trung nhau se sinh vong lap: ban dich phat ra loa -> loopback bat lai ->
    dich tiep (xem muc 8 cua HUONG_DAN_XAY_DUNG.md).
    """
    return _normalize_device_name(loopback.name) == _normalize_device_name(output.name)


class LoopbackCapture:
    """Mo mot WASAPI loopback stream va day audio thu duoc (float32 numpy) vao queue.

    Callback CHI day du lieu vao queue - khong xu ly nang o day, de tranh lam
    nghen luong callback cua PortAudio.
    """

    def __init__(self, device: LoopbackDevice | None = None,
                 out_queue: "queue.Queue | None" = None, status_cb=None):
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
