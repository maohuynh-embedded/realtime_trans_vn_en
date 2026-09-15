"""Che do "xem video/hop tieng Anh, doc phu de tieng Viet".

Lenh don gian nhat trong app - khong phai chon thiet bi gi ca:
  python main.py --watch           -> hien phu de tieng Viet tren man hinh
  python main.py --watch --speak   -> doc to ban dich tieng Viet (dung duoc du chi co 1 loa)

App tu do xem am thanh dang phat ra thiet bi nao roi bat dung cai do.

Ve cau hoi "chi co 1 loa 1 mic thi co dich real-time duoc khong":
  - Che do phu de (mac dinh): duoc hoan toan, khong can thiet bi thu 2.
  - Che do doc to (--speak): cung duoc, nho co che TU TAT THU trong luc dang doc
    (xem DirectionPipeline._playing) nen ban dich khong bi bat lai roi dich tiep.
    Doi lai, trong vai giay dang doc tieng Viet thi app khong nghe video -> co the
    bo lo mot it noi dung. Xem video thi nen tam dung video luc do.
"""
import queue
import sys
import time

from app.config import default_config
from app.levels import find_active_loopback
from app.models import ModelHub
from app.pipeline import DirectionPipeline


def main() -> None:
    args = sys.argv[1:]
    speak = "--speak" in args
    listen_vi = "--vi" in args      # nguon la TIENG VIET (vd. ban be noi tieng Viet tren Discord)

    cfg = default_config()
    if listen_vi:
        from app.config import listen_vi_to_en_direction
        cfg.en2vi = listen_vi_to_en_direction()
    cfg.en2vi.speak = speak

    print("=" * 66)
    src, dst = ("VIET", "ANH") if listen_vi else ("ANH", "VIET")
    print(f"  DICH AM THANH TIENG {src}  ->  TIENG {dst}")
    print("=" * 66)

    print("\nDang do xem am thanh phat ra thiet bi nao...")
    print("(hay de video dang CHAY CO TIENG trong luc nay)")
    source = find_active_loopback(probe_s=3.0)

    if source is None:
        print("\n!! Khong thiet bi nao dang co am thanh.")
        print("   - Bat video len cho co tieng roi chay lai lenh nay.")
        print("   - Hoac chay 'python main.py --levels' de xem chi tiet tung thiet bi.")
        return

    print(f"--> Bat am thanh tu: {source.name}")

    # Noi phat ban dich (chi dung khi --speak)
    if speak:
        from app.audio_devices import get_default_output_device, is_same_physical_device, suggest_output_device
        output = suggest_output_device(source)
        if is_same_physical_device(source, output):
            print(f"--> Doc ban dich ra: {output.name}  (CUNG thiet bi voi nguon)")
            print("    May chi co 1 duong phat -> app se TU TAT THU trong luc doc,")
            print("    nen khong bi dich chong dich. Doi lai se bo lo vai giay video.")
        else:
            print(f"--> Doc ban dich ra: {output.name}")
    else:
        from app.audio_devices import get_default_output_device
        output = get_default_output_device()
        print("--> Che do PHU DE: chi hien chu, khong doc to (them --speak neu muon nghe)")

    status_q: queue.Queue = queue.Queue()
    result_q: queue.Queue = queue.Queue()
    hub = ModelHub(cfg, status_cb=lambda m: status_q.put(m))

    pipeline = DirectionPipeline(cfg.en2vi, cfg.audio, hub, source, output, result_q, status_q)

    print("\nDang tai model (lan dau co the mat vai phut)...")
    pipeline.load_models()
    pipeline.start()

    print("\n" + "=" * 66)
    print("  DANG NGHE. Nhan Ctrl+C de dung.")
    print("=" * 66 + "\n")

    try:
        while True:
            while True:
                try:
                    status_q.get_nowait()   # nuot status cho man hinh gon
                except queue.Empty:
                    break
            try:
                r = result_q.get(timeout=0.2)
                print(f"  EN  {r.source_text}")
                print(f"  VI  {r.translated_text}\n")
            except queue.Empty:
                continue
    except KeyboardInterrupt:
        print("\nDang dung...")
    finally:
        pipeline.stop()
        time.sleep(0.3)


if __name__ == "__main__":
    sys.exit(main() or 0)
