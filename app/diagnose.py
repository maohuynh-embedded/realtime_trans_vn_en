"""Chan doan chat luong: soi tung buoc tren am thanh THAT dang phat.

Khac voi --watch (chi in ban dich), lenh nay in ra TAT CA thong tin trung gian
de biet buoc nao dang hong:

  - Thiet bi nao dang co tin hieu, muc am bao nhieu
  - VAD cat duoc may cau, moi cau dai bao nhieu
  - Whisper nghe ra gi (van ban goc)
  - Do tin cay cua Whisper (avg_logprob, no_speech_prob)
  - Ban dich ra gi
  - Thoi gian tung buoc

Chay: python main.py --diagnose [so_giay]
"""
import sys
import time

import numpy as np

from app.config import default_config
from app.hardware import detect
from app.levels import find_active_loopback
from app.capture import LoopbackCapture
from app.resample import prepare_for_vad
from app.speaker import SpeakerTracker
from app.vad_segmenter import VadSegmenter

DEFAULT_SECONDS = 180.0     # cho toi da 3 phut
TARGET_UTTERANCES = 8       # du 8 cau thi dung som, khong cho het gio

# Vi sao cho lau: nguoi dung thuc te KHONG noi lien tuc (choi game, hop...),
# co the im lang ca phut roi moi noi mot cau. Dem gio co dinh 25s thi thuong
# ket thuc voi 0 cau va khong chan doan duoc gi.


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    seconds = float(args[0]) if args else DEFAULT_SECONDS

    cfg = default_config()
    if "--auto" in sys.argv[1:]:
        from app.config import auto_listen_direction
        cfg.en2vi = auto_listen_direction()
    elif "--vi" in sys.argv[1:]:
        from app.config import listen_vi_to_en_direction
        cfg.en2vi = listen_vi_to_en_direction()
    if "--tech" in sys.argv[1:]:
        from app.config import apply_domain_prompt
        apply_domain_prompt(cfg)
    hw = detect()

    print("=" * 72)
    print("  CHAN DOAN CHAT LUONG DICH")
    print("=" * 72)
    print(f"Phan cung : {hw.summary()}")

    if hw.has_cuda:
        _warn_gpu_contention()
    print(f"STT       : Whisper '{cfg.stt.model_size}' / {cfg.stt.device} / {cfg.stt.compute_type}")
    print(f"Nghe tieng: {cfg.en2vi.stt_language} -> dich sang {cfg.en2vi.tgt_language}")
    print(f"Dich      : {cfg.en2vi.mt_backend}")
    print(f"Cat cau   : im lang {cfg.audio.end_ring_ms}ms, toi da {cfg.audio.max_segment_s}s")
    print()

    print("Dang do thiet bi nao co am thanh (de video CHAY CO TIENG)...")
    source = find_active_loopback(probe_s=3.0)
    if source is None:
        print("\n!! Khong thiet bi nao co am thanh. Bat video len roi chay lai.")
        return
    print(f"--> Bat tu: {source.name} ({source.sample_rate}Hz, {source.channels}ch)\n")

    print("Dang tai model...")
    from app.models import ModelHub
    hub = ModelHub(cfg)
    stt = hub.ensure_stt()
    translator, _tts = hub.ensure_direction(cfg.en2vi)
    tracker = SpeakerTracker()
    print(f"ECAPA nhan dien nguoi noi: {'CO' if tracker.using_ecapa else 'KHONG'}\n")

    print("=" * 72)
    print(f"  DANG THU - dung khi du {TARGET_UTTERANCES} cau hoac het {seconds:.0f}s")
    print("  Cu noi chuyen binh thuong, KHONG can noi lien tuc.")
    print("  (doi thoi gian cho: python main.py --diagnose 300 --auto)")
    print("=" * 72 + "\n")

    capture = LoopbackCapture(device=source)
    capture.start()

    segmenter = VadSegmenter(cfg.audio)
    frame_bytes = segmenter.frame_bytes
    pending = b""
    utterances = []
    peak_level = 0.0
    t_start = time.time()
    t_end = t_start + seconds
    last_tick = 0.0

    try:
        while time.time() < t_end and len(utterances) < TARGET_UTTERANCES:
            # Bao hieu van dang chay, de khong tuong bi treo trong luc im lang
            elapsed = time.time() - t_start
            if elapsed - last_tick >= 10.0:
                last_tick = elapsed
                print(f"  ... dang cho ({elapsed:.0f}s, {len(utterances)} cau, "
                      f"con {t_end - time.time():.0f}s)")
            try:
                chunk = capture.out_queue.get(timeout=0.5)
            except Exception:
                continue

            mono = chunk.mean(axis=1) if chunk.ndim > 1 else chunk
            if mono.size:
                peak_level = max(peak_level, float(np.abs(mono).max()))

            pending += prepare_for_vad(chunk, source.sample_rate, cfg.audio.target_sample_rate)
            while len(pending) >= frame_bytes:
                frame, pending = pending[:frame_bytes], pending[frame_bytes:]
                utt = segmenter.feed(frame)
                if utt is not None:
                    utterances.append(utt)
                    print(f"  [cat duoc cau #{len(utterances)}: {utt.duration_s:.1f}s]")
    finally:
        capture.stop()

    tail = segmenter.flush()
    if tail is not None:
        utterances.append(tail)

    print(f"\nMuc am cao nhat: {peak_level:.3f}", end="")
    if peak_level < 0.02:
        print("   <-- RAT NHO! Tang am luong video/Windows len.")
    elif peak_level > 0.98:
        print("   <-- BI CLIP! Giam am luong xuong, Whisper se nghe sai.")
    else:
        print("   (on)")

    if not utterances:
        print("\n!! Khong cat duoc cau nao. Co the:")
        print("   - Video khong co tieng noi (nhac nen?)")
        print("   - Am luong qua nho")
        print(f"   - Nguong im lang {cfg.audio.end_ring_ms}ms qua dai so voi cach noi trong video")
        return

    print(f"Cat duoc {len(utterances)} cau trong {seconds:.0f}s\n")
    print("=" * 72)
    print("  CHI TIET TUNG CAU")
    print("=" * 72)

    for i, utt in enumerate(utterances, 1):
        audio = np.frombuffer(utt.pcm16_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        lang = cfg.en2vi.stt_language
        if lang == "auto":
            try:
                lang, _p = stt.detect_language(utt.pcm16_bytes, ("en", "vi"))
            except Exception:
                lang = "en"

        t0 = time.time()
        segments, info = stt.model.transcribe(
            audio, language=lang,
            beam_size=cfg.stt.beam_size, vad_filter=False,
        )
        segs = list(segments)
        t_stt = time.time() - t0
        text_en = " ".join(s.text.strip() for s in segs).strip()

        # Do tin cay: avg_logprob cang gan 0 cang tot; duoi -1.0 la dang ngo
        avg_lp = float(np.mean([s.avg_logprob for s in segs])) if segs else float("nan")
        no_speech = float(np.mean([s.no_speech_prob for s in segs])) if segs else float("nan")

        t0 = time.time()
        if text_en and lang != cfg.en2vi.tgt_language:
            tr = (hub.ensure_translator(lang, cfg.en2vi.tgt_language)
                  if cfg.en2vi.stt_language == "auto" else translator)
            # Dong bo voi co --tech: khong bat glossary "am tham" khi nguoi
            # dung dang chan doan hoi thoai BINH THUONG (xem app/mt.py de biet
            # ly do glossary co the dich SAI cho hoi thoai thuong).
            text_vi = tr.translate(text_en, use_glossary="--tech" in sys.argv[1:])
        else:
            text_vi = "(khong can dich)" if text_en else ""
        t_mt = time.time() - t0

        try:
            spk = tracker.identify(utt.pcm16_bytes, cfg.audio.target_sample_rate).label
        except Exception:
            spk = "?"

        flag = ""
        if avg_lp == avg_lp and avg_lp < -1.0:
            flag = "  <-- WHISPER KHONG CHAC (nghe sai cao)"
        elif utt.duration_s < 1.0:
            flag = "  <-- CAU QUA NGAN (co the bi cat vun)"

        print(f"\n#{i}  {utt.duration_s:.1f}s  {spk}{flag}")
        print(f"   SRC: {text_en or '(khong nghe ra gi)'}")
        print(f"   DST: {text_vi or '(khong co)'}")
        print(f"   tin cay={avg_lp:.2f}  im_lang={no_speech:.2f}  | STT {t_stt:.2f}s  dich {t_mt:.2f}s")

    # Tong ket chan doan
    print("\n" + "=" * 72)
    print("  CHAN DOAN")
    print("=" * 72)

    durations = [u.duration_s for u in utterances]
    short = sum(1 for d in durations if d < 1.0)
    print(f"Cau trung binh {np.mean(durations):.1f}s, ngan nhat {min(durations):.1f}s")

    if short > len(utterances) * 0.3:
        print(f"! {short}/{len(utterances)} cau ngan duoi 1s -> dang bi CAT VUN.")
        print(f"  Tang end_ring_ms (hien {cfg.audio.end_ring_ms}ms) len 900-1000ms trong app/config.py")
    if peak_level < 0.02:
        print("! Am luong qua nho -> Whisper nghe sai nhieu. Tang volume len.")
    if not hw.has_cuda:
        print("! Dang chay CPU. Neu may co GPU NVIDIA thi cai torch CUDA de dung model 'medium'.")
    if cfg.stt.model_size in ("tiny", "base"):
        print(f"! Dang dung model '{cfg.stt.model_size}' (nho, de nghe sai).")
        print("  Doi sang 'medium' hoac 'large-v3' trong app/config.py de chinh xac hon.")

    print("\nLuu y: giong doc hien tai la giong Piper co dinh, KHONG phai giong")
    print("nguoi trong video. Tinh nang giu giong goc (OpenVoice V2) chua trien khai.")


if __name__ == "__main__":
    sys.exit(main() or 0)


def _warn_gpu_contention() -> None:
    """Canh bao neu GPU dang bi app KHAC chiem dung (game, trinh duyet nang...).

    Da gap that: chay --test ngay khi dang mo Teamfight Tactics -> STT tu 1s
    nhay len 51s, dich tu 0.6s len 64s. Khong phai loi cua app - GPU 6GB bi
    tranh chap giua game va model thi ca hai deu cham di ro ret. Bao truoc de
    nguoi dung khong tuong nham la app bi hong.
    """
    import subprocess

    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        util, used, total = (int(x) for x in out.split(","))
    except Exception:
        return

    if util > 50 or used > total * 0.5:
        print(f"!! GPU dang ban: {util}% su dung, {used}/{total}MB VRAM - CO THE la")
        print("   nguyen nhan chinh khien app cham, KHONG phai loi cau hinh. Kiem tra")
        print("   xem co dang mo game/trinh duyet nang khac dung GPU khong.")
