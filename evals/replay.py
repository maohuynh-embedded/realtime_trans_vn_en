"""Phat lai mot file am thanh qua cac giai doan that cua pipeline va do do tre.

Khong can thiet bi am thanh hay quyen he thong: doc WAV 16kHz mono, cat cau bang
VadSegmenter that, chay STT (tu nhan dien ngon ngu) va dich bang ModelHub that,
do thoi gian tung buoc, roi MO PHONG hang doi (VAD -> STT -> dich) theo dong ho
am thanh de tinh do tre tu luc nguoi noi dut cau den luc co ban dich.

Chay:  .venv/bin/python evals/replay.py evals/samples/friends9.wav [--limit N]

Ket qua so lieu: evals/results/<ten>.<gio>.json (khong chua van ban goc).
Van ban nhan dang duoc ghi rieng canh file am thanh (thu muc bi gitignore).
"""
import argparse
import json
import statistics
import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import AudioConfig, default_config  # noqa: E402
from app.models import ModelHub  # noqa: E402
from app.vad_segmenter import VadSegmenter  # noqa: E402

SENTENCE_END = (".", "!", "?", "...", "。", "！", "？", "…")


def load_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1, "can WAV 16kHz mono"
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)


def segment(audio: np.ndarray, cfg: AudioConfig):
    """Cat cau bang VAD that. Tra ve danh sach (pcm, t_bat_dau, t_cat, do_cho_im_lang)."""
    seg = VadSegmenter(cfg)
    fb = seg.frame_bytes
    step = fb // 2
    out, frame_speech = [], []
    cur_start = None
    n = len(audio) // step
    for i in range(n):
        frame = audio[i * step:(i + 1) * step].tobytes()
        was_in = seg._in_utterance
        is_sp = seg._is_speech(frame)
        utt = seg.feed(frame)
        t = (i + 1) * cfg.vad_frame_ms / 1000
        if not was_in and seg._in_utterance:
            cur_start = t - len(seg._voiced_frames) * cfg.vad_frame_ms / 1000
        frame_speech.append(is_sp)
        if utt is not None:
            n_frames = int(round(utt.duration_s * 1000 / cfg.vad_frame_ms))
            tail = frame_speech[i + 1 - n_frames:i + 1]
            last_voiced = max((k for k, s in enumerate(tail) if s), default=0)
            trailing = (len(tail) - 1 - last_voiced) * cfg.vad_frame_ms / 1000
            out.append((utt.pcm16_bytes, cur_start if cur_start is not None else t - utt.duration_s, t, trailing))
            cur_start = None
    return out


def pct(values, p):
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


