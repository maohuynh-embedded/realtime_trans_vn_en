"""Tu do phan cung va chon cau hinh phu hop.

Phan cung tang toc do tung nen tang khai bao (windows/hardware.py,
macos/hardware.py); app/accel.py quyet dinh moi giai doan chay tren cai nao.
Cung mot bo ma vi vay chay toi uu tren:
  - Windows co GPU NVIDIA      -> CUDA float16, model lon
  - Windows chi co CPU          -> CPU int8, model nho
  - macOS Apple Silicon         -> GPU Apple (MLX), model lon
"""
import os
from dataclasses import dataclass, field

from app.accel import APPLE_GPU, CUDA, Accelerator, ExecutionPlan, choose_plan
from app.platform_impl import hardware as _platform


@dataclass
class HardwareProfile:
    has_cuda: bool
    gpu_name: str
    vram_gb: float
    cpu_threads: int

    # Cau hinh duoc de xuat theo phan cung
    stt_device: str
    stt_compute_type: str
    stt_model_size: str
    can_clone_voice: bool

    stt_backend: str = "faster-whisper"
    mt_device: str = "cpu"
    speaker_device: str = "cpu"
    ram_gb: float = 0.0
    accelerators: list[Accelerator] = field(default_factory=list)

    @property
    def has_gpu(self) -> bool:
        """Co GPU dung duoc cho STT (NVIDIA hoac Apple) - quyet dinh danh sach model to."""
        return self.stt_device in ("cuda", "gpu")

    def summary(self) -> str:
        gpu = f"{self.gpu_name} ({self.vram_gb:.0f}GB)" if self.gpu_name else "khong co GPU"
        return (f"{gpu}, {self.cpu_threads} luong CPU -> Whisper '{self.stt_model_size}' "
                f"[{self.stt_backend}] chay {self.stt_device} ({self.stt_compute_type})")


def detect() -> HardwareProfile:
    """Nhan dien phan cung hien tai va de xuat cau hinh."""
    cpu_threads = os.cpu_count() or 4
    accels = _platform.detect_accelerators()
    ram_gb = _platform.total_ram_gb()
    plan: ExecutionPlan = choose_plan(accels, ram_gb, cpu_threads)

    cuda = next((a for a in accels if a.kind == CUDA and a.usable), None)
    apple = next((a for a in accels if a.kind == APPLE_GPU and a.usable), None)
    gpu = cuda or apple
    return HardwareProfile(
        has_cuda=cuda is not None,
        gpu_name=gpu.name if gpu else "",
        vram_gb=gpu.memory_gb if gpu else 0.0,
        cpu_threads=cpu_threads,
        stt_device=plan.stt.device,
        stt_compute_type=plan.stt.compute_type,
        stt_model_size=plan.stt_model_size,
        can_clone_voice=plan.can_clone_voice,
        stt_backend=plan.stt.backend,
        mt_device=plan.mt_device,
        speaker_device=plan.speaker_device,
        ram_gb=ram_gb,
        accelerators=accels,
    )


def apply_to(cfg) -> HardwareProfile:
    """Ap cau hinh phan cung vao AppConfig."""
    hw = detect()
    cfg.stt.backend = hw.stt_backend
    cfg.stt.device = hw.stt_device
    cfg.stt.compute_type = hw.stt_compute_type
    cfg.stt.model_size = hw.stt_model_size
    return hw


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    hw = detect()
    print(hw.summary())
    for a in hw.accelerators:
        state = "san sang" if a.usable else f"chua dung ({a.note})"
        print(f"  - {a.kind}: {a.name} {a.memory_gb:.0f}GB [{state}]")
    print(f"  Clone giong duoc: {'CO' if hw.can_clone_voice else 'KHONG (can GPU >= 5GB VRAM)'}")
