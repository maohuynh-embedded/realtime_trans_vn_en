"""Cai dat tu dong tren may moi.

Chay bang Python he thong (KHONG phai python trong .venv):

    python setup_env.py

Script tu lam het:
  1. Kiem tra phien ban Python
  2. Tao virtualenv .venv
  3. Cai cac goi trong requirements.txt
  4. Do phan cung -> neu co GPU NVIDIA thi cai ban torch CUDA + thu vien cuDNN/cuBLAS
  5. Tai 2 giong doc Piper (tieng Viet + tieng Anh)
  6. Tai truoc cac model con lai (Whisper, NLLB, ECAPA) neu chay voi --full
  7. Chay tu kiem tra va bao ket qua

Tuy chon:
  --full      tai truoc TAT CA model ngay (lau hon, nhung sau do chay duoc offline)
  --cpu       ep dung ban CPU du may co GPU NVIDIA
  --skip-test bo qua buoc tu kiem tra cuoi cung
"""
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
PIPER_DIR = ROOT / "models" / "piper"

# (duong dan tren Hugging Face, ten tep luu ve)
PIPER_VOICES = [
    "vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium.onnx",
    "vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium.onnx.json",
    "en/en_US/lessac/medium/en_US-lessac-medium.onnx",
    "en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
]

TORCH_CUDA_INDEX = "https://download.pytorch.org/whl/cu126"

_step = 0


def step(title: str) -> None:
    global _step
    _step += 1
    print(f"\n{'=' * 68}\n  BUOC {_step}: {title}\n{'=' * 68}")


def fail(msg: str) -> None:
    print(f"\n!! THAT BAI: {msg}")
    sys.exit(1)


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(cmd: list, desc: str, check: bool = True) -> bool:
    """Chay lenh, hien output truc tiep de nguoi dung thay tien trinh."""
    print(f"  $ {' '.join(str(c) for c in cmd[:6])}{' ...' if len(cmd) > 6 else ''}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        if check:
            fail(f"{desc} (ma loi {result.returncode})")
        print(f"  ! Bo qua: {desc} khong thanh cong")
        return False
    return True


def has_nvidia_gpu() -> tuple[bool, str]:
    """Do GPU bang nvidia-smi - khong can torch (luc nay torch chua cai)."""
    if not shutil.which("nvidia-smi"):
        return False, ""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=30,
        )
        if out.returncode == 0 and out.stdout.strip():
            return True, out.stdout.strip().splitlines()[0]
    except Exception:
        pass
    return False, ""


# ---------------------------------------------------------------- các bước

def check_python() -> None:
    step("Kiem tra Python")
    v = sys.version_info
    print(f"  Python {v.major}.{v.minor}.{v.micro} ({platform.machine()})")
    if v < (3, 10):
        fail("Can Python 3.10 tro len.")
    if v >= (3, 13):
        print("  ! Canh bao: Python 3.13+ chua duoc thu ky, mot so goi co the thieu wheel.")
    if platform.system() != "Windows":
        print("  ! Canh bao: app dung WASAPI loopback nen chi chay day du tren Windows.")


def make_venv() -> None:
    step("Tao virtualenv")
    if venv_python().exists():
        print(f"  Da co san: {VENV}")
        return
    run([sys.executable, "-m", "venv", str(VENV)], "tao virtualenv")
    print(f"  Da tao: {VENV}")


def install_requirements() -> None:
    step("Cai cac goi Python")
    py = venv_python()
    run([str(py), "-m", "pip", "install", "--upgrade", "pip", "-q"], "nang cap pip", check=False)
    req = ROOT / "requirements.txt"
    if not req.exists():
        fail(f"Khong tim thay {req}")
    run([str(py), "-m", "pip", "install", "-r", str(req)], "cai requirements.txt")


def install_gpu(force_cpu: bool) -> bool:
    step("Do phan cung va cai tang toc GPU")
    if force_cpu:
        print("  Da chon --cpu, bo qua phan GPU.")
        return False

    found, name = has_nvidia_gpu()
    if not found:
        print("  Khong thay GPU NVIDIA -> dung CPU.")
        print("  (May co GPU tich hop Intel co the dung OpenVINO, xem HUONG_DAN_XAY_DUNG.md muc 3.3b)")
        return False

    print(f"  Tim thay: {name}")
    print("  Dang cai ban torch CUDA (vai tram MB, hoi lau)...")
    py = venv_python()
    # --force-reinstall la BAT BUOC: neu khong, pip thay da co torch ban CPU va
    # bao "Requirement already satisfied", giu nguyen ban CPU - loi de mac.
    ok = run(
        [str(py), "-m", "pip", "install", "torch",
         "--index-url", TORCH_CUDA_INDEX, "--force-reinstall", "--no-cache-dir"],
        "cai torch CUDA", check=False,
    )
    if not ok:
        print("  ! Cai torch CUDA that bai -> app se tu lui ve CPU khi chay.")
        return False

    # cuDNN/cuBLAS cho faster-whisper chay tren GPU
    run([str(py), "-m", "pip", "install", "nvidia-cublas-cu12", "nvidia-cudnn-cu12", "-q"],
        "cai thu vien CUDA", check=False)
    return True


