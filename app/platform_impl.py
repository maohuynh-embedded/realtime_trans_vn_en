"""Chon cai dat dung theo he dieu hanh: windows/ hoac macos/.

Loi app (app/) KHONG import truc tiep windows/ hay macos/ - chi di qua day.
Moi goi nen tang phai cung cap cung mot bo module:

  audio    - dò loopback, bat am thanh he thong, luat loc thiet bi
             (xem windows/audio.py va macos/audio.py: hai file dinh nghia cung giao dien)
  levels   - do muc tin hieu / tu tim nguon dang phat tieng
  runtime  - chuan bi moi truong chay model (vd. nap DLL CUDA tren Windows)
  hardware - khai bao bo tang toc co san (GPU/NPU) cho app/accel.py
"""
import importlib
import sys

if sys.platform == "win32":
    PLATFORM = "windows"
elif sys.platform == "darwin":
    PLATFORM = "macos"
else:
    raise RuntimeError(
        f"He dieu hanh '{sys.platform}' chua duoc ho tro (chi co Windows va macOS)."
    )

audio = importlib.import_module(f"{PLATFORM}.audio")
levels = importlib.import_module(f"{PLATFORM}.levels")
runtime = importlib.import_module(f"{PLATFORM}.runtime")
hardware = importlib.import_module(f"{PLATFORM}.hardware")
