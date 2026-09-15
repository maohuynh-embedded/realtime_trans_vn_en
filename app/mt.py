"""Buoc [4] Machine Translation.

Ho tro 2 backend, chon theo cau hinh:

  - "nllb"   : facebook/nllb-200-distilled-600M  (MAC DINH - chinh xac hon nhieu)
  - "marian" : Helsinki-NLP/opus-mt-*            (nhe hon, cho may yeu)

Vi sao doi tu MarianMT sang NLLB (do thuc te tren bo cau hop cong viec):

  | Cau goc                  | MarianMT              | NLLB-600M            |
  |--------------------------|-----------------------|----------------------|
  | quarterly results        | ket qua PHAN TRAM  X  | ket qua quy       V  |
  | revenue numbers for Q3   | SO NHAN voi Q3     X  | doanh thu quy 3   V  |
  | the integration          | su lien ket        X  | viec tich hop     V  |
  | dependency issue         | (mat nghia)        X  | van de phu thuoc  V  |

MarianMT con hay bi lap vo han ("phong phong phong phong...") - da chan bang
no_repeat_ngram_size + repetition_penalty ap cho ca 2 backend.

Khong dung argos-translate: goi en_vi da bi go bo (muc 3.4 HUONG_DAN_XAY_DUNG.md).
"""
import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

# Ma ngon ngu cua NLLB
_NLLB_LANG = {"en": "eng_Latn", "vi": "vie_Latn"}

# Model MarianMT tuong ung tung chieu
_MARIAN_MODEL = {
    ("en", "vi"): "Helsinki-NLP/opus-mt-en-vi",
    ("vi", "en"): "Helsinki-NLP/opus-mt-vi-en",
}

NLLB_DEFAULT = "facebook/nllb-200-distilled-600M"
NLLB_LARGE = "facebook/nllb-200-distilled-1.3B"   # tot hon nua, can GPU


class Translator:
    """Dich 1 chieu (src_lang -> tgt_lang)."""

    def __init__(self, src_lang: str, tgt_lang: str, backend: str = "nllb",
                 model_name: str | None = None, device: str | None = None):
        self.src_lang = src_lang
        self.tgt_lang = tgt_lang
        self.backend = backend
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        if backend == "nllb":
            self.model_name = model_name or self._resolve_nllb()
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name, src_lang=_NLLB_LANG[src_lang])
            self._forced_bos = self.tokenizer.convert_tokens_to_ids(_NLLB_LANG[tgt_lang])
        else:
            self.model_name = model_name or _MARIAN_MODEL[(src_lang, tgt_lang)]
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self._forced_bos = None

        self.model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name).to(self.device)
        self.model.eval()

    @staticmethod
    def _resolve_nllb() -> str:
        """Dung ban da xuat san di kem neu co, khong thi tai tu Hugging Face."""
        from app.offline import local_model_path
        return local_model_path("nllb-600m") or NLLB_DEFAULT

    @torch.inference_mode()
    def translate(self, text: str) -> str:
        if not text.strip():
            return ""

        batch = self.tokenizer([text], return_tensors="pt", padding=True, truncation=True,
                               max_length=512).to(self.device)
        gen_kwargs = {
            "max_new_tokens": 256,
            # Chan hien tuong lap vo han kieu "phong phong phong phong..."
            "no_repeat_ngram_size": 4,
            "repetition_penalty": 1.15,
            "num_beams": 1,          # greedy cho nhanh; tang len neu can chinh xac hon
        }
        if self._forced_bos is not None:
            gen_kwargs["forced_bos_token_id"] = self._forced_bos

        generated = self.model.generate(**batch, **gen_kwargs)
        out = self.tokenizer.decode(generated[0], skip_special_tokens=True)
        # envit5/nllb doi khi kem tien to ngon ngu
        for prefix in ("vi: ", "en: "):
            if out.startswith(prefix):
                out = out[len(prefix):]
        return out.strip()
