"""Thu nghiem sherpa-onnx tren video mau: Silero VAD va Zipformer tieng Viet.

  (1) Silero VAD vs webrtcvad: so cau, do dai, ty le bi cat cuong buc.
  (2) Zipformer-vi 30M vs Whisper turbo (MLX): toc do va MUC KHAC BIET van ban
      tren cac cau Whisper nhan la tieng Viet. Video khong co ban chep chuan nen
      day la do KHAC BIET giua hai model, khong phai do chinh xac.

Chay: .venv/bin/python evals/spike_sherpa.py evals/samples/friends9.wav
"""
import json, re, statistics, sys, time, unicodedata
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "evals"))
import sherpa_onnx  # noqa: E402
from replay import load_wav, pct  # noqa: E402

wav = Path(sys.argv[1])
pcm = load_wav(wav)
audio = pcm.astype(np.float32) / 32768.0
MODELS = ROOT / "models" / "sherpa"

# ---------------- (1) Silero VAD ----------------
def silero_segments(min_silence, max_speech, threshold=0.5):
    cfg = sherpa_onnx.VadModelConfig()
    cfg.silero_vad.model = str(MODELS / "silero_vad.onnx")
    cfg.silero_vad.threshold = threshold
    cfg.silero_vad.min_silence_duration = min_silence
    cfg.silero_vad.min_speech_duration = 0.25
    cfg.silero_vad.max_speech_duration = max_speech
    cfg.sample_rate = 16000
    vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=60)
    w = cfg.silero_vad.window_size
    segs = []
    def drain():
        while not vad.empty():
            s = vad.front
            segs.append((s.start / 16000, len(s.samples) / 16000))
            vad.pop()
    t0 = time.perf_counter()
    for i in range(0, len(audio) - w + 1, w):
        vad.accept_waveform(audio[i:i + w]); drain()
    vad.flush(); drain()
    return segs, time.perf_counter() - t0

print("== (1) Silero VAD (sherpa-onnx) ==")
print(f"  {'nguong':>6} {'im lang':>7} {'max_s':>5} | {'so cau':>6} {'trung vi':>8} {'p95':>6} {'cat cuong buc':>13} {'thoi gian chay':>14}")
for thr in (0.5,):
    for ms in (0.5, 0.3, 0.2):
        for mx in (8.0, 15.0):
            segs, dt = silero_segments(ms, mx, thr)
            d = [x[1] for x in segs]
            forced = sum(1 for x in d if x >= mx - 0.15)
            print(f"  {thr:>6} {ms:>6.1f}s {mx:>5} | {len(segs):>6} {statistics.median(d):>7.1f}s {pct(d,95):>5.1f}s {100*forced/len(d):>11.0f}% {dt:>12.1f}s")

# ---------------- (2) Zipformer-vi vs Whisper ----------------
d = MODELS / "sherpa-onnx-zipformer-vi-30M-int8-2026-02-09"
rec = sherpa_onnx.OfflineRecognizer.from_transducer(
    tokens=str(d / "tokens.txt"), encoder=str(d / "encoder.int8.onnx"),
    decoder=str(d / "decoder.onnx"), joiner=str(d / "joiner.int8.onnx"),
    num_threads=4, sample_rate=16000, feature_dim=80, decoding_method="greedy_search")

def norm(s, strip_diacritics=False):
    s = unicodedata.normalize("NFC", s.lower())
    if strip_diacritics:
        s = unicodedata.normalize("NFD", s)
        s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def edit(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]

def cer(ref, hyp):
    return edit(ref, hyp) / max(1, len(ref))

items = json.loads((wav.parent / f"{wav.stem}.transcript.json").read_text())
vi = [i for i in items if i["text"] and i["lang"] == "vi"]
ts, dur, c_full, c_plain = [], [], [], []
empty = 0
for it in vi:
    end = it["t_cut"]; start = end - it["dur"]
    seg = audio[int(start * 16000):int(end * 16000)]
    t0 = time.perf_counter()
    s = rec.create_stream(); s.accept_waveform(16000, seg); rec.decode_stream(s)
    ts.append(time.perf_counter() - t0); dur.append(it["dur"])
    hyp = s.result.text
    if not hyp.strip():
        empty += 1
    c_full.append(cer(norm(it["text"]), norm(hyp)))
    c_plain.append(cer(norm(it["text"], True), norm(hyp, True)))

print(f"\n== (2) Zipformer-vi 30M int8 (CPU, 4 luong) tren {len(vi)} cau Whisper nhan la tieng Viet ==")
print(f"  toc do: trung vi {statistics.median(ts)*1000:.0f} ms/cau, p95 {pct(ts,95)*1000:.0f} ms, RTF {sum(ts)/sum(dur):.3f}  (Whisper turbo MLX GPU: ~1200 ms/cau, RTF 0.2)")
print(f"  khac biet voi Whisper (KHONG phai do chinh xac): CER co dau trung vi {statistics.median(c_full):.2f}, khong tinh dau {statistics.median(c_plain):.2f}; cau rong {empty}")
print(f"  phan bo CER co dau: p25 {pct(c_full,25):.2f}  p75 {pct(c_full,75):.2f}  p95 {pct(c_full,95):.2f}")
