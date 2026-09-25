"""Phan tich them tu ket qua replay: gom cau dung theo timer cua app, do tre tu dau cau,
va quet tham so VAD (khong can chay lai model).

Chay: .venv/bin/python evals/analyze.py evals/samples/friends9.wav
"""
import json, statistics, sys, wave
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))
from replay import SENTENCE_END, load_wav, pct, segment  # noqa: E402
from app.config import AudioConfig  # noqa: E402

wav = Path(sys.argv[1])
items = json.loads((wav.parent / f"{wav.stem}.transcript.json").read_text())

# ---- 1) Mo phong gom cau CHINH XAC hon: app kiem tra timeout moi 0.3s, cho toi da 4s ----
def simulate(items, buffered, poll=0.3, max_wait=4.0, max_parts=4):
    stt_free = mt_free = 0.0
    out = []                         # (t_start_cau, t_speech_end, t_ban_dich)
    buf, since = [], None

    def flush(t_ready, group):
        nonlocal mt_free
        start = max(t_ready, mt_free)
        mt_free = start + sum(g["mt_s"] for g in group)
        for g in group:
            out.append((g["t_start"], g["t_speech_end"], mt_free))

    ready = []
    for it in items:
        s = max(it["t_cut"], stt_free); stt_free = s + it["stt_s"]
        if it["text"]:
            ready.append((stt_free, it))
    for t_text, it in ready:
        # timeout cua buffer dang do xay ra TRUOC khi manh moi toi
        if buf and t_text > since + max_wait:
            t_fire = since + max_wait
            t_fire = since + np.ceil((t_fire - since) / poll) * poll
            flush(min(t_fire, t_text), buf); buf = []
        if not buffered:
            flush(t_text, [it]); continue
        if buf and it["lang"] != buf[0]["lang"]:
            flush(t_text, buf); buf = []
        if not buf:
            since = t_text
        buf.append(it)
        if it["text"].rstrip().endswith(SENTENCE_END) or len(buf) >= max_parts:
            flush(t_text, buf); buf = []
    if buf:
        flush(max(stt_free, since + max_wait), buf)
    return out

def summarize(rows):
    end_lat = [r[2] - r[1] for r in rows]     # tu luc dut loi
    start_lat = [r[2] - r[0] for r in rows]   # tu luc BAT DAU noi cau do
    f = lambda v: f"trung vi {statistics.median(v):5.1f}s  p95 {pct(v,95):5.1f}s  max {max(v):5.1f}s"
    return f"tu luc dut loi: {f(end_lat)} | tu luc bat dau cau: {f(start_lat)}"

print("== Do tre mo phong (ca video, dich moi cau tieng Anh; cau Viet khong dich) ==")
en = [i for i in items if i["text"]]
for name, buf in (("Khong gom cau", False), ("Gom cau nhu app (timer 0,3s/4s/4 manh)", True)):
    rows = simulate(items, buf)
    # chi tinh cau CO dich (tieng Anh) de dung nhu nguoi dung cam nhan
    rows_en = [r for r, it in zip(simulate(items, buf), [i for i in items if i["text"]]) if it["lang"] == "en"]
    print(f"  {name:42s} {summarize(rows_en)}")

durs = [i["dur"] for i in items]
forced = sum(1 for d in durs if d >= 7.9)
print(f"\n== Cat cau ==\n  {forced}/{len(durs)} cau ({100*forced/len(durs):.0f}%) bi CAT CUONG BUC o {AudioConfig().max_segment_s}s (do dai >= 7.9s)")
kept = [i for i in items if i["text"]]
print(f"  {100*sum(1 for i in kept if not i['text'].rstrip().endswith(SENTENCE_END))/len(kept):.0f}% van ban khong ket thuc bang dau cau")

# ---- 2) Quet tham so VAD (chi VAD, ~0.2s moi lan) ----
audio = load_wav(wav)
print("\n== Quet tham so VAD (chi cat cau, khong chay model) ==")
print(f"  {'aggr':>4} {'end_ms':>6} {'ratio':>5} {'max_s':>5} | {'so cau':>6} {'trung vi':>8} {'p95':>6} {'cat cuong buc':>13}")
for aggr in (2, 3):
    for end_ms in (700, 500, 300):
        for ratio in (0.6, 0.8):
            for max_s in (8.0, 15.0):
                cfg = AudioConfig(vad_aggressiveness=aggr, end_ring_ms=end_ms, end_trigger_ratio=ratio, max_segment_s=max_s)
                u = segment(audio, cfg)
                d = [len(x[0]) / 2 / 16000 for x in u]
                forced = sum(1 for x in d if x >= max_s - 0.1)
                print(f"  {aggr:>4} {end_ms:>6} {ratio:>5} {max_s:>5} | {len(u):>6} {statistics.median(d):>7.1f}s {pct(d,95):>5.1f}s {100*forced/len(d):>11.0f}%")
