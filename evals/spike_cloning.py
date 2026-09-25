"""Thu nghiem sao chep giong: mau giong TIENG VIET -> doc cau TIENG ANH bang giong do.

Cho moi model x moi mau giong x moi cau, do:
  - RTF: thoi gian sinh / thoi luong am thanh (phai < 1 de theo kip thoi gian thuc)
  - do giong (ECAPA): cosine giua mau goc va giong sinh ra; kem cosine voi mau cua
    NGUOI KHAC (doi chung) de biet model co thuc su giu giong hay chi ra giong chung
  - de hieu: nhan dang lai bang Whisper small roi tinh WER so voi cau goc
Am thanh sinh ra duoc luu de nghe thu: evals/samples/cloning/<model>/

Chay: .venv/bin/python evals/spike_cloning.py [ten_model ...]
      (mac dinh: moss-nano chatterbox voxcpm2)
"""
import csv, gc, re, statistics, sys, time, unicodedata
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FL = ROOT / "evals" / "samples" / "fleurs"
OUT = ROOT / "evals" / "samples" / "cloning"

MODELS = {
    "moss-nano": "mlx-community/MOSS-TTS-Nano-100M",
    "chatterbox": "mlx-community/chatterbox-multilingual-v3",
    "voxcpm2": "mlx-community/VoxCPM2-4bit",
}

# Cau tieng Anh tu viet (ngan / vua / dai) - khong lay tu video
TEXTS = [
    "Please send me the report before the meeting starts tomorrow morning.",
    "We tested the new system last week and the results were much better than we expected.",
    "If the battery drains too quickly, restart the device and check whether the firmware is up to date before contacting support.",
]


def load_wav(path):
    from scipy.io import wavfile
    sr, a = wavfile.read(str(path))
    a = a.astype(np.float32) / 32768.0 if a.dtype == np.int16 else a.astype(np.float32)
    return a, sr


def resample(a, sr, dst):
    from app.resample import resample_audio
    return a if sr == dst else resample_audio(a, sr, dst)


def pick_refs():
    """Mau giong tieng Viet: 1 nam that (FLEURS, 5-14s ngan nhat) + 1 nu.

    Tap dev FLEURS chi co giong NAM, nen giong nu lay tu giong tong hop 'Linh' cua
    macOS (say). Day chi la mau tam: giong tong hop de sao chep hon nguoi that, nen
    ket qua cua mau nu KHONG dai dien cho giong nguoi that.
    """
    import subprocess
    best = None
    with open(FL / "dev.tsv", encoding="utf-8") as f:
        for r in csv.reader(f, delimiter="\t"):
            n = int(r[5]) / 16000
            if 5.0 <= n <= 14.0 and (best is None or n < best[2]):
                best = (r[1], r[2], n)
    refs = {"MALE": (FL / "dev" / best[0], best[1])}

    ref_dir = OUT / "refs"
    ref_dir.mkdir(parents=True, exist_ok=True)
    text = ("Hôm nay chúng tôi sẽ trình bày kết quả kiểm tra hệ thống mới và thảo luận "
            "những việc cần làm trong tuần tới để hoàn thành dự án đúng hạn.")
    aiff, wav = ref_dir / "linh.aiff", ref_dir / "female_linh.wav"
    if not wav.exists():
        subprocess.run(["say", "-v", "Linh", "-o", str(aiff), text], check=True)
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", str(aiff), str(wav)], check=True)
    refs["FEMALE"] = (wav, text)
    return refs


def norm(s):
    s = unicodedata.normalize("NFC", s.lower())
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s)).strip()


def wer(ref, hyp):
    a, b = norm(ref).split(), norm(hyp).split()
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1] / max(1, len(a))


