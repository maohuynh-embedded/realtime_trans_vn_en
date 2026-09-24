"""Do STT qua lop SpeechToText that (backend do app/accel.py chon) tren am thanh mau.

Chay: .venv/bin/python macos/bench/bench_engine.py [small|medium|large-v3-turbo ...]
"""
import subprocess, sys, tempfile, time, wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.config import default_config
from app.stt import SpeechToText

SAMPLES = [
    ("en", "Samantha", "The quarterly revenue report shows significant growth in the embedded systems division."),
    ("en", "Samantha", "We need to check the UART interrupt handler because the buffer overflows under heavy load."),
    ("vi", "Linh", "Chúng ta cần kiểm tra lại bộ nhớ đệm vì nó bị tràn khi tải nặng."),
]


def synth(voice: str, text: str) -> bytes:
    d = Path(tempfile.mkdtemp())
    subprocess.run(["say", "-v", voice, "-o", str(d / "a.aiff"), text], check=True)
    subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", str(d / "a.aiff"), str(d / "a.wav")], check=True)
    with wave.open(str(d / "a.wav")) as w:
        return w.readframes(w.getnframes())


sizes = sys.argv[1:] or [None]
for size in sizes:
    cfg = default_config()
    if size:
        cfg.stt.model_size = size
    t0 = time.time()
    stt = SpeechToText(cfg.stt)
    print(f"\n== {cfg.stt.backend} / {cfg.stt.model_size} / {stt.cfg.device}  (nap+warmup {time.time() - t0:.1f}s)")
    for lang, voice, text in SAMPLES:
        pcm = synth(voice, text)
        secs = len(pcm) / 2 / 16000
        t0 = time.time()
        out = stt.transcribe_pcm16(pcm, lang)
        dt = time.time() - t0
        t0 = time.time()
        guess, _ = stt.detect_language(pcm)
        dl = time.time() - t0
        print(f"  [{lang}] {secs:4.1f}s audio -> {dt:5.2f}s ({secs / dt:4.1f}x realtime) lang-detect={guess}/{dl:.2f}s\n      {out}")
