"""Kiem tra duong dan am thanh chieu Viet -> Anh: app phat tieng Anh ra mot
thiet bi, Zoom lay tieng do tu mot "mic ao" (Stereo Mix / CABLE Output / line-in).

Script nay tu dong hoa cau hoi "doi tac co nghe duoc khong":
  1. Phat mot cau tieng Anh (Piper) ra OUTPUT device.
  2. Dong thoi ghi lai tu INPUT device (mic ao) - dung cai ma Zoom se lay.
  3. Chay Whisper tren ban ghi do -> in ra DUNG NHUNG GI DOI TAC SE NGHE THAY.

Neu buoc 3 doc ra dung cau da phat, duong dan am thanh da thong.

Chay: python main.py --check-route
"""
import queue
import sys
import threading
import time

import numpy as np
import sounddevice as sd

from app.audio_devices import (
    InputDevice,
    _card_name,
    get_default_output_device,
    suggest_output_for_virtual_mic,
    list_input_devices,
    list_output_devices,
)
from app.config import default_config
from app.platform_impl import audio as _platform
from app.resample import downmix_to_mono, resample_audio, to_int16_bytes
from app.stt import SpeechToText
from app.tts import TextToSpeech

TEST_SENTENCE = "Hello, this is a microphone routing test. If you can read this, the audio path works."

# Ten cac thiet bi thuong duoc dung lam "mic ao"
VIRTUAL_MIC_HINTS = _platform.VIRTUAL_MIC_HINTS


def find_virtual_mics() -> list[InputDevice]:
    return [d for d in list_input_devices() if any(h in d.name.lower() for h in VIRTUAL_MIC_HINTS)]


def main() -> None:
    """Chay hoan toan tu dong - khong hoi gi ca."""
    cfg = default_config()

    outputs = list_output_devices()
    if not outputs:
        print("Khong tim thay thiet bi phat nao."); return

    virtual_mics = find_virtual_mics()
    if not virtual_mics:
        print("!! CHUA CO MIC AO NAO.\n")
        print("   Zoom can mot 'mic ao' de nhan tieng Anh tu app. Cach bat:")
        for step in _platform.VIRTUAL_MIC_SETUP:
            print(f"     {step}")
        print(f"\n   {_platform.VIRTUAL_MIC_SETUP_NOTE}")
        return

    in_dev = virtual_mics[0]

    # QUAN TRONG: mic ao kieu Stereo Mix chi nghe duoc am thanh phat ra CHINH CARD
    # no thuoc ve. Stereo Mix (Realtek) khong nghe duoc tieng phat ra Maonocaster,
    # nen khong duoc dung thiet bi phat mac dinh mot cach mu quang.
    out_dev = suggest_output_for_virtual_mic(in_dev)
    if out_dev is None:
        out_dev = get_default_output_device()
        pair_note = "  (!! khong tim duoc output cung card voi mic ao)"
    else:
        pair_note = f"  (cung card voi mic ao: {_card_name(in_dev.name)})"

    print("Da tu dong chon thiet bi:")
    print(f"  Phat tieng Anh ra : [{out_dev.index}] {out_dev.name}{pair_note}")
    print(f"  Zoom nghe qua mic : [{in_dev.index}] {in_dev.name}")
    if len(virtual_mics) > 1:
        print(f"  (con {len(virtual_mics)-1} mic ao khac, dang dung cai dau tien)")

    print("\nDang tai giong doc tieng Anh...")
    tts = TextToSpeech(cfg.vi2en.tts_onnx, cfg.vi2en.tts_json)
    pcm, tts_sr = tts.synthesize(TEST_SENTENCE)
    audio = pcm.astype(np.float32) / 32768.0
    print(f'Cau test: "{TEST_SENTENCE}"  ({len(audio)/tts_sr:.1f}s)')

    in_sr = in_dev.sample_rate
    recorded: list[np.ndarray] = []

    def rec_cb(indata, frames, time_info, status):
        recorded.append(indata.copy())

    print("\nDang phat va ghi dong thoi...")
    try:
        with sd.InputStream(device=in_dev.index, samplerate=in_sr,
                            channels=min(in_dev.channels, 2), dtype="float32", callback=rec_cb):
            time.sleep(0.4)
            sd.play(audio, samplerate=tts_sr, device=out_dev.index, blocking=True)
            time.sleep(0.4)
    except Exception as exc:
        print(f"Loi khi mo stream: {exc}")
        return

    if not recorded:
        print("FAIL: khong ghi duoc gi tu mic ao."); return

    rec = downmix_to_mono(np.concatenate(recorded, axis=0))
    peak = float(np.max(np.abs(rec)))
    rms = float(np.sqrt(np.mean(rec ** 2)))
    print(f"Ghi duoc {len(rec)/in_sr:.1f}s | peak={peak:.4f} | RMS={rms:.5f}")

    if peak < 0.005:
        print("\n==> THAT BAI: mic ao khong nhan duoc tin hieu nao.")
        for hint in _platform.VIRTUAL_MIC_TROUBLE:
            print(f"    - {hint}")
        return

    print("\nDang chay Whisper tren ban ghi de xem doi tac nghe duoc gi...")
    stt = SpeechToText(cfg.stt)
    mono16k = resample_audio(rec, in_sr, cfg.audio.target_sample_rate)
    heard = stt.transcribe_pcm16(to_int16_bytes(mono16k), "en", cfg.audio.target_sample_rate)

    print("\n" + "=" * 60)
    print(f"DOI TAC SE NGHE THAY: {heard!r}")
    print("=" * 60)

    if heard.strip():
        print("\n==> THANH CONG: duong dan am thanh da thong.")
        print(f"    Trong Zoom/Teams dat Microphone = '{in_dev.name}'")
        print(f"    va trong app dat chieu Viet->Anh phat vao '{out_dev.name}'.")
    else:
        print("\n==> Co tin hieu nhung Whisper khong doc ra chu.")
        print("    Co the am luong qua nho - tang volume thiet bi phat roi thu lai.")


if __name__ == "__main__":
    sys.exit(main() or 0)