def simulate(items, use_buffer: bool):
    """Mo phong 2 luong noi tiep tren dong ho am thanh: STT roi (gop cau) + dich.

    items: moi phan tu co t_cut (luc VAD cat), t_speech_end, stt_s, mt_s, text, lang.
    Tra ve danh sach do tre (giay) tinh tu luc nguoi noi DUT LOI toi luc co ban dich.
    """
    stt_free = 0.0
    mt_free = 0.0
    lat = []
    buf = []          # cac manh dang cho du cau
    buf_since = None

    def flush(t_ready, group):
        nonlocal mt_free
        start = max(t_ready, mt_free)
        mt_s = sum(g["mt_s"] for g in group)
        mt_free = start + mt_s
        for g in group:
            lat.append(mt_free - g["t_speech_end"])

    for it in items:
        start = max(it["t_cut"], stt_free)
        stt_free = start + it["stt_s"]
        t_text = stt_free
        if not it["text"]:
            continue
        if not use_buffer:
            flush(t_text, [it])
            continue
        if not buf:
            buf_since = t_text
        buf.append(it)
        done = it["text"].rstrip().endswith(SENTENCE_END) or len(buf) >= 4 or it["lang"] != buf[0]["lang"]
        if done:
            flush(t_text, buf)
            buf = []
        elif t_text - buf_since > 4.0:
            flush(t_text, buf)
            buf = []
    if buf:
        flush(stt_free + 4.0, buf)   # cho het han 4s
    return lat


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("wav")
    ap.add_argument("--limit", type=int, default=0, help="chi chay N cau dau (thu nhanh)")
    args = ap.parse_args()

    wav = Path(args.wav)
    audio = load_wav(wav)
    cfg = default_config()
    print(f"File: {wav.name}  {len(audio) / 16000:.0f}s  | STT: {cfg.stt.backend}/{cfg.stt.model_size}", flush=True)

    t0 = time.time()
    utts = segment(audio, cfg.audio)
    if args.limit:
        utts = utts[:args.limit]
    print(f"VAD: {len(utts)} cau trong {time.time() - t0:.1f}s "
          f"(end_ring_ms={cfg.audio.end_ring_ms})", flush=True)

    hub = ModelHub(cfg)
    stt = hub.ensure_stt()
    hub.ensure_translator("en", "vi")

    items = []
    for k, (pcm, t_start, t_cut, trailing) in enumerate(utts):
        dur = len(pcm) / 2 / 16000
        t0 = time.perf_counter()
        text, lang = stt.transcribe_auto(pcm, candidates=("en", "vi"))
        stt_s = time.perf_counter() - t0
        mt_s = 0.0
        vi = ""
        if text and lang == "en":
            t0 = time.perf_counter()
            vi = hub.ensure_translator("en", "vi").translate(text, use_glossary=False)
            mt_s = time.perf_counter() - t0
        items.append(dict(idx=k, t_start=t_start, t_cut=t_cut, t_speech_end=t_cut - trailing,
                          trailing=trailing, dur=dur, stt_s=stt_s, mt_s=mt_s, text=text,
                          lang=lang, vi=vi))
        if (k + 1) % 20 == 0:
            print(f"  ... {k + 1}/{len(utts)}", flush=True)

    kept = [i for i in items if i["text"]]
    en = [i for i in kept if i["lang"] == "en"]
    vi_only = [i for i in kept if i["lang"] == "vi"]

    res = {
        "file": wav.name, "audio_s": len(audio) / 16000,
        "stt": f"{cfg.stt.backend}/{cfg.stt.model_size}",
        "end_ring_ms": cfg.audio.end_ring_ms,
        "utterances": len(items), "kept": len(kept), "rejected": len(items) - len(kept),
        "lang_en": len(en), "lang_vi": len(vi_only),
        "utt_len_s": {"median": statistics.median(i["dur"] for i in items),
                      "p95": pct([i["dur"] for i in items], 95),
                      "max": max(i["dur"] for i in items)},
        "vad_wait_s": {"median": statistics.median(i["trailing"] for i in items),
                       "p95": pct([i["trailing"] for i in items], 95)},
        "stt_s": {"median": statistics.median(i["stt_s"] for i in items),
                  "p95": pct([i["stt_s"] for i in items], 95),
                  "rtf": sum(i["stt_s"] for i in items) / sum(i["dur"] for i in items)},
        "mt_s": {"median": statistics.median(i["mt_s"] for i in en) if en else 0,
                 "p95": pct([i["mt_s"] for i in en], 95)},
        "ends_with_terminal_punct": sum(1 for i in kept if i["text"].rstrip().endswith(SENTENCE_END)) / max(1, len(kept)),
    }
    for name, use_buf in (("no_buffer", False), ("with_buffer_like_app", True)):
        lat = simulate(items, use_buf)
        res[f"e2e_latency_s_{name}"] = {"median": statistics.median(lat) if lat else 0,
                                        "p95": pct(lat, 95), "max": max(lat) if lat else 0}

    out_dir = ROOT / "evals" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    (out_dir / f"{wav.stem}.{stamp}.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
    (wav.parent / f"{wav.stem}.transcript.json").write_text(json.dumps(items, indent=1, ensure_ascii=False))

    print("\n=== KET QUA ===")
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
