"""Chan doan chieu VIET -> ANH tren mot file am thanh dai (video that, nhieu nhac nen).

Chay dung cac buoc that cua app: VadSegmenter -> STT (tieng Viet) + bo loc ao giac ->
nhan dien nguoi noi (ECAPA) -> dich vi->en. Bao cao de tach LOI THAT khoi GIOI HAN:
  - cat cau: ty le bi cat cuong buc
  - STT: cau bi loc, cau do tin cay thap (avg_logprob), phan bo
  - cau LAP: cac cau lien tiep giong nhau (nghi van thu lai/noi lap)
  - nguoi noi: co bao nhieu nhan, ty le doi nhan giua cac cau lien tiep
  - ten rieng lap lai: co duoc dich nhat quan khong

Chay: .venv/bin/python evals/diagnose_vi.py evals/samples/duyluan.wav [--limit N]
Van ban nhan dang chi luu cuc bo canh file am thanh (thu muc gitignore); bao cao chi in
so lieu va vai doan ngan.
"""
import argparse, collections, difflib, json, re, statistics, sys, time
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "evals"))
from replay import SENTENCE_END, load_wav, pct, segment  # noqa: E402
from app.config import default_config  # noqa: E402
from app.hallucination import is_too_quiet, should_reject  # noqa: E402
from app.models import ModelHub  # noqa: E402
from app.speaker import SpeakerTracker  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("wav"); ap.add_argument("--limit", type=int, default=0)
args = ap.parse_args()
wav = Path(args.wav)

audio = load_wav(wav)
cfg = default_config()
print(f"{wav.name}: {len(audio) / 16000 / 60:.1f} phut | STT {cfg.stt.backend}/{cfg.stt.model_size}", flush=True)

utts = segment(audio, cfg.audio)
if args.limit:
    utts = utts[:args.limit]
durs = [len(u[0]) / 2 / 16000 for u in utts]
forced = sum(1 for d in durs if d >= cfg.audio.max_segment_s - 0.1)
print(f"Cat cau: {len(utts)} cau, trung vi {statistics.median(durs):.1f}s, "
      f"cat cuong buc {100 * forced / len(utts):.0f}%", flush=True)

hub = ModelHub(cfg)
stt = hub.ensure_stt()
mt = hub.ensure_translator("vi", "en")
tracker = SpeakerTracker()
print(f"ECAPA: {'co' if tracker.using_ecapa else 'khong'}\n", flush=True)

items = []
for k, (pcm, t0, t_cut, trailing) in enumerate(utts):
    quiet, _ = is_too_quiet(pcm)
    a = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    text, lp, ns, reason = "", 0.0, 0.0, ""
    if quiet:
        reason = "qua nho"
    else:
        raw = stt.backend.transcribe(a, "vi", None)
        lp, ns = raw.avg_logprob, raw.no_speech_prob
        if raw.empty:
            reason = "rong"
        else:
            rej, why = should_reject(raw.text, raw.no_speech_prob, raw.avg_logprob)
            text, reason = ("", why) if rej else (raw.text, "")
    spk = tracker.identify(pcm, 16000) if text else None
    en, t_mt = "", 0.0
    if text:
        s = time.perf_counter()
        en = mt.translate(text, use_glossary=False)
        t_mt = time.perf_counter() - s
    items.append(dict(idx=k, t=round(t_cut, 1), dur=len(pcm) / 2 / 16000, text=text, en=en, lp=lp, ns=ns,
                      reason=reason, spk=(spk.speaker_id if spk else 0), gender=(spk.gender if spk else ""),
                      t_mt=t_mt))
    if (k + 1) % 40 == 0:
        print(f"  ... {k + 1}/{len(utts)}", flush=True)

(wav.parent / f"{wav.stem}.transcript.json").write_text(json.dumps(items, ensure_ascii=False, indent=1))
kept = [i for i in items if i["text"]]
print(f"\n=== STT ===\ncau giu lai {len(kept)}, bi loc {len(items) - len(kept)} "
      f"({collections.Counter(i['reason'].split(':')[0] for i in items if i['reason']).most_common(4)})")
lps = [i["lp"] for i in kept]
print(f"avg_logprob: trung vi {statistics.median(lps):.2f}, p10 {pct(lps, 10):.2f}, p5 {pct(lps, 5):.2f}")
low = [i for i in kept if i["lp"] < -0.8]
print(f"do tin cay THAP (avg_logprob < -0.8): {len(low)}/{len(kept)} ({100 * len(low) / len(kept):.0f}%)")
print(f"ket thuc bang dau cau: {100 * sum(1 for i in kept if i['text'].rstrip().endswith(SENTENCE_END)) / len(kept):.0f}%")

# ---- cau lap ----
print("\n=== CAU LAP (giong nhau >= 0.8 trong 4 cau ke tiep) ===")
norm = lambda s: re.sub(r"\W+", " ", s.lower()).strip()
dups = []
for a_i, a in enumerate(kept):
    for b in kept[a_i + 1:a_i + 5]:
        r = difflib.SequenceMatcher(None, norm(a["text"]), norm(b["text"])).ratio()
        if r >= 0.8 and len(a["text"]) > 25:
            dups.append((a["idx"], b["idx"], a["t"], b["t"], r, a["spk"], b["spk"]))
print(f"{len(dups)} cap lap")
for x in dups[:8]:
    print(f"  cau {x[0]}@{x[2]}s ~ cau {x[1]}@{x[3]}s  giong {x[4]:.2f}  nguoi {x[5]} vs {x[6]}")

# ---- nguoi noi ----
print("\n=== NGUOI NOI ===")
ids = [i["spk"] for i in kept]
cnt = collections.Counter(ids)
switches = sum(1 for a, b in zip(ids, ids[1:]) if a != b)
print(f"{len(cnt)} nhan khac nhau; phan bo {dict(cnt.most_common(8))}")
print(f"ty le DOI nhan giua 2 cau lien tiep: {100 * switches / max(1, len(ids) - 1):.0f}%")
g = collections.defaultdict(collections.Counter)
for i in kept:
    g[i["spk"]][i["gender"]] += 1
unstable = {s: dict(c) for s, c in g.items() if len(c) > 1}
print(f"nhan co gioi tinh khong on dinh: {len(unstable)} ({list(unstable.items())[:3]})")

# ---- ten rieng lap lai ----
print("\n=== TEN RIENG LAP LAI: dich co nhat quan khong? ===")
name_re = re.compile(r"(?<![.!?]\s)(?<!^)\b([A-ZĐÀ-Ỹ][\wà-ỹ]+(?:\s+[A-ZĐÀ-Ỹ][\wà-ỹ]+){1,3})")
names = collections.Counter()
for i in kept:
    for m in name_re.findall(i["text"]):
        names[m.strip()] += 1
for n, c in names.most_common(6):
    if c >= 3:
        outs = set()
        for i in kept:
            if n in i["text"]:
                m = re.search(r"(the |a )?\"?[A-Z][\w']+(?:\s+[A-Z][\w']+)*\"?\s+channel|channel\s+\"?[A-Z][\w' ]+", i["en"])
                outs.add(m.group(0)[:40] if m else "(khong thay 'channel')")
        print(f"  '{n}' x{c}: {len(outs)} cach dich khac nhau -> {list(outs)[:4]}")

print(f"\ndich: trung vi {statistics.median(i['t_mt'] for i in kept):.2f}s/cau (p95 {pct([i['t_mt'] for i in kept], 95):.2f}s)")
