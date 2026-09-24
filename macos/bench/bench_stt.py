"""Do toc do STT tren Apple Silicon: faster-whisper (CPU int8) vs mlx-whisper (Metal GPU).

Chay: .venv/bin/python macos/bench/bench_stt.py   (can ffmpeg: brew install ffmpeg)
"""
import subprocess
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

TEXT = "The quarterly revenue report shows significant growth in the embedded systems division."

tmp = Path(tempfile.mkdtemp())
aiff, wav_path = tmp / "en.aiff", tmp / "en.wav"
subprocess.run(["say", "-o", str(aiff), TEXT], check=True)
subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", str(aiff), str(wav_path)], check=True)

with wave.open(str(wav_path), "rb") as w:
    sr = w.getframerate()
    audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
print(f"audio: {len(audio) / sr:.2f}s @ {sr}Hz")

from faster_whisper import WhisperModel

t0 = time.time()
fw = WhisperModel("small", device="cpu", compute_type="int8")
load_fw = time.time() - t0
t0 = time.time()
segs, _ = fw.transcribe(audio, language="en", beam_size=1, condition_on_previous_text=False)
text_fw = " ".join(s.text.strip() for s in segs)
print(f"[faster-whisper cpu int8] load={load_fw:.2f}s infer={time.time() - t0:.3f}s text={text_fw!r}")

import mlx_whisper

repo = "mlx-community/whisper-small-mlx"
t0 = time.time()
r = mlx_whisper.transcribe(str(wav_path), path_or_hf_repo=repo, language="en")
print(f"[mlx-whisper metal] first(load+infer)={time.time() - t0:.3f}s text={r['text'].strip()!r}")
t0 = time.time()
mlx_whisper.transcribe(str(wav_path), path_or_hf_repo=repo, language="en")
print(f"[mlx-whisper metal] warm infer={time.time() - t0:.3f}s")
