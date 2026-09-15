"""Buoc [6] Phat audio ra thiet bi chi dinh.

Dung sounddevice, chi dinh ro device (tach biet khoi loopback input) de tranh
vong lap dich chong dich. Phat tuan tu tung cau, khong chong lan.

Hai cai bay da gap tren thuc te va duoc xu ly o day:
  - Piper tra audio 22050 Hz nhung thiet bi chi nhan 44100/48000 -> 'Invalid sample
    rate'. Nen phai RESAMPLE ve dung sample rate cua thiet bi truoc khi phat.
  - Windows liet ke ca endpoint khong co thiet bi cam vao -> 'Invalid device'.
    Neu gap thi tu chuyen sang thiet bi phat mac dinh thay vi lam chet ca thread.
"""
import threading

import numpy as np
import sounddevice as sd

from app.audio_devices import OutputDevice, get_default_output_device
from app.resample import resample_audio


class Player:
    def __init__(self, device: OutputDevice, status_cb=None):
        self.device = device
        self._lock = threading.Lock()
        self._status_cb = status_cb or (lambda _msg: None)
        self._fallback_done = False

    def _play_on(self, device: OutputDevice, audio_f32: np.ndarray, sample_rate: int) -> None:
        """Resample ve sample rate cua thiet bi roi phat."""
        target_sr = device.sample_rate
        data = resample_audio(audio_f32, sample_rate, target_sr) if sample_rate != target_sr else audio_f32

        # Nhan kenh neu thiet bi yeu cau stereo
        if device.channels > 1:
            data = np.repeat(data[:, None], device.channels, axis=1)

        sd.play(data, samplerate=target_sr, device=device.index, blocking=True)

    def play_blocking(self, pcm_int16: np.ndarray, sample_rate: int) -> None:
        """Phat 1 doan audio, cho phat xong roi moi tra ve (khong chong lan cau)."""
        if pcm_int16.size == 0:
            return
        audio_f32 = pcm_int16.astype(np.float32) / 32768.0

        with self._lock:
            try:
                self._play_on(self.device, audio_f32, sample_rate)
                return
            except Exception as exc:
                first_error = exc

            # Thiet bi da chon khong dung duoc -> chuyen sang thiet bi phat mac dinh
            try:
                fallback = get_default_output_device()
                if fallback.index != self.device.index:
                    if not self._fallback_done:
                        self._status_cb(
                            f"Khong phat duoc ra '{self.device.name}' ({first_error}). "
                            f"Chuyen sang '{fallback.name}'."
                        )
                        self._fallback_done = True
                    self._play_on(fallback, audio_f32, sample_rate)
                    self.device = fallback
                    return
            except Exception:
                pass

            self._status_cb(f"Loi phat audio: {first_error}")

    def abort(self) -> None:
        """Cat ngang am thanh dang phat.

        Can khi dong app: sd.play(blocking=True) dang cho phat het cau se giu
        luong PortAudio song, khien tien trinh khong thoat du cua so da dong.
        """
        try:
            sd.stop()
        except Exception:
            pass
