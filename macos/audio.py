"""Nen tang macOS: bat am thanh he thong bang Core Audio process tap.

Python khong co API sach cho Core Audio tap, nen viec bat am thanh nam trong mot
tien trinh Swift rieng (macos/sysaudio-capture) va day PCM float32 xen ke sang
day qua stdout. Khong can driver ao, khong can BlackHole cho chieu Anh -> Viet.

Uu diem so voi WASAPI loopback: helper LOAI TRU tien trinh Python khoi tap, nen
ban dich phat ra loa khong bi bat lai -> khong co vong lap, khong can chon
thiet bi phat khac thiet bi dang bat.

Giao dien ma app/ mong doi tu goi nen tang (giong windows/audio.py):
  HOST_APIS, GENERIC_ALIASES, PREFER_DEFAULT_OUTPUT
  list_loopback_devices(), get_default_loopback_device()
  is_same_physical_device(loopback, output)
  class LoopbackCapture

Quyen: macOS gan quyen 'Ghi am thanh he thong' cho tien trinh chiu trach nhiem
(ung dung da khoi chay - Terminal hoac .app), khong phai cho binary. Xem
docs/architecture-windows-vs-macos.md muc 5.
"""
import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path

import numpy as np
import sounddevice as sd

from app.audio_types import LoopbackDevice

HOST_APIS = ("Core Audio",)
GENERIC_ALIASES: tuple = ()

# Tap da loai tru tien trinh cua app -> khong co vong lap -> dung output mac dinh.
PREFER_DEFAULT_OUTPUT = True

# Mic ao de dua tieng Anh vao Zoom/Teams (chieu Viet -> Anh). Khong gom
# 'Microsoft Teams Audio' (thiet bi cua chinh Teams, khong phai duong dan cho app nay).
VIRTUAL_MIC_HINTS = ("blackhole", "loopback audio", "soundflower", "cable output", "vb-audio")
VIRTUAL_MIC_SETUP = (
    "1. Cai mic ao BlackHole:  brew install blackhole-2ch",
    "2. Trong Zoom/Teams dat Microphone = BlackHole 2ch",
    "3. Chay lai lenh nay",
)
VIRTUAL_MIC_SETUP_NOTE = "(macOS khong co san 'Stereo Mix' nhu Windows nen can BlackHole.)"
VIRTUAL_MIC_TODO = "Cai mic ao: brew install blackhole-2ch, roi dat mic trong Zoom/Teams = BlackHole 2ch"
VIRTUAL_MIC_TROUBLE = (
    "Kiem tra BlackHole da cai (brew install blackhole-2ch) va da chon lam mic trong Zoom/Teams.",
    "Kiem tra thiet bi phat la BlackHole 2ch (app phat tieng Anh vao dung thiet bi do).",
)
NO_LOOPBACK_TODO = (
    "Cap quyen 'Ghi am thanh he thong' cho Terminal: System Settings > Privacy & Security > "
    "Screen & System Audio Recording"
)

_CHUNK_MS = 30
_SILENCE_WARN_S = 8.0

_HELPER_REL = Path("sysaudio-capture/.build/sysaudio-capture.app/Contents/MacOS/sysaudio-capture")

# Mot 'thiet bi' duy nhat: tap tren toan he thong (chi so am - khong phai chi so PortAudio).
_TAP_DEVICE = LoopbackDevice(
    index=-1,
    name="Am thanh he thong (Core Audio tap) [Loopback]",
    sample_rate=48000,
    channels=2,
)


def list_loopback_devices() -> list[LoopbackDevice]:
    return [_TAP_DEVICE]


def get_default_loopback_device() -> LoopbackDevice:
    return _TAP_DEVICE


def is_same_physical_device(loopback: LoopbackDevice, output) -> bool:
    """Luon False: tap loai tru tien trinh cua app nen khong the bat lai chinh no."""
    return False


def helper_path() -> Path:
    """Duong dan binary Swift, hoac bao loi kem cach build neu chua co."""
    override = os.environ.get("SYSAUDIO_CAPTURE_BIN")
    path = Path(override) if override else Path(__file__).resolve().parent / _HELPER_REL
    if not path.is_file():
        raise FileNotFoundError(
            f"Chua co helper bat am thanh he thong: {path}\n"
            "Build bang: macos/build_helper.sh"
        )
    return path


