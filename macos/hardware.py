"""Khai bao phan cung tang toc tren macOS: GPU Apple (Metal) va Neural Engine (ANE)."""
import platform
import subprocess

from app.accel import APPLE_ANE, APPLE_GPU, Accelerator


def _sysctl(name: str) -> str:
    try:
        return subprocess.run(["sysctl", "-n", name], capture_output=True, text=True,
                              timeout=5).stdout.strip()
    except Exception:
        return ""


def total_ram_gb() -> float:
    mem = _sysctl("hw.memsize")
    return int(mem) / 1024 ** 3 if mem.isdigit() else 0.0


def detect_accelerators() -> list[Accelerator]:
    if platform.machine() != "arm64":
        return []   # Mac Intel: chi CPU

    chip = _sysctl("machdep.cpu.brand_string") or "Apple Silicon"
    ram = total_ram_gb()   # bo nho hop nhat: CPU, GPU, ANE dung chung mot vung

    try:
        import mlx.core  # noqa: F401
        import mlx_whisper  # noqa: F401
        gpu_ok, gpu_note = True, ""
    except Exception as exc:
        gpu_ok, gpu_note = False, f"chua cai mlx-whisper ({type(exc).__name__})"

    return [
        Accelerator(APPLE_GPU, chip, ram, usable=gpu_ok, note=gpu_note),
        # Neural Engine chi truy cap duoc qua Core ML. Chua co backend Core ML
        # trong app nen chua dung (usable=False) - xem docs, muc ANE.
        Accelerator(APPLE_ANE, chip, ram, usable=False, note="chua co backend Core ML"),
    ]
