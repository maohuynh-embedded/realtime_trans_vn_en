"""Khai bao phan cung tang toc tren Windows: GPU NVIDIA (CUDA). Intel NPU: de sau."""
from app.accel import CUDA, Accelerator


def detect_accelerators() -> list[Accelerator]:
    accels: list[Accelerator] = []

    try:
        import torch
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            accels.append(Accelerator(
                CUDA, torch.cuda.get_device_name(0), props.total_memory / 1024 ** 3))
    except Exception:
        pass

    return accels


def total_ram_gb() -> float:
    try:
        import ctypes

        class _MemStatus(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]

        st = _MemStatus()
        st.dwLength = ctypes.sizeof(st)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
        return st.ullTotalPhys / 1024 ** 3
    except Exception:
        return 0.0
