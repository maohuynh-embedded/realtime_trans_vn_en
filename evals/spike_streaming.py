"""Mo phong nhan dang dang LUONG bang Zipformer-vi (nhanh nen nhan dang lai duoc lien tuc).

Cu moi `step` giay, nhan dang lai TOAN BO phan am thanh da tich luy cua cau, roi
"chot" cac token ma hai lan lien tiep dong y (LocalAgreement-2, nhu whisper_streaming).
Do: do tre cua tung token (tu luc token do duoc noi den luc duoc chot) va muc on dinh
(van ban da chot so voi ket qua nhan dang cuoi cung).

Chay: .venv/bin/python evals/spike_streaming.py evals/samples/friends9.wav
"""
import json, statistics, sys, time
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "evals"))
import sherpa_onnx  # noqa: E402
from replay import load_wav, pct  # noqa: E402

wav = Path(sys.argv[1])
audio = load_wav(wav).astype(np.float32) / 32768.0
d = ROOT / "models" / "sherpa" / "sherpa-onnx-zipformer-vi-30M-int8-2026-02-09"
rec = sherpa_onnx.OfflineRecognizer.from_transducer(
    tokens=str(d / "tokens.txt"), encoder=str(d / "encoder.int8.onnx"),
    decoder=str(d / "decoder.onnx"), joiner=str(d / "joiner.int8.onnx"),
    num_threads=4, sample_rate=16000, feature_dim=80, decoding_method="greedy_search")

def decode(seg):
    t0 = time.perf_counter()
    s = rec.create_stream(); s.accept_waveform(16000, seg); rec.decode_stream(s)
    r = s.result
    return list(r.tokens), list(r.timestamps), time.perf_counter() - t0

items = [i for i in json.loads((wav.parent / f"{wav.stem}.transcript.json").read_text())
         if i["text"] and i["lang"] == "vi"]

def run(step):
    lags, batch_lags, mismatch, n_tok, decode_ms = [], [], [], 0, []
    for it in items:
        end = it["t_cut"]; dur = it["dur"]; start = end - dur
        seg = audio[int(start * 16000):int(end * 16000)]
        prev, committed = [], []
        commit_at = {}          # chi so token -> thoi diem (dong ho am thanh) duoc chot
        t = step
        while True:
            t = min(t, dur)
            toks, tss, dt = decode(seg[:int(t * 16000)])
            decode_ms.append(dt * 1000)
            now = t + dt         # dong ho am thanh: da noi xong t giay, xu ly mat dt
            last = t >= dur
            if last:
                agree = len(toks)     # cuoi cau: chot het
            else:
                agree = 0
                while agree < min(len(prev), len(toks)) and prev[agree] == toks[agree]:
                    agree += 1
            for k in range(len(committed), agree):
                commit_at[k] = now
            committed = toks[:agree]
            prev = toks
            if last:
                final_toks, final_ts = toks, tss
                break
            t += step
        # do tre tung token: chot luc nao - noi luc nao (theo moc thoi gian token trong ban cuoi)
        for k, tt in commit_at.items():
            if k < len(final_ts):
                lags.append(commit_at[k] - final_ts[k])
        n_tok += len(final_toks)
        # so sanh voi cach "doi het cau roi moi nhan dang" (nhu app hien nay)
        _, _, dt_full = decode(seg)
        for ts_ in final_ts:
            batch_lags.append(dur + dt_full - ts_)
    return lags, batch_lags, decode_ms

print(f"{len(items)} cau tieng Viet (Zipformer-vi 30M int8, CPU)\n")
print(f"  {'cach lam':28s} {'tre token trung vi':>18} {'p90':>6} {'p99':>6} | {'lan nhan dang/cau':>17} {'ms/lan':>7}")
for step in (1.0, 0.5, 0.25):
    lags, batch_lags, dms = run(step)
    calls = len(dms) / len(items)
    print(f"  {'LocalAgreement, buoc '+str(step)+'s':28s} {statistics.median(lags):>17.2f}s {pct(lags,90):>5.2f}s {pct(lags,99):>5.2f}s | {calls:>17.1f} {statistics.median(dms):>7.0f}")
print(f"  {'Doi het cau (nhu hien nay)':28s} {statistics.median(batch_lags):>17.2f}s {pct(batch_lags,90):>5.2f}s {pct(batch_lags,99):>5.2f}s |")
