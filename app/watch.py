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


def _warn_if_noisy_device(source) -> None:
    """Do nhanh 1 giay xem thiet bi loopback co dang bi 'on' boi app khac khong.

    WASAPI loopback bat TOAN BO am thanh cua thiet bi, khong rieng gi video ban
    muon dich. Da gap that: game chay nen (Discord, trinh duyet, nhac...) phat
    tieng qua CUNG thiet bi lam nhieu tin hieu, khien VAD kho tach cau sach -
    trieu chung la app "nghe" nhung khong bao gio dich duoc gi. Canh bao truoc
    de nguoi dung khong phai doan mo tai sao.
    """
    import numpy as np
    from app.capture import LoopbackCapture

    cap = LoopbackCapture(device=source)
    try:
        cap.start()
        samples = []
        t_end = time.time() + 1.0
        while time.time() < t_end:
            try:
                chunk = cap.out_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            mono = chunk.mean(axis=1) if chunk.ndim > 1 else chunk
            samples.append(float(np.sqrt(np.mean(mono.astype(np.float64) ** 2))))
    finally:
        cap.stop()

    if samples and max(samples) > 0.05:
        print("\n  !! CANH BAO: thiet bi nay dang co am thanh NEN ngay ca khi video")
        print("     im lang (RMS toi da = %.3f). Loopback bat TOAN BO am thanh cua" % max(samples))
        print("     thiet bi, khong rieng video - neu co app khac (game, nhac, Discord)")
        print("     dang phat qua CUNG thiet bi nay, tin hieu se bi tron lan va VAD kho")
        print("     tach cau sach -> co the khong dich duoc gi ca ma khong bao loi.")
        print("     Dong hoac tat tieng cac app khac dang dung thiet bi nay roi thu lai.")


def main() -> None:
    args = sys.argv[1:]
    speak = "--speak" in args
    listen_vi = "--vi" in args      # nguon la TIENG VIET (vd. ban be noi tieng Viet tren Discord)

    cfg = default_config()
    if "--auto" in args:
        from app.config import auto_listen_direction
        cfg.en2vi = auto_listen_direction()
    elif listen_vi:
        from app.config import listen_vi_to_en_direction
        cfg.en2vi = listen_vi_to_en_direction()
    cfg.en2vi.speak = speak

    if "--tech" in args:
        from app.config import apply_domain_prompt
        apply_domain_prompt(cfg)   # nhet tu vung embedded/software/hardware cho Whisper
        print("  (che do chuyen nganh embedded/software/hardware - da bat initial_prompt)")

    print("=" * 66)
    if "--auto" in args:
        src, dst = ("ANH + VIET LAN LON", "VIET")
    else:
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
    _warn_if_noisy_device(source)

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
    if "--tech" in args:
        pipeline.tech_mode.set()   # bat glossary bao ve thuat ngu (xem app/mt.py)

    print("\nDang tai model (lan dau co the mat vai phut)...")
    pipeline.load_models()
    pipeline.start()

    print("\n" + "=" * 66)
    print("  DANG NGHE. Nhan Ctrl+C de dung.")
    print("=" * 66 + "\n")

    last_status = ""
    try:
        while True:
            while True:
                try:
                    msg = status_q.get_nowait()
                except queue.Empty:
                    break
                # Nuot cac trang thai binh thuong ("Dang nghe...", "Dang dich...")
                # cho man hinh gon, NHUNG phai in ra loi va cau bi tu choi - neu
                # khong nguoi dung se thay man hinh trong khong ma khong biet tai
                # sao (da gap dung truong hop nay: bo loc loai het moi cau ma
                # khong ai thay ly do vi status bi nuot sach).
                if "Loi" in msg or "Bo qua" in msg:
                    if msg != last_status:   # tranh in lap cung 1 loi lien tuc
                        print(f"  [!] {msg}")
                        last_status = msg
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
