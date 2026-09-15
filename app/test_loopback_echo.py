"""Test buoc 2 cua muc 6: capture WASAPI loopback va phat lai y nguyen (chua dich gi).

Muc dich: xac nhan luong audio in/out da dung thiet bi, khong bi vong/lap, va
loopback dang bat dung noi dung dang phat.

Chay: python -m app.test_loopback_echo  (chay ~8 giay roi tu dong dung)
"""
import time

import numpy as np

from app.audio_devices import get_default_loopback_device, get_default_output_device
from app.capture import LoopbackCapture
from app.resample import downmix_to_mono
from app.playback import Player


def main() -> None:
    loopback = get_default_loopback_device()
    output = get_default_output_device()
    print(f"Loopback input : {loopback.name} ({loopback.sample_rate} Hz, {loopback.channels} ch)")
    print(f"Output device  : {output.name}")

    capture = LoopbackCapture(device=loopback)
    capture.start()
    print("Dang ghi 8 giay... (mo 1 video/am thanh tieng Anh bat ky de test)")

    chunks = []
    t0 = time.time()
    while time.time() - t0 < 8.0:
        try:
            chunk = capture.out_queue.get(timeout=0.5)
            chunks.append(chunk)
        except Exception:
            continue
    capture.stop()

    if not chunks:
        print("Khong bat duoc audio nao - kiem tra lai thiet bi phat mac dinh co dang phat am thanh khong.")
        return

    audio = np.concatenate(chunks, axis=0)
    mono = downmix_to_mono(audio)
    print(f"Da bat duoc {len(mono) / loopback.sample_rate:.1f} giay audio. Dang phat lai...")

    player = Player(output)
    pcm16 = (np.clip(mono, -1, 1) * 32767).astype(np.int16)
    player.play_blocking(pcm16, loopback.sample_rate)
    print("Xong. Neu nghe dung noi dung vua phat thi loopback da hoat dong dung.")


if __name__ == "__main__":
    main()
