"""Do muc tin hieu am thanh he thong tren macOS.

Chi co MOT nguon (tap toan he thong) nen khong phai 'tim thiet bi nao dang phat'
nhu Windows; ham van giu cung giao dien de watch/diagnose dung chung.
"""
import queue
import sys
import time

import numpy as np

from macos.audio import LoopbackCapture, get_default_loopback_device

DURATION_S = 12.0
BAR_WIDTH = 34


def _bar(level: float) -> str:
    """Muc RMS -> vach, thang log (-60dB..0dB)."""
    if level <= 0:
        return " " * BAR_WIDTH
    db = 20 * np.log10(max(level, 1e-6))
    frac = max(0.0, min(1.0, (db + 60) / 60))
    filled = int(frac * BAR_WIDTH)
    return "#" * filled + "-" * (BAR_WIDTH - filled)


def find_active_loopback(probe_s: float = 2.5):
    """Nghe thu am thanh he thong; tra ve thiet bi neu co tieng, None neu im lang."""
    cap = LoopbackCapture()
    cap.start()
    peak = 0.0
    try:
        t_end = time.time() + probe_s
        while time.time() < t_end:
            try:
                chunk = cap.out_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            peak = max(peak, float(np.abs(chunk).max()))
    finally:
        cap.stop()
    return get_default_loopback_device() if peak > 0.005 else None


def main() -> None:
    print("=" * 72)
    print("DO MUC TIN HIEU AM THANH HE THONG (macOS)")
    print("=" * 72)
    print("\n>>> HAY MO VIDEO / CUOC HOP TIENG ANH LEN NGAY BAY GIO <<<")
    print(f"    Dang do trong {DURATION_S:.0f} giay...\n")

    cap = LoopbackCapture(status_cb=lambda m: print(f"\n  ! {m}"))
    cap.start()
    level = 0.0
    try:
        t_end = time.time() + DURATION_S
        while time.time() < t_end:
            try:
                chunk = cap.out_queue.get(timeout=0.1)
                level = float(np.sqrt(np.mean(chunk ** 2)))
            except queue.Empty:
                pass
            sys.stdout.write(f"\r  He thong |{_bar(level)}|  con {t_end - time.time():4.1f}s")
            sys.stdout.flush()
        print()
    except KeyboardInterrupt:
        pass
    finally:
        cap.stop()
