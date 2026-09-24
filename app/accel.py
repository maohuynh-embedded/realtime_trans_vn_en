"""Mo hinh 'bo tang toc' (accelerator) va chinh sach chon backend theo phan cung.

Moi nen tang (windows/hardware.py, macos/hardware.py) chi KHAI BAO phan cung no
co: danh sach Accelerator. File nay - dung chung - quyet dinh moi giai doan cua
pipeline (STT, dich, nhan dien nguoi noi) chay tren bo tang toc nao.

Vi sao chon theo TUNG GIAI DOAN thay vi mot thiet bi cho ca app: pipeline co 3
thread (VAD / STT / MT+TTS) chay song song, nen tan dung nhieu bo tang toc
KHAC NHAU cung luc se giam tranh chap tai nguyen (vd. STT tren GPU trong khi
dich tren CPU/NPU).

Bo tang toc         Windows                    macOS (Apple Silicon)
------------------  -------------------------  ---------------------------------
GPU                 CUDA (NVIDIA)              GPU Apple (Metal, qua MLX)
NPU                 (Intel NPU - de sau)       Neural Engine (Core ML - de sau)
CPU                 int8                       int8 (Accelerate/NEON)

Uu tien hien tai: macOS. Windows giu nguyen hanh vi cu (CUDA hoac CPU).
"""
import os
from dataclasses import dataclass, field

CUDA = "cuda"
APPLE_GPU = "apple-gpu"
APPLE_ANE = "apple-ane"
CPU = "cpu"

# Ten backend STT (xem app/stt_backends/)
BACKEND_FASTER_WHISPER = "faster-whisper"
BACKEND_MLX = "mlx"


@dataclass(frozen=True)
class Accelerator:
    kind: str
    name: str = ""
    memory_gb: float = 0.0      # VRAM (CUDA) hoac bo nho hop nhat (Apple)
    usable: bool = True         # backend cho no da cai va san sang chay
    note: str = ""              # ly do khi usable=False, hoac ghi chu


@dataclass(frozen=True)
class StagePlan:
    backend: str
    device: str
    compute_type: str = ""
    reason: str = ""


@dataclass(frozen=True)
class ExecutionPlan:
    stt: StagePlan
    stt_model_size: str
    mt_device: str              # "cuda" | "cpu"
    speaker_device: str         # "cuda:0" | "cpu"
    can_clone_voice: bool = False


def _find(accels: list[Accelerator], kind: str) -> Accelerator | None:
    return next((a for a in accels if a.kind == kind and a.usable), None)


def choose_plan(accels: list[Accelerator], ram_gb: float, cpu_threads: int) -> ExecutionPlan:
    """Chon backend + model cho tung giai doan. Ap dung theo thu tu uu tien.

    Bien moi truong ghi de (de thu nghiem, khong can sua code):
      RT_STT_BACKEND = faster-whisper | mlx
    """
    forced = os.environ.get("RT_STT_BACKEND", "").strip().lower()
    cuda = _find(accels, CUDA)
    apple = _find(accels, APPLE_GPU)

    # ---- STT ----
    if forced == BACKEND_MLX or (not forced and apple):
        # Do tren M2 Pro (macos/bench/bench_engine.py): turbo ~0.6s/cau 5s va dich tieng Viet
        # dung hon medium (~0.55s); small ~0.2s nhung sai dau tieng Viet nhieu hon.
        size = "large-v3-turbo" if ram_gb >= 16 else "small" if ram_gb >= 8 else "base"
        stt = StagePlan(BACKEND_MLX, "gpu", "float16", "GPU Apple (Metal/MLX)")
    elif forced == BACKEND_FASTER_WHISPER or cuda or not forced:
        if cuda:
            vram = cuda.memory_gb
            size = "large-v3" if vram >= 9 else "medium" if vram >= 5 else "small"
            stt = StagePlan(BACKEND_FASTER_WHISPER, "cuda", "float16", f"GPU NVIDIA {cuda.name}")
        else:
            size = "small" if cpu_threads >= 8 else "base"
            stt = StagePlan(BACKEND_FASTER_WHISPER, "cpu", "int8", "CPU int8")
    else:
        raise ValueError(f"RT_STT_BACKEND khong hop le: {forced!r}")

    return ExecutionPlan(
        stt=stt,
        stt_model_size=size,
        mt_device="cuda" if cuda else "cpu",
        speaker_device="cuda:0" if cuda else "cpu",
        can_clone_voice=bool(cuda and cuda.memory_gb >= 5),   # XTTS can ~4GB VRAM
    )