def main():
    import mlx.core as mx
    from mlx_audio.tts import load
    from app.speaker import _EcapaEmbedder
    from app.config import SttConfig
    from app.stt_backends.mlx import MlxBackend
    from scipy.io import wavfile

    names = sys.argv[1:] or list(MODELS)
    refs = pick_refs()
    print("Mau giong:", {g: p.name for g, (p, _) in refs.items()}, flush=True)

    ecapa = _EcapaEmbedder.get()
    def emb(a16):
        return ecapa.embed((np.clip(a16, -1, 1) * 32767).astype(np.int16).tobytes(), 16000)
    def cos(u, v):
        return float(np.dot(u, v) / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-9))

    ref_audio = {g: load_wav(p) for g, (p, _) in refs.items()}
    ref_emb = {g: emb(resample(a, sr, 16000)) for g, (a, sr) in ref_audio.items()}
    # Do chung: 2 mau nam/nu co that su khac nhau khong?
    g1, g2 = list(ref_emb)
    print(f"Doi chung: giong {g1} vs {g2} cosine = {cos(ref_emb[g1], ref_emb[g2]):.2f}\n", flush=True)

    asr = MlxBackend(SttConfig(backend="mlx", model_size="small"))

    for key in names:
        repo = MODELS[key]
        print(f"===== {key}  ({repo})", flush=True)
        out_dir = OUT / key
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            t0 = time.time()
            model = load(repo)
            print(f"  nap model: {time.time() - t0:.1f}s, sample_rate {model.sample_rate}", flush=True)
            rows = []
            for gi, (g, (path, _)) in enumerate(refs.items()):
                a_ref, sr_ref = ref_audio[g]
                for ti, text in enumerate(TEXTS):
                    kw = dict(text=text, ref_audio=str(path))
                    if key == "chatterbox":
                        kw = dict(text=text, ref_audio=mx.array(resample(a_ref, sr_ref, model.sample_rate)), lang_code="en")
                    if key == "moss-nano":
                        kw["ref_text"] = None
                    t0 = time.perf_counter()
                    chunks, sr_out = [], model.sample_rate
                    for res in model.generate(**kw):
                        chunks.append(np.array(res.audio, dtype=np.float32).reshape(-1))
                        sr_out = getattr(res, "sample_rate", sr_out)
                    dt = time.perf_counter() - t0
                    audio = np.concatenate(chunks) if chunks else np.zeros(1, np.float32)
                    dur = len(audio) / sr_out
                    a16 = resample(audio, sr_out, 16000)
                    wavfile.write(str(out_dir / f"{g.lower()}_t{ti + 1}.wav"), sr_out, audio)
                    if gi == 0 and ti == 0:
                        rows_warm = dt   # lan dau gom bien dich: bo khoi thong ke toc do
                    same = cos(emb(a16), ref_emb[g])
                    other = cos(emb(a16), ref_emb[[k for k in ref_emb if k != g][0]])
                    hyp = asr.transcribe(a16, "en", None).text
                    rows.append(dict(dt=dt, dur=dur, same=same, other=other, wer=wer(text, hyp),
                                     first=(gi == 0 and ti == 0)))
                    print(f"  {g:6s} cau{ti + 1}: {dur:5.1f}s audio, sinh {dt:5.1f}s (RTF {dt / max(dur, 1e-3):4.2f}) "
                          f"giong-dung {same:4.2f} giong-khac {other:4.2f} WER {rows[-1]['wer'] * 100:3.0f}%", flush=True)
            use = [r for r in rows if not r["first"]] or rows
            print(f"  -> RTF trung vi {statistics.median(r['dt'] / max(r['dur'], 1e-3) for r in use):.2f} | "
                  f"do giong dung {statistics.mean(r['same'] for r in use):.2f} vs khac {statistics.mean(r['other'] for r in use):.2f} | "
                  f"WER {100 * statistics.mean(r['wer'] for r in use):.0f}%\n", flush=True)
            del model
        except Exception as exc:
            print(f"  LOI: {type(exc).__name__}: {str(exc)[:200]}\n", flush=True)
        gc.collect()
        mx.clear_cache()


if __name__ == "__main__":
    main()
