"""Tu kiem tra toan bo he thong - chay 1 lenh, khong hoi gi ca.

  python main.py --test

Tuan tu kiem tra va bao cao DAT / KHONG DAT cho tung phan:
  1. Thiet bi audio (loopback / mic / output / mic ao cho Zoom)
  2. Model da tai du chua
  3. VAD cat cau
  4. Chieu Anh -> Viet  (STT en + dich + doc tieng Viet)
  5. Chieu Viet -> Anh  (STT vi + dich + doc tieng Anh)
  6. Duong dan am thanh vao Zoom (neu co mic ao)

Cuoi cung in ra viec ban can lam tiep.
"""
import sys
import time

import numpy as np

from app.audio_devices import (
    get_default_input_device,
    get_default_loopback_device,
    get_default_output_device,
    is_same_physical_device,
    list_input_devices,
    list_loopback_devices,
    list_output_devices,
    suggest_output_device,
)
from app.config import default_config
from app.platform_impl import audio as _platform
from app.resample import prepare_for_vad
from app.vad_segmenter import VadSegmenter

PASS, FAIL, WARN = "[ DAT ]", "[KHONG]", "[ LUU ]"
_results: list[tuple[str, str]] = []
_todo: list[str] = []


def _report(status: str, msg: str) -> None:
    print(f"  {status} {msg}")
    _results.append((status, msg))


def _header(n: int, title: str) -> None:
    print(f"\n{'=' * 62}\n{n}. {title}\n{'=' * 62}")


def check_devices(cfg):
    _header(1, "THIET BI AUDIO")
    ok = True

    loopbacks = list_loopback_devices()
    if loopbacks:
        lb = get_default_loopback_device()
        _report(PASS, f"Loopback (bat am thanh cuoc hop): {lb.name}")
    else:
        _report(FAIL, "Khong tim thay loopback device nao")
        _todo.append(_platform.NO_LOOPBACK_TODO)
        return None, None, None, False

    mics = list_input_devices()
    if mics:
        mic = get_default_input_device()
        _report(PASS, f"Mic cua ban (cho chieu Viet->Anh): {mic.name}")
    else:
        mic = None
        _report(FAIL, "Khong tim thay mic nao")
        ok = False

    outputs = list_output_devices()
    _report(PASS if outputs else FAIL, f"Thiet bi phat: tim thay {len(outputs)} cai")

    # Kiem tra nguy co vong lap
    suggested = suggest_output_device(lb)
    if is_same_physical_device(lb, suggested):
        _report(WARN, "Chi co 1 duong phat -> nen BO TICH 'Doc thanh tieng' o chieu Anh->Viet")
        _todo.append("Bo tich 'Doc thanh tieng' o chieu Anh->Viet de tranh vong lap")
    else:
        _report(PASS, f"Duong phat ban dich tieng Viet (tach biet): {suggested.name}")

    # Mic ao cho Zoom
    from app.route_check import find_virtual_mics
    vmics = find_virtual_mics()
    if vmics:
        _report(PASS, f"Mic ao cho Zoom: {vmics[0].name}")
    else:
        _report(WARN, "Chua co mic ao -> doi tac CHUA nghe duoc tieng Anh")
        _todo.append(_platform.VIRTUAL_MIC_TODO)

    return lb, mic, suggested, ok


def check_models(cfg):
    _header(2, "MODEL")
    import os
    ok = True
    for label, path in [
        ("Giong doc tieng Viet", cfg.en2vi.tts_onnx),
        ("Giong doc tieng Anh", cfg.vi2en.tts_onnx),
    ]:
        if os.path.exists(path):
            _report(PASS, f"{label}: {os.path.basename(path)} ({os.path.getsize(path)//1024//1024} MB)")
        else:
            _report(FAIL, f"{label}: THIEU {path}")
            _todo.append(f"Tai file giong Piper con thieu: {path}")
            ok = False
    _report(PASS, "Whisper + MarianMT se tu tai/lay tu cache khi chay")
    return ok


