"""Do muc tin hieu cua TAT CA thiet bi loopback cung luc.

Giai quyet dut diem cau hoi "am thanh cua toi dang phat ra thiet bi nao?" -
cu mo video/cuoc hop len roi chay lenh nay, thiet bi nao co vach xanh chay
chinh la thiet bi can chon lam Nguon cho chieu Anh -> Viet.

Chay: python main.py --levels
"""
import sys
import threading
import time

import numpy as np
import pyaudiowpatch as pyaudio

from app.audio_devices import list_loopback_devices
from app.resample import downmix_to_mono

DURATION_S = 12.0
BAR_WIDTH = 34


class _Monitor:
    """Mo 1 loopback stream va theo doi muc am lien tuc."""

    def __init__(self, pa: pyaudio.PyAudio, device):
        self.device = device
        self.peak = 0.0          # muc cao nhat tu truoc den gio
        self.current = 0.0       # muc hien tai
        self.error: str | None = None
        self._stream = None
        try:
            self._stream = pa.open(
                format=pyaudio.paFloat32,
                channels=device.channels,
                rate=device.sample_rate,
                input=True,
                input_device_index=device.index,
                frames_per_buffer=int(device.sample_rate * 0.05),
                stream_callback=self._cb,
            )
            self._stream.start_stream()
        except Exception as exc:
            self.error = str(exc)[:40]

    def _cb(self, in_data, frame_count, time_info, status):
        audio = np.frombuffer(in_data, dtype=np.float32)
        if self.device.channels > 1:
            audio = audio.reshape(-1, self.device.channels)
        mono = downmix_to_mono(audio)
        if mono.size:
            level = float(np.sqrt(np.mean(mono ** 2)))
            self.current = level
            self.peak = max(self.peak, level)
        return (None, pyaudio.paContinue)

    def close(self):
        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass


def _bar(level: float) -> str:
    """Muc RMS -> vach. Dung thang log cho de nhin."""
    if level <= 0:
        return " " * BAR_WIDTH
    db = 20 * np.log10(max(level, 1e-6))
    frac = max(0.0, min(1.0, (db + 60) / 60))   # -60dB..0dB
    filled = int(frac * BAR_WIDTH)
    return "#" * filled + "-" * (BAR_WIDTH - filled)


def find_active_loopback(probe_s: float = 2.5):
    """Tu dong tim thiet bi loopback DANG CO am thanh phat ra.

    Nghe thu tat ca thiet bi loopback trong vai giay, tra ve cai co tin hieu manh
    nhat. Nho vay nguoi dung khong phai tu doan "video cua minh phat ra dau".
    Tra ve None neu khong thiet bi nao co tieng.
    """
    devices = list_loopback_devices()
    if not devices:
        return None

    pa = pyaudio.PyAudio()
    monitors = [_Monitor(pa, d) for d in devices]
    try:
        time.sleep(probe_s)
        alive = [m for m in monitors if not m.error]
        if not alive:
            return None
        best = max(alive, key=lambda m: m.peak)
        return best.device if best.peak > 0.005 else None
    finally:
        for m in monitors:
            m.close()
        pa.terminate()


def main() -> None:
    devices = list_loopback_devices()
    if not devices:
        print("Khong tim thay thiet bi loopback nao."); return

    print("=" * 72)
    print("DO MUC TIN HIEU CAC THIET BI LOOPBACK")
    print("=" * 72)
    print("\n>>> HAY MO VIDEO / CUOC HOP TIENG ANH LEN NGAY BAY GIO <<<")
    print(f"    Dang do trong {DURATION_S:.0f} giay...\n")
    print("Thiet bi nao co vach '#' chay = am thanh dang phat ra do.\n")

    pa = pyaudio.PyAudio()
    monitors = [_Monitor(pa, d) for d in devices]
    time.sleep(0.3)

    try:
        t_end = time.time() + DURATION_S
        while time.time() < t_end:
            lines = []
            for m in monitors:
                name = m.device.name.replace(" [Loopback]", "")[:32].ljust(32)
                if m.error:
                    lines.append(f"  {name} | LOI: {m.error}")
                else:
                    lines.append(f"  {name} |{_bar(m.current)}|")
            remain = t_end - time.time()
            sys.stdout.write("\r" + "\n".join(lines) + f"\n  con {remain:4.1f}s")
            sys.stdout.flush()
            time.sleep(0.15)
            # di chuyen con tro len de ve de len cho cu
            sys.stdout.write(f"\033[{len(lines) + 1}A")
        sys.stdout.write(f"\033[{len(lines) + 1}B\n")
    except KeyboardInterrupt:
        pass
    finally:
        for m in monitors:
            m.close()
        pa.terminate()

    # Ket luan
    print("\n" + "=" * 72)
    print("KET QUA (muc cao nhat ghi nhan duoc):")
    print("=" * 72)
    ranked = sorted(monitors, key=lambda m: m.peak, reverse=True)
    for m in ranked:
        name = m.device.name.replace(" [Loopback]", "")
        if m.error:
            print(f"  [LOI ] {name}: {m.error}")
        elif m.peak > 0.005:
            print(f"  [ CO ] {name}  (peak RMS {m.peak:.4f})")
        else:
            print(f"  [im  ] {name}")

    best = ranked[0] if ranked else None
    if best and not best.error and best.peak > 0.005:
        print(f"\n==> Am thanh cua ban dang phat ra: '{best.device.name}'")
        print("    Trong app, chon dung cai nay lam NGUON cho chieu Anh -> Viet.")
        print("    Va chon mot thiet bi KHAC de phat ban dich (tranh vong lap).")
    else:
        print("\n==> Khong thiet bi nao nhan duoc am thanh.")
        print("    - Kiem tra video/cuoc hop co dang phat that khong (co tieng trong tai/loa?).")
        print("    - Kiem tra am luong Windows khong bi tat tieng.")


if __name__ == "__main__":
    sys.exit(main() or 0)
