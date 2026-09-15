"""Tu do phan cung va chon cau hinh phu hop.

App duoc dung tren 2 may khac han nhau:
  - May nha : i5-13400F + RTX 2060 6GB + 32GB RAM  -> chay GPU, model to, co the clone giong.
  - May cty : i7-1270P, khong GPU roi, khong quyen admin -> chay CPU, model nho.

Thay vi sua config moi lan doi may, module nay tu nhan dien roi chon giup.
"""
from dataclasses import dataclass


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

    def summary(self) -> str:
        if self.has_cuda:
            return (f"GPU {self.gpu_name} ({self.vram_gb:.0f}GB) -> Whisper '{self.stt_model_size}' "
                    f"chay GPU ({self.stt_compute_type})")
        return (f"Khong co GPU, {self.cpu_threads} luong CPU -> Whisper '{self.stt_model_size}' "
                f"chay CPU ({self.stt_compute_type})")


def detect() -> HardwareProfile:
    """Nhan dien phan cung hien tai va de xuat cau hinh."""
    import os

    cpu_threads = os.cpu_count() or 4
    has_cuda, gpu_name, vram_gb = False, "", 0.0

    try:
        import torch
        if torch.cuda.is_available():
            has_cuda = True
            gpu_name = torch.cuda.get_device_name(0)
            vram_gb = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
    except Exception:
        pass

    if has_cuda:
        # GPU: float16 nhanh hon nhieu va VRAM du. Chon co model theo VRAM.
        if vram_gb >= 9:
            model = "large-v3"
        elif vram_gb >= 5:
            model = "medium"      # RTX 2060 6GB thoai mai voi medium
        else:
            model = "small"
        return HardwareProfile(
            has_cuda=True, gpu_name=gpu_name, vram_gb=vram_gb, cpu_threads=cpu_threads,
            stt_device="cuda", stt_compute_type="float16", stt_model_size=model,
            can_clone_voice=vram_gb >= 5,   # XTTS can ~4GB VRAM
        )

    # CPU-only (may cong ty): int8 de giam tre, model nho
    model = "small" if cpu_threads >= 8 else "base"
    return HardwareProfile(
        has_cuda=False, gpu_name="", vram_gb=0.0, cpu_threads=cpu_threads,
        stt_device="cpu", stt_compute_type="int8", stt_model_size=model,
        can_clone_voice=False,   # clone giong tren CPU qua cham, khong dung real-time duoc
    )


def apply_to(cfg) -> HardwareProfile:
    """Ap cau hinh phan cung vao AppConfig."""
    hw = detect()
    cfg.stt.device = hw.stt_device
    cfg.stt.compute_type = hw.stt_compute_type
    cfg.stt.model_size = hw.stt_model_size
    return hw


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    hw = detect()
    print(hw.summary())
    print(f"  Clone giong duoc: {'CO' if hw.can_clone_voice else 'KHONG (can GPU >= 5GB VRAM)'}")
