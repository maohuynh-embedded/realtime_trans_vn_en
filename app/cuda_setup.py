"""Nap DLL CUDA (cuBLAS/cuDNN) cai qua pip vao duong dan tim thu vien cua Windows.

faster-whisper (CTranslate2) can cuBLAS + cuDNN de chay tren GPU. Khi cai bang pip
(`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`) cac DLL nam trong site-packages/nvidia/*/bin
chu khong nam trong PATH he thong, nen CTranslate2 khong tim thay va bao loi kho hieu.

Goi ensure_cuda_dlls() TRUOC khi tao WhisperModel(device="cuda").
Tren may khong co GPU thi ham nay khong lam gi ca, khong gay loi.
"""
import os
import sys
from pathlib import Path

_done = False


def ensure_cuda_dlls() -> bool:
    """Tra ve True neu da nap duoc (hoac khong can nap)."""
    global _done
    if _done:
        return True
    if sys.platform != "win32":
        _done = True
        return True

    try:
        import nvidia
    except ImportError:
        return False

    # nvidia la namespace package -> co the khong co __file__, phai duyet __path__
    roots = []
    if getattr(nvidia, "__file__", None):
        roots.append(Path(nvidia.__file__).parent)
    roots.extend(Path(p) for p in getattr(nvidia, "__path__", []))

    added = 0
    for root in roots:
        for bin_dir in root.glob("*/bin"):
            if bin_dir.is_dir():
                try:
                    os.add_dll_directory(str(bin_dir))
                    os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
                    added += 1
                except (OSError, FileNotFoundError):
                    pass

    _done = added > 0
    return _done