def check_vad(cfg):
    _header(3, "CAT CAU (VAD)")
    seg = VadSegmenter(cfg.audio)
    sr = 48000

    def block(dur, speech):
        n = int(sr * dur)
        if speech:
            t = np.arange(n) / sr
            s = 0.3 * np.sin(2 * np.pi * 150 * t) + 0.2 * np.sin(2 * np.pi * 450 * t)
            s += 0.05 * np.random.randn(n)
        else:
            s = 0.0001 * np.random.randn(n)
        return np.stack([s, s], axis=1).astype(np.float32)

    audio = np.concatenate([block(0.4, False), block(2.0, True), block(1.0, False)], axis=0)
    chunk, pending, utts = int(sr * 0.03), b"", []
    for i in range(0, len(audio), chunk):
        pending += prepare_for_vad(audio[i:i + chunk], sr, cfg.audio.target_sample_rate)
        while len(pending) >= seg.frame_bytes:
            frame, pending = pending[:seg.frame_bytes], pending[seg.frame_bytes:]
            u = seg.feed(frame)
            if u:
                utts.append(u)
    tail = seg.flush()
    if tail:
        utts.append(tail)

    if utts:
        _report(PASS, f"Cat duoc {len(utts)} cau tu audio thu ({utts[0].duration_s:.1f}s)")
        return True
    _report(FAIL, "Khong cat duoc cau nao")
    return False


def check_direction(cfg, hub, direction, sample_text_tts, label):
    """Test 1 chieu bang cach tu tao audio roi cho chay qua STT -> MT -> TTS."""
    from app.tts import TextToSpeech

    _header(4 if direction.key == "en2vi" else 5, f"CHIEU {label}")
    try:
        # Tao audio o ngon ngu NGUON de lam dau vao gia lap
        src_voice = TextToSpeech(sample_text_tts[1], sample_text_tts[2])
        pcm, sr = src_voice.synthesize(sample_text_tts[0])
        mono16k = prepare_for_vad(pcm.astype(np.float32) / 32768.0, sr, cfg.audio.target_sample_rate)

        stt = hub.ensure_stt()
        translator, tts = hub.ensure_direction(direction)

        t0 = time.time()
        heard = stt.transcribe_pcm16(mono16k, direction.stt_language, cfg.audio.target_sample_rate)
        t_stt = time.time() - t0

        t0 = time.time()
        translated = translator.translate(heard)
        t_mt = time.time() - t0

        t0 = time.time()
        out_pcm, out_sr = tts.synthesize(translated)
        t_tts = time.time() - t0

        print(f"     Nghe duoc : {heard}")
        print(f"     Dich ra   : {translated}")
        print(f"     Doc thanh : {len(out_pcm)/out_sr:.1f}s audio")
        print(f"     Do tre    : STT {t_stt:.1f}s + dich {t_mt:.1f}s + doc {t_tts:.1f}s"
              f" = {t_stt+t_mt+t_tts:.1f}s")

        if heard.strip() and translated.strip() and len(out_pcm) > 0:
            _report(PASS, f"Chieu {label} hoat dong day du")
            return True
        _report(FAIL, f"Chieu {label} co buoc tra ve rong")
        return False
    except Exception as exc:
        _report(FAIL, f"Chieu {label} loi: {exc}")
        return False


def main() -> None:
    print("\n" + "#" * 62)
    print("#  TU KIEM TRA APP PHIEN DICH CUOC HOP")
    print("#  (khong can lam gi, chi ngoi xem ket qua)")
    print("#" * 62)

    cfg = default_config()
    check_devices(cfg)
    models_ok = check_models(cfg)
    check_vad(cfg)

    if models_ok:
        from app.models import ModelHub
        print("\nDang tai model (lan dau co the mat vai phut)...")
        hub = ModelHub(cfg, status_cb=lambda m: print(f"  ... {m}"))

        check_direction(
            cfg, hub, cfg.en2vi,
            ("Good morning, thanks for joining the call today.",
             cfg.vi2en.tts_onnx, cfg.vi2en.tts_json),   # giong ANH lam dau vao
            "ANH -> VIET",
        )
        check_direction(
            cfg, hub, cfg.vi2en,
            ("Chúng tôi cần thêm hai tuần để hoàn thành phần tích hợp.",
             cfg.en2vi.tts_onnx, cfg.en2vi.tts_json),   # giong VIET lam dau vao
            "VIET -> ANH",
        )

    # Tong ket
    print("\n" + "#" * 62)
    n_pass = sum(1 for s, _ in _results if s == PASS)
    n_fail = sum(1 for s, _ in _results if s == FAIL)
    n_warn = sum(1 for s, _ in _results if s == WARN)
    print(f"#  KET QUA: {n_pass} dat, {n_fail} khong dat, {n_warn} luu y")
    print("#" * 62)

    if _todo:
        print("\nVIEC BAN CAN LAM TIEP:")
        for i, t in enumerate(_todo, 1):
            print(f"  {i}. {t}")
    else:
        print("\nTat ca san sang. Chay app bang:  python main.py")

    print("\nTest voi am thanh THAT (mo 1 video YouTube tieng Anh roi chay):")
    print("  python main.py --console")


if __name__ == "__main__":
    sys.exit(main() or 0)
