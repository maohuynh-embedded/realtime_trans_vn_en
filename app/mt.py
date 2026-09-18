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

TOI UU TAI (do thuc te, khong doan):
  Backend "nllb" mac dinh chay qua transformers (fp32/fp16), chiem ~2.4GB VRAM
  tren GPU va la mot trong hai model nang nhat cua pipeline (cung Whisper) -
  nguyen nhan chinh gay "model chay lam lag may" tren GPU 6GB dung chung voi
  cac app khac. Da convert NLLB-600M sang CTranslate2 int8_float16 (backend
  "nllb-ct2") va do lai tren dung bo cau nay:

      VRAM  : 2437 MB -> 667 MB   (giam 73%)
      Toc do:  587 ms -> 582 ms/cau (khong doi)
      Nap   :  9.6s   -> 6.4s

  Neu co san model da convert trong models/bundled/nllb-600m-ct2/, Translator
  se TU DONG dung backend nay khi goi backend="nllb" - khong can doi cau hinh
  o dau khac. Neu chua convert (may khac, hoac chua chay setup_env.py --full)
  thi tu lui ve ban transformers nhu cu, van chay dung, chi nang hon.
"""
import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

from app.glossary import protect_terms, restore_terms

# Ma ngon ngu cua NLLB
_NLLB_LANG = {"en": "eng_Latn", "vi": "vie_Latn"}

# Model MarianMT tuong ung tung chieu
_MARIAN_MODEL = {
    ("en", "vi"): "Helsinki-NLP/opus-mt-en-vi",
    ("vi", "en"): "Helsinki-NLP/opus-mt-vi-en",
}

NLLB_DEFAULT = "facebook/nllb-200-distilled-600M"
NLLB_LARGE = "facebook/nllb-200-distilled-1.3B"   # tot hon nua, can GPU

_GEN_KWARGS = {
    "max_new_tokens": 256,
    # Chan hien tuong lap vo han kieu "phong phong phong phong..."
    "no_repeat_ngram_size": 4,
    "repetition_penalty": 1.15,
    "num_beams": 1,          # greedy cho nhanh; tang len neu can chinh xac hon
}


class _Ct2NllbTranslator:
    """NLLB-600M chay qua CTranslate2 int8_float16 - nhe VRAM hon ~3.6 lan.

    Cung giao dien .translate(text) nhu Translator (transformers) de dung thay
    the duoc cho nhau, khong phai sua noi goi.
    """

    def __init__(self, model_dir: str, src_lang: str, tgt_lang: str, device: str):
        import ctranslate2
        from transformers import AutoTokenizer as _Tok

        self.src_tag = _NLLB_LANG[src_lang]
        self.tgt_tag = _NLLB_LANG[tgt_lang]
        # CTranslate2 dung "cuda"/"cpu" (khong can chi so nhu "cuda:0")
        ct2_device = "cuda" if device.startswith("cuda") else "cpu"
        self.model = ctranslate2.Translator(model_dir, device=ct2_device, compute_type="int8_float16"
                                            if ct2_device == "cuda" else "int8")
        self.tokenizer = _Tok.from_pretrained(model_dir, src_lang=self.src_tag)

    def translate(self, text: str) -> str:
        if not text.strip():
            return ""
        tokens = self.tokenizer.convert_ids_to_tokens(self.tokenizer.encode(text))
        results = self.model.translate_batch(
            [tokens],
            target_prefix=[[self.tgt_tag]],
            max_decoding_length=_GEN_KWARGS["max_new_tokens"],
            no_repeat_ngram_size=_GEN_KWARGS["no_repeat_ngram_size"],
            repetition_penalty=_GEN_KWARGS["repetition_penalty"],
        )
        out_tokens = results[0].hypotheses[0][1:]   # bo token ngon ngu dich o dau
        text_out = self.tokenizer.decode(self.tokenizer.convert_tokens_to_ids(out_tokens))
        for prefix in ("vi: ", "en: "):
            if text_out.startswith(prefix):
                text_out = text_out[len(prefix):]
        return text_out.strip()


class Translator:
    """Dich 1 chieu (src_lang -> tgt_lang).

    backend="nllb" tu dong chon giua ban CTranslate2 (neu co san, nhe VRAM hon
    nhieu) va ban transformers goc (luon co san, tai tu Hugging Face khi can).
    """

    def __init__(self, src_lang: str, tgt_lang: str, backend: str = "nllb",
                 model_name: str | None = None, device: str | None = None):
        self.src_lang = src_lang
        self.tgt_lang = tgt_lang
        self.backend = backend
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._ct2: "_Ct2NllbTranslator | None" = None

        if backend == "nllb" and model_name is None:
            ct2_dir = self._resolve_nllb_ct2()
            if ct2_dir is not None:
                self._ct2 = _Ct2NllbTranslator(ct2_dir, src_lang, tgt_lang, self.device)
                self.model_name = ct2_dir
                self.model = None
                self.tokenizer = self._ct2.tokenizer
                self._forced_bos = None
                return

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
        """Dung ban transformers da xuat san di kem neu co, khong thi tai tu Hugging Face."""
        from app.offline import local_model_path
        return local_model_path("nllb-600m") or NLLB_DEFAULT

    @staticmethod
    def _resolve_nllb_ct2() -> str | None:
        """Dung ban CTranslate2 (nhe VRAM hon) neu da convert san, khong thi None."""
        from app.offline import local_model_path
        return local_model_path("nllb-600m-ct2")

    @torch.inference_mode()
    def translate(self, text: str) -> str:
        """Bao ve thuat ngu chuyen nganh (glossary) TRUOC khi goi model, phuc
        hoi lai SAU khi dich xong - ap dung chung cho ca 2 backend (CTranslate2
        va transformers) o day, tranh trung lap logic. Xem app/glossary.py de
        biet ly do va cac loi thuc te da do duoc (vd. NLLB dich "I2C bus"
        thanh "xe buyt I2C", "ground plane" thanh "may bay mat dat").
        """
        protected, restore = protect_terms(text)
        result = self._translate_raw(protected)
        return restore_terms(result, restore)

    def _translate_raw(self, text: str) -> str:
        if self._ct2 is not None:
            return self._ct2.translate(text)

        if not text.strip():
            return ""

        batch = self.tokenizer([text], return_tensors="pt", padding=True, truncation=True,
                               max_length=512).to(self.device)
        gen_kwargs = dict(_GEN_KWARGS)
        if self._forced_bos is not None:
            gen_kwargs["forced_bos_token_id"] = self._forced_bos

        generated = self.model.generate(**batch, **gen_kwargs)
        out = self.tokenizer.decode(generated[0], skip_special_tokens=True)
        # envit5/nllb doi khi kem tien to ngon ngu
        for prefix in ("vi: ", "en: "):
            if out.startswith(prefix):
                out = out[len(prefix):]
        return out.strip()