def download_piper() -> None:
    step("Tai giong doc Piper")
    PIPER_DIR.mkdir(parents=True, exist_ok=True)

    missing = [v for v in PIPER_VOICES if not (PIPER_DIR / Path(v).name).exists()]
    if not missing:
        print(f"  Da co du {len(PIPER_VOICES)} tep giong doc.")
        return

    print(f"  Can tai {len(missing)} tep (~120MB)...")
    code = (
        "import shutil, sys\n"
        "from pathlib import Path\n"
        "from huggingface_hub import hf_hub_download\n"
        f"dst = Path(r'{PIPER_DIR}')\n"
        f"files = {missing!r}\n"
        "for f in files:\n"
        "    p = hf_hub_download('rhasspy/piper-voices', f)\n"
        "    shutil.copy(p, dst / Path(f).name)\n"
        "    print('   tai xong:', Path(f).name)\n"
    )
    run([str(venv_python()), "-c", code], "tai giong Piper")


def prefetch_models(full: bool) -> None:
    step("Tai truoc cac model con lai")
    if not full:
        print("  Bo qua (cac model se tu tai khi chay lan dau).")
        print("  Muon tai ngay de sau do chay offline: python setup_env.py --full")
        return

    print("  Dang tai Whisper + NLLB + ECAPA (vai GB, rat lau)...")
    code = (
        "import sys\n"
        "sys.path.insert(0, r'%s')\n"
        "from app.config import default_config\n"
        "from app.models import ModelHub\n"
        "cfg = default_config()\n"
        "print('   Whisper:', cfg.stt.model_size, cfg.stt.device)\n"
        "hub = ModelHub(cfg, status_cb=lambda m: print('   ', m))\n"
        "hub.ensure_stt()\n"
        "hub.ensure_direction(cfg.en2vi)\n"
        "hub.ensure_direction(cfg.vi2en)\n"
        "from app.speaker import SpeakerTracker\n"
        "t = SpeakerTracker()\n"
        "print('   ECAPA:', 'OK' if t.using_ecapa else 'khong tai duoc')\n"
    ) % ROOT
    run([str(venv_python()), "-c", code], "tai truoc model", check=False)


def run_selftest(skip: bool) -> None:
    step("Tu kiem tra")
    if skip:
        print("  Bo qua (--skip-test).")
        return
    print("  Chay main.py --test ...\n")
    subprocess.run([str(venv_python()), str(ROOT / "main.py"), "--test"])


def final_notes(gpu: bool) -> None:
    py = venv_python()
    print(f"\n{'=' * 68}\n  XONG\n{'=' * 68}")
    print("\nChay app:")
    print(f"  {py} main.py                     # giao dien day du")
    print(f"  {py} main.py --watch --speak     # dich nhanh video dang xem")
    print(f"  {py} main.py --test              # tu kiem tra lai bat cu luc nao")

    print("\nCon lai can lam bang tay (chi khi can):")
    print("  - Muon DOI TAC nghe duoc tieng Anh (chieu Viet->Anh):")
    print("      Win+R > mmsys.cpl > tab Recording > chuot phai > Show Disabled Devices")
    print("      > chuot phai 'Stereo Mix' > Enable, roi dat mic trong Zoom = Stereo Mix.")
    print(f"      Kiem tra: {py} main.py --check-route")
    if not gpu:
        print("  - May khong co GPU NVIDIA: app chay CPU, se cham hon nhung van dung duoc.")
        print("    Neu co GPU tich hop Intel, xem muc 3.3b trong HUONG_DAN_XAY_DUNG.md.")


def main() -> None:
    args = sys.argv[1:]
    print("#" * 68)
    print("#  CAI DAT APP PHIEN DICH CUOC HOP")
    print("#" * 68)

    check_python()
    make_venv()
    install_requirements()
    gpu = install_gpu(force_cpu="--cpu" in args)
    download_piper()
    prefetch_models(full="--full" in args)
    run_selftest(skip="--skip-test" in args)
    final_notes(gpu)


if __name__ == "__main__":
    main()
