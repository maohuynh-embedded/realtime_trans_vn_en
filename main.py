"""Entry point.

  python main.py --watch             -> DON GIAN NHAT: dich video dang xem, tu do thiet bi
  python main.py --watch --speak     -> nhu tren nhung doc to ban dich
  python main.py --levels            -> xem am thanh dang phat ra thiet bi nao
  python main.py                     -> mo GUI (ca 2 chieu)
  python main.py --console           -> console, chieu Anh->Viet (nghe doi tac)
  python main.py --console --vi2en   -> console, chieu Viet->Anh (doi tac nghe ban)
  python main.py --console --both    -> console, ca hai chieu cung luc
  python main.py --devices           -> in danh sach thiet bi audio roi thoat
  python main.py --echo              -> test capture + phat lai (chua dich)
  python main.py --check-route       -> kiem tra doi tac co nghe duoc tieng Anh khong
"""
import sys


def _force_utf8_console() -> None:
    """Ten thiet bi audio co the chua ky tu tieng Viet -> console cp1252 se loi.

    Ep stdout/stderr sang UTF-8 (thay ky tu khong ho tro thay vi crash).
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main() -> None:
    _force_utf8_console()
    args = sys.argv[1:]

    if "--devices" in args:
        from app.audio_devices import print_devices
        print_devices()
        return

    if "--echo" in args:
        from app.test_loopback_echo import main as echo_main
        echo_main()
        return

    if "--watch" in args:
        from app.watch import main as watch_main
        watch_main()
        return

    if "--levels" in args:
        from app.levels import main as levels_main
        levels_main()
        return

    if "--test" in args:
        from app.selftest import main as selftest_main
        selftest_main()
        return

    if "--check-route" in args:
        from app.route_check import main as route_main
        route_main()
        return

    if "--console" in args:
        from app.console_run import main as console_main
        console_main()
        return

    from app.gui import main as gui_main
    gui_main()


if __name__ == "__main__":
    main()
