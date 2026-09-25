"""Doc thanh tieng ANH bang GIONG CUA NGUOI NOI (sao chep giong) - Chatterbox tren MLX.

Dung cho chieu Viet -> Anh: lay vai giay tieng Viet cua chinh nguoi noi lam mau
(xem app/voice_bank.py), doc cau tieng Anh theo giong do. Do tren M2 Pro
(evals/spike_cloning.py): RTF ~0.85, do giong ECAPA ~0.57 so voi ~0.00 giua nguoi
khac, doc dung 100% - nhung CHI VUA du thoi gian thuc, nen pipeline phai co duong
lui ve Piper khi bi tut lai.

MLX gan luong tinh toan voi THREAD tao ra no (giong backend STT MLX), nen moi loi goi
model di qua MOT thread rieng. Dieu kien giong (Conditionals) duoc cache theo
(nguoi noi, phien ban mau): tinh mot lan roi dung lai cho moi cau.

Yeu cau: `pip install mlx-audio` (chi macOS/Apple Silicon).
"""
import re
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from app.resample import resample_audio

REPO = "mlx-community/chatterbox-multilingual-v3"
EXAGGERATION = 0.1     # nhu mac dinh cua mlx-audio: doc trung tinh, it "dien"
MAX_CHARS = 240        # cau dai hon thi tach ra doc tung doan (chat luong on dinh hon)


def split_text(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """Tach van ban thanh cac doan <= max_chars, uu tien cat o cuoi cau roi dau phay."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []
    pieces: list[str] = []
    for sent in re.split(r"(?<=[.!?])\s+", text):
        while len(sent) > max_chars:
            cut = max(sent.rfind(", ", 0, max_chars), sent.rfind(" ", 0, max_chars))
            cut = cut + 1 if cut > 0 else max_chars
            pieces.append(sent[:cut].strip())
            sent = sent[cut:].strip()
        if sent:
            pieces.append(sent)
    merged: list[str] = []
    for p in pieces:
        if merged and len(merged[-1]) + 1 + len(p) <= max_chars:
            merged[-1] = f"{merged[-1]} {p}"
        else:
            merged.append(p)
    return merged


class VoiceCloneTTS:
    def __init__(self, repo: str = REPO, lang_code: str = "en"):
        self._repo = repo
        self.lang_code = lang_code
        self.sample_rate = 24000
        self._conds: dict[tuple[str, int], object] = {}   # chi dung trong luong cua backend
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="clone-tts")
        self._pool.submit(self._load).result()

    # ---- chay trong luong rieng cua backend ----

    def _load(self) -> None:
        import mlx.core as mx
        from mlx_audio.tts import load
        self._mx = mx
        self._model = load(self._repo)
        self.sample_rate = int(self._model.sample_rate)

    def _conditionals(self, key: str, version: int, ref16: np.ndarray):
        ck = (key, version)
        conds = self._conds.get(ck)
        if conds is None:
            ref = resample_audio(ref16, 16000, self.sample_rate)
            conds = self._model.prepare_conditionals(
                self._mx.array(ref), self.sample_rate, EXAGGERATION)
            for old in [k for k in self._conds if k[0] == key]:   # chi giu ban moi nhat
                del self._conds[old]
            self._conds[ck] = conds
        return conds

    def _synthesize(self, text: str, ref16: np.ndarray, key: str, version: int):
        conds = self._conditionals(key, version, ref16)
        chunks: list[np.ndarray] = []
        for piece in split_text(text):
            for res in self._model.generate(
                text=piece, conds=conds, exaggeration=EXAGGERATION,
                lang_code=self.lang_code, verbose=False,
            ):
                chunks.append(np.array(res.audio, dtype=np.float32).reshape(-1))
        audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
        return (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16), self.sample_rate

    # ---- API cong khai (goi tu bat ky luong nao) ----

    def synthesize(self, text: str, ref16: np.ndarray, key: str, version: int):
        """Doc `text` bang giong trong `ref16` (float32 mono 16kHz). Tra ve (pcm_int16, sample_rate)."""
        if not text.strip():
            return np.zeros(0, dtype=np.int16), self.sample_rate
        return self._pool.submit(self._synthesize, text, ref16, key, version).result()

    def warmup(self, ref16: np.ndarray) -> None:
        """Bien dich kernel / nap bo nho truoc cau that dau tien (lan goi dau rat cham)."""
        self._pool.submit(self._synthesize, "Hello, this is a short test.", ref16, "_warmup", 0).result()
        self._pool.submit(self._conds.clear).result()
