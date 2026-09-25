"""Kiem tra tich hop: cau tieng Viet -> DirectionPipeline that (STT, dich, doc sao chep giong).

Khong can thiet bi am thanh: thay Player bang bo ghi de luu am thanh 'se phat' ra file.
Kiem tra:
  - kho mau giong gom dung mau theo nguoi noi
  - doc bang giong sao chep khi du mau, lui ve Piper khi (gia lap) bi tut lai
  - khong loi khi chay qua cac giai doan that cua pipeline

Chay: .venv/bin/python evals/e2e_clone.py
Am thanh luu tai evals/samples/cloning/e2e/ de nghe thu.
"""
import csv, queue, sys, time, types
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scipy.io import wavfile  # noqa: E402

from app.audio_types import LoopbackDevice, OutputDevice  # noqa: E402
from app.config import default_config, listen_vi_to_en_direction  # noqa: E402
from app.models import ModelHub  # noqa: E402
from app.pipeline import DirectionPipeline  # noqa: E402
from app.voice_bank import VoiceBank  # noqa: E402

FL = ROOT / "evals" / "samples" / "fleurs"
OUT = ROOT / "evals" / "samples" / "cloning" / "e2e"
OUT.mkdir(parents=True, exist_ok=True)

# ---- 1) don vi: kho mau giong ----
bank = VoiceBank()
sec = lambda s: np.zeros(int(s * 16000), dtype=np.int16).tobytes()
bank.add("a", sec(1.0)); assert bank.get("a") is None, "chua du 3s thi phai la None"
bank.add("a", sec(3.0)); s1 = bank.get("a"); assert s1 is not None and s1.version == 2
bank.add("a", sec(5.0)); s2 = bank.get("a")            # 9s >= 8s -> dong bang
assert len(s2.audio) / 16000 >= 8.0
bank.add("a", sec(5.0)); assert bank.get("a").version == s2.version, "da dong bang thi khong doi"
bank.add("b", sec(20.0)); assert len(bank.get("b").audio) / 16000 <= VoiceBank.MAX_S + 1e-6
assert bank.get("c") is None
from app.tts_clone import split_text
assert split_text("Hi there.") == ["Hi there."]
long = ("word " * 30 + "one. ") * 4
assert all(len(p) <= 240 for p in split_text(long)) and len(split_text(long)) > 1
print("don vi: kho mau giong + tach van ban OK\n", flush=True)

# ---- 2) tich hop ----
class RecordingPlayer:
    def __init__(self): self.played = []
    def play_blocking(self, pcm, sr): self.played.append((pcm.copy(), sr))
    def abort(self): pass

cfg = default_config()
status_lines = []
hub = ModelHub(cfg, status_cb=lambda m: status_lines.append(m))
direction = listen_vi_to_en_direction()
pipe = DirectionPipeline(direction, cfg.audio, hub,
                         LoopbackDevice(-1, "stub", 48000, 2), OutputDevice(0, "stub", 48000))
pipe.clone_voice = True
pipe.speak.set()

t0 = time.time()
pipe.load_models()
print(f"nap model + lam nong: {time.time() - t0:.1f}s | sao chep giong san sang: {pipe._clone is not None}", flush=True)
assert pipe._clone is not None, "khong nap duoc sao chep giong: " + " | ".join(status_lines[-3:])
rec_player = RecordingPlayer()
pipe._player = rec_player

# cau tieng Viet that (giong nam) tu FLEURS
clips = []
with open(FL / "dev.tsv", encoding="utf-8") as f:
    for r in csv.reader(f, delimiter="\t"):
        n = int(r[5]) / 16000
        if 7.0 <= n <= 12.0:
            clips.append(r[1])
        if len(clips) == 3:
            break

def run_one(name, note):
    sr_, a = wavfile.read(str(FL / "dev" / name))
    a = a.astype(np.float32) if a.dtype != np.int16 else a.astype(np.float32) / 32768.0
    pcm16 = (np.clip(a, -1, 1) * 32767).astype(np.int16).tobytes()
    utt = types.SimpleNamespace(pcm16_bytes=pcm16, duration_s=len(a) / 16000, captured_at=time.monotonic())
    n_before = len(rec_player.played)
    pipe._run_stt(utt, hub.ensure_stt(), 0)
    rec = pipe._recognized_queue.get(timeout=5)
    pipe._translate_and_speak(rec, hub.ensure_translator_for(direction), 0)
    res = pipe.result_queue.get(timeout=5)
    pcm, sr = rec_player.played[-1]
    assert len(rec_player.played) == n_before + 1
    dur = len(pcm) / sr
    wavfile.write(str(OUT / f"{note}.wav"), sr, pcm)
    print(f"  [{note}] nguoi noi={rec.speaker_key or '-'} (kho mau {pipe.voice_bank.seconds(rec.speaker_key):.1f}s) "
          f"| STT {res.t_stt:.2f}s dich {res.t_mt:.2f}s doc {res.t_tts:.2f}s ({dur:.1f}s am thanh @ {sr}Hz) "
          f"| tre {res.lag_s:.1f}s\n      EN: {res.translated_text[:90]}", flush=True)
    return sr

print("\nChay 3 cau (mong doi: sao chep giong, 24kHz):", flush=True)
sr_used = [run_one(n, f"clone_{i + 1}") for i, n in enumerate(clips)]
assert all(s == 24000 for s in sr_used), f"phai dung Chatterbox (24000Hz): {sr_used}"

print("\nGia lap TUT LAI (clone_max_lag_s < 0) -> phai lui ve Piper (22050Hz):", flush=True)
pipe.clone_max_lag_s = -1.0
sr_fb = run_one(clips[0], "fallback_piper")
assert sr_fb != 24000, "phai lui ve giong Piper"

print("\nTat clone_voice -> Piper:", flush=True)
pipe.clone_max_lag_s = 5.0; pipe.clone_voice = False
sr_off = run_one(clips[1], "clone_off_piper")
assert sr_off != 24000

print("\nTHANH CONG. Trang thai cuoi:", [s for s in status_lines if "giong" in s.lower()][-3:])
