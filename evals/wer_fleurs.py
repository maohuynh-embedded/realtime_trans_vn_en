"""Do do chinh xac nhan dang tieng Viet tren FLEURS vi (tap dev): WER (theo am tiet) va CER.

So sanh: Zipformer-vi 30M int8 (sherpa-onnx, CPU) va Whisper (MLX, GPU Apple) cac co.
Loi chuan: cot 'transcription' cua FLEURS (chu thuong, bo dau cau). Ket qua Whisper
duoc chuan hoa cung kieu; CON SO viet bang chu/so co the tinh la loi du dung nghia.

Chay: .venv/bin/python evals/wer_fleurs.py [--limit N]
"""
import argparse, csv, re, statistics, sys, time, unicodedata, wave
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FL = ROOT / "evals" / "samples" / "fleurs"

ap = argparse.ArgumentParser(); ap.add_argument("--limit", type=int, default=0)
args = ap.parse_args()

def norm(s):
    s = unicodedata.normalize("NFC", s.lower())
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def edit(a, b):
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]

rows = []
with open(FL / "dev.tsv", encoding="utf-8") as f:
    for r in csv.reader(f, delimiter="\t"):
        rows.append((r[1], norm(r[3])))
if args.limit:
    rows = rows[:args.limit]

def load(name):
    # FLEURS luu WAV dang float32 (module wave khong doc duoc) -> dung scipy
    from scipy.io import wavfile
    sr, a = wavfile.read(str(FL / "dev" / name))
    assert sr == 16000 and a.ndim == 1, (name, sr, a.shape)
    return a.astype(np.float32) / 32768.0 if a.dtype == np.int16 else a.astype(np.float32)

audios = [load(n) for n, _ in rows]
total_s = sum(len(a) for a in audios) / 16000
print(f"{len(rows)} cau, {total_s / 60:.1f} phut am thanh\n", flush=True)

def evaluate(name, transcribe):
    t0 = time.perf_counter()
    hyps = [norm(transcribe(a)) for a in audios]
    dt = time.perf_counter() - t0
    we = sum(edit(r.split(), h.split()) for (_, r), h in zip(rows, hyps))
    wn = sum(len(r.split()) for _, r in rows)
    ce = sum(edit(r, h) for (_, r), h in zip(rows, hyps))
    cn = sum(len(r) for _, r in rows)
    per = [edit(r.split(), h.split()) / max(1, len(r.split())) for (_, r), h in zip(rows, hyps)]
    print(f"{name:34s} WER {100 * we / wn:5.1f}%  CER {100 * ce / cn:5.1f}%  "
          f"(trung vi/cau {100 * statistics.median(per):4.1f}%)  toc do {1000 * dt / len(rows):6.0f} ms/cau  RTF {dt / total_s:.3f}", flush=True)
    return hyps

import sherpa_onnx
d = ROOT / "models" / "sherpa" / "sherpa-onnx-zipformer-vi-30M-int8-2026-02-09"
rec = sherpa_onnx.OfflineRecognizer.from_transducer(
    tokens=str(d / "tokens.txt"), encoder=str(d / "encoder.int8.onnx"),
    decoder=str(d / "decoder.onnx"), joiner=str(d / "joiner.int8.onnx"),
    num_threads=4, sample_rate=16000, feature_dim=80, decoding_method="greedy_search")

def zip_tr(a):
    s = rec.create_stream(); s.accept_waveform(16000, a); rec.decode_stream(s)
    return s.result.text

evaluate("Zipformer-vi 30M int8 (CPU)", zip_tr)

from app.config import SttConfig
from app.stt_backends.mlx import MlxBackend
for size in ("small", "large-v3-turbo"):
    be = MlxBackend(SttConfig(backend="mlx", model_size=size))
    be.warmup()
    evaluate(f"Whisper {size} (MLX GPU)", lambda a, be=be: be.transcribe(a, "vi", None).text)
