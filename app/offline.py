"""Chay hoan toan offline: doc model tu thu muc di kem, khong goi mang.

Binh thuong transformers / faster-whisper / speechbrain tai model ve cache chung
cua he thong (~/.cache/huggingface). Tren may KHONG CO INTERNET thi khong tai
duoc, va app se treo o buoc tai model roi bao loi kho hieu.

Module nay tro cache sang thu muc `models/hf` nam ngay canh app (duoc dong goi
san), va bat co HF_HUB_OFFLINE de thu vien bao loi ro rang thay vi cho mang
timeout.

Goi setup_offline() TRUOC khi import transformers/faster-whisper.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUNDLED_HF = ROOT / "models" / "hf"


def is_bundled() -> bool:
    """Co thu muc model di kem khong (tuc la ban dong goi offline)."""
    return BUNDLED_HF.is_dir() and any(BUNDLED_HF.iterdir())


def setup_offline(force_offline: bool | None = None) -> bool:
    """Tro cache HuggingFace sang thu muc di kem neu co.

    force_offline:
      None  - tu quyet: co thu muc di kem thi chay offline, khong thi de mac dinh
      True  - ep offline (bao loi ngay neu thieu model, khong cho mang)
      False - ep online (luon cho phep tai ve)

    Tra ve True neu dang o che do offline.
    """
    bundled = is_bundled()

    if bundled:
        # Phai dat TRUOC khi import transformers thi moi co tac dung
        os.environ["HF_HOME"] = str(BUNDLED_HF)
        os.environ["HUGGINGFACE_HUB_CACHE"] = str(BUNDLED_HF / "hub")
        os.environ["TRANSFORMERS_CACHE"] = str(BUNDLED_HF / "hub")

    offline = bundled if force_offline is None else force_offline
    if offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

    return offline


def describe() -> str:
    """Mo ta ngan gon dang lay model tu dau - de in ra cho nguoi dung biet."""
    if is_bundled():
        return f"Model di kem: {BUNDLED_HF}"
    default = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    return f"Model tu cache he thong: {default}"


def missing_models(cfg) -> list[str]:
    """Kiem tra cac model bat buoc da co san chua (quan trong khi khong co mang).

    Tra ve danh sach thu con thieu; rong nghia la du.
    """
    missing = []

    for label, path in (
        ("Giong doc tieng Viet", cfg.en2vi.tts_onnx),
        ("Giong doc tieng Anh", cfg.vi2en.tts_onnx),
    ):
        if not (ROOT / path).exists() and not Path(path).exists():
            missing.append(f"{label} ({path})")

    if is_bundled():
        hub = BUNDLED_HF / "hub"
        needed = {
            f"Whisper {cfg.stt.model_size}": f"models--Systran--faster-whisper-{cfg.stt.model_size}",
            "Model dich NLLB": "models--facebook--nllb-200-distilled-600M",
        }
        for label, folder in needed.items():
            if not (hub / folder).is_dir():
                missing.append(f"{label} ({folder})")

    return missing


# Ten thu muc cho tung model khi da xuat ra dang goi gon
BUNDLED_MODELS = ROOT / "models" / "bundled"


def local_model_path(name: str) -> str | None:
    """Duong dan model da xuat san di kem, hoac None neu khong co.

    Dong goi bang save_pretrained() ra thu muc rieng thay vi sao chep cache
    HuggingFace, vi cache giu ca `model.safetensors` LAN `pytorch_model.bin`
    cua cac ban khac nhau - NLLB-600M chiem 9.2GB trong cache trong khi ban
    than model chi 2.4GB. Xuat ra thu muc sach thi vua gon vua khong phu thuoc
    vao cach cache to chuc thu muc.
    """
    path = BUNDLED_MODELS / name
    return str(path) if path.is_dir() and any(path.iterdir()) else None
