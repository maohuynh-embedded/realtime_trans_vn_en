"""Chay pipeline o console (khong GUI) - dung de test/tinh chinh truoc khi boc GUI,
theo thu tu "console truoc, GUI sau" o muc 6 cua HUONG_DAN_XAY_DUNG.md.

  python main.py --console            -> chieu Anh->Viet (nghe doi tac)
  python main.py --console --vi2en    -> chieu Viet->Anh (doi tac nghe ban)
  python main.py --console --both     -> ca hai chieu cung luc
"""
import queue
import sys
import time

from app.audio_devices import (
    get_default_input_device,
    get_default_loopback_device,
    get_default_output_device,
    is_same_physical_device,
    suggest_output_device,
)
from app.config import default_config
from app.models import ModelHub
from app.pipeline import DirectionPipeline


def _build(direction, cfg, hub, result_q, status_q) -> DirectionPipeline:
    if direction.source == "loopback":
        source = get_default_loopback_device()
        output = suggest_output_device(source)
        if is_same_physical_device(source, output):
            print(
                "[!] CANH BAO: output trung thiet bi bi loopback bat -> ban dich se bi bat lai "
                "va dich chong dich. Hay cam tai nghe rieng."
            )
    else:
        source = get_default_input_device()
        # Chieu Viet->Anh: output phai la duong dan vao app hop (mic ao / cap loopback),
        # mac dinh lay output he thong de ban nghe thu truoc khi dinh tuyen that.
        output = get_default_output_device()

    print(f"  {direction.label}")
    print(f"    Nguon : {source.name}")
    print(f"    Phat  : {output.name}")
    return DirectionPipeline(direction, cfg.audio, hub, source, output, result_q, status_q)


def main() -> None:
    args = sys.argv[1:]
    want_vi2en = "--vi2en" in args or "--both" in args
    want_en2vi = "--vi2en" not in args or "--both" in args

    cfg = default_config()
    status_q: queue.Queue = queue.Queue()
    result_q: queue.Queue = queue.Queue()
    hub = ModelHub(cfg, status_cb=lambda m: status_q.put(m))

    directions = []
    if want_en2vi:
        directions.append(cfg.en2vi)
    if want_vi2en:
        directions.append(cfg.vi2en)

    print("Thiet bi:")
    pipelines = [_build(d, cfg, hub, result_q, status_q) for d in directions]

    print("\nDang tai model (lan dau co the mat vai phut)...")
    for p in pipelines:
        p.load_models()
    for p in pipelines:
        p.start()
    print("\nDang nghe. Nhan Ctrl+C de dung.\n")

    labels = {d.key: d.label for d in directions}
    try:
        while True:
            while True:
                try:
                    print(f"[status] {status_q.get_nowait()}")
                except queue.Empty:
                    break
            try:
                r = result_q.get(timeout=0.2)
                print(f"--- {labels.get(r.direction_key, r.direction_key)} ({r.duration_s:.1f}s) ---")
                print(f"  Nguon : {r.source_text}")
                print(f"  Dich  : {r.translated_text}")
            except queue.Empty:
                continue
    except KeyboardInterrupt:
        print("\nDang dung...")
    finally:
        for p in pipelines:
            p.stop()
        time.sleep(0.3)


if __name__ == "__main__":
    sys.exit(main() or 0)