class LoopbackCapture:
    """Chay helper Swift va day audio he thong (float32 numpy) vao queue."""

    def __init__(self, device: LoopbackDevice | None = None,
                 out_queue: "queue.Queue | None" = None, status_cb=None):
        self.device = device or _TAP_DEVICE
        self.out_queue: queue.Queue = out_queue if out_queue is not None else queue.Queue()
        self._status_cb = status_cb or (lambda _msg: None)
        self._rate = self.device.sample_rate
        self._channels = self.device.channels
        self._proc: subprocess.Popen | None = None
        self._anchor: sd.OutputStream | None = None
        self._reader: threading.Thread | None = None
        self._running = threading.Event()

    # Gia tri THUC cua tap (doc tu helper luc start), khong phai gia tri gia dinh.
    @property
    def sample_rate(self) -> int:
        return self._rate

    @property
    def channels(self) -> int:
        return self._channels

    def _open_anchor(self) -> None:
        """Mo mot stream phat im lang.

        Core Audio chi cho phep loai tru mot tien trinh khi no la 'audio client'
        (da mo stream am thanh). Neu Python chua tung phat gi, PID cua no chua co
        process object va helper se khong loai tru duoc -> bat lai ban dich.
        """
        try:
            self._anchor = sd.OutputStream(
                samplerate=48000, channels=1, dtype="float32",
                callback=lambda outdata, frames, t, status: outdata.fill(0),
            )
            self._anchor.start()
            time.sleep(0.3)
        except Exception:
            self._anchor = None

    def _read_info(self) -> dict:
        """Doc dong JSON dinh dang helper in ra stderr; loi neu helper chet."""
        box: list[str] = []
        t = threading.Thread(target=lambda: box.append(self._proc.stderr.readline()), daemon=True)
        t.start()
        t.join(5.0)
        line = box[0].decode("utf-8", "replace").strip() if box else ""
        if not line or line.startswith("error"):
            self._kill_proc()
            raise RuntimeError(f"Helper bat am thanh khong khoi dong duoc: {line or 'khong co phan hoi'}")
        return json.loads(line)

    def start(self) -> None:
        binary = helper_path()
        self._open_anchor()
        self._proc = subprocess.Popen(
            [str(binary), "--exclude-pid", str(os.getpid())],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        info = self._read_info()
        self._rate = int(info["sample_rate"])
        self._channels = int(info["channels"])

        self._running.set()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        chunk_bytes = int(self._rate * _CHUNK_MS / 1000) * self._channels * 4
        stream_fd = self._proc.stdout.fileno()
        pending = b""
        started = time.time()
        heard = False
        warned = False

        while self._running.is_set():
            data = os.read(stream_fd, chunk_bytes)
            if not data:  # helper da dong pipe
                if self._running.is_set():
                    self._status_cb("Helper bat am thanh he thong da dung dot ngot.")
                break
            pending += data
            while len(pending) >= chunk_bytes:
                audio = np.frombuffer(pending[:chunk_bytes], dtype=np.float32)
                pending = pending[chunk_bytes:]
                audio = audio.reshape(-1, self._channels).copy()
                if not heard and audio.any():
                    heard = True
                    if warned:
                        self._status_cb("Da nhan duoc am thanh he thong.")
                try:
                    self.out_queue.put_nowait(audio)
                except queue.Full:
                    pass

            # Toan so 0 keo dai: nhieu kha nang chua cap quyen (macOS tra im lang
            # thay vi bao loi), hoac dung la khong co gi dang phat.
            if not heard and not warned and time.time() - started > _SILENCE_WARN_S:
                warned = True
                self._status_cb(
                    "Chua nhan duoc am thanh he thong sau vai giay. Hay phat mot video; "
                    "neu van im lang, cap quyen 'Ghi am thanh he thong' cho Terminal/ung dung "
                    "trong System Settings > Privacy & Security."
                )

    def _kill_proc(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        proc.terminate()  # SIGTERM -> helper tu don dep tap + aggregate device
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
        for pipe in (proc.stdout, proc.stderr):
            try:
                pipe.close()
            except Exception:
                pass

    def stop(self) -> None:
        self._running.clear()
        self._kill_proc()
        if self._anchor is not None:
            try:
                self._anchor.stop()
                self._anchor.close()
            except Exception:
                pass
            self._anchor = None

    def is_running(self) -> bool:
        return self._running.is_set()
