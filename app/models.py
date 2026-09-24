"""ModelHub: giu tat ca model va cho 2 chieu dung chung.

Whisper duoc load DUY NHAT 1 lan (ngon ngu truyen vao tung lan goi), con MT va
TTS thi moi chieu mot bo. Nho vay bat them chieu thu hai chi ton them ~400MB
thay vi gap doi toan bo.
"""
from pathlib import Path

from app.config import AppConfig, DirectionConfig
from app.mt import Translator
from app.stt import SpeechToText
from app.tts import TextToSpeech


class ModelHub:
    def __init__(self, cfg: AppConfig, status_cb=None):
        self.cfg = cfg
        self._status_cb = status_cb or (lambda _msg: None)
        self.stt: SpeechToText | None = None
        self._translators: dict[str, Translator] = {}
        self._tts: dict[str, TextToSpeech] = {}

    def _status(self, msg: str) -> None:
        self._status_cb(msg)

    def ensure_stt(self) -> SpeechToText:
        if self.stt is None:
            self._status(f"Dang tai model STT ({self.cfg.stt.backend}, {self.cfg.stt.model_size})...")
            self.stt = SpeechToText(self.cfg.stt)
        return self.stt

    @staticmethod
    def _resolve_mt_langs(direction: DirectionConfig) -> tuple[str, str]:
        tgt = direction.tgt_language
        src = direction.stt_language
        if src == "auto":
            # Che do tu nhan dien: dung cap pho bien nhat lam mac dinh, moi cau
            # se tu lay translator dung theo ngon ngu doan duoc.
            src = "en" if tgt == "vi" else "vi"
        return src, tgt

    def ensure_translator_for(self, direction: DirectionConfig) -> Translator:
        """Lay translator cho 1 chieu, KHONG dong cham gi den TTS.

        Dung khi khong can doc thanh tieng (mac dinh cua app: nguoi dung doc
        duoc ca 2 thu tieng nen chi can phu de) - tranh nap Piper vo ich, ton
        RAM/VRAM va thoi gian khoi dong ma khong ai dung toi.
        """
        src, tgt = self._resolve_mt_langs(direction)
        return self.ensure_translator(src, tgt)

    def ensure_tts(self, direction: DirectionConfig) -> TextToSpeech:
        """Lay (hoac nap moi) giong doc Piper cho 1 chieu. Nap THAT SU, khong tre hoan."""
        tts_key = direction.tts_onnx
        if tts_key not in self._tts:
            self._status(f"Dang tai giong doc {Path(tts_key).stem}...")
            self._tts[tts_key] = TextToSpeech(
                direction.tts_onnx, direction.tts_json, direction.tts_length_scale
            )
        return self._tts[tts_key]

    def ensure_direction(self, direction: DirectionConfig) -> tuple[Translator, TextToSpeech]:
        """Load model MT + TTS cho 1 chieu, roi tra ve ca hai.

        Cache danh dau theo CAP NGON NGU va TEP GIONG, khong phai theo
        direction.key. Ly do: ca ba che do nghe (Anh->Viet, Viet->Anh, tu nhan
        dien) deu dung chung key "en2vi", nen neu danh dau theo key thi doi che
        do se lay nham model cua che do truoc - dich sai ngon ngu va doc sai
        giong, ma khong bao loi gi.

        Nap CA TTS du direction.speak co tat hay khong - dung khi can san sang
        doc bat cu luc nao (vd. cong cu chan doan). DirectionPipeline khong dung
        ham nay de khoi dong nua, no goi rieng ensure_translator_for() + tai TTS
        tre hoan trong ensure_tts() de tranh nap Piper khi khong can.
        """
        translator = self.ensure_translator_for(direction)
        return translator, self.ensure_tts(direction)

    def reset_stt(self) -> None:
        """Bo model Whisper dang giu (de load lai voi co khac).

        Chi bo Whisper, GIU nguyen cac model dich va giong doc - chung khong lien
        quan gi den co Whisper nen khong co ly do tai lai.
        """
        self.stt = None

    def warm_up(self, direction: DirectionConfig) -> None:
        """Chay thu 1 lan qua cac model dang THAT SU dung cho 1 chieu.

        Lan goi dau tien cua moi model cham hon han cac lan sau (vd. Piper: RTF 0.67
        lan dau vs 0.04 cac lan sau), nen "dot nong" truoc de cau dau tien khong bi
        tre bat thuong. CHI dot nong TTS neu direction.speak dang bat - neu khong
        se vo tinh nap Piper cho mot chieu khong bao gio dung toi no.
        """
        import numpy as np

        stt = self.ensure_stt()
        translator = self.ensure_translator_for(direction)
        self._status(f"Dang lam nong {direction.label}...")
        try:
            silence = np.zeros(self.cfg.audio.target_sample_rate // 2, dtype=np.int16).tobytes()
            warm_lang = direction.stt_language
            if warm_lang == "auto":
                warm_lang = "en" if direction.tgt_language == "vi" else "vi"
            stt.transcribe_pcm16(silence, warm_lang, self.cfg.audio.target_sample_rate)
            if direction.speak:
                warm_text = "xin chào" if warm_lang == "vi" else "hello"
                self.ensure_tts(direction).synthesize(translator.translate(warm_text))
        except Exception:
            pass  # warm-up that bai khong phai loi nghiem trong, van chay duoc

    def ensure_translator(self, src_lang: str, tgt_lang: str) -> Translator:
        """Lay (hoac tao) translator cho mot cap ngon ngu bat ky.

        Che do tu nhan dien can cai nay: khong biet truoc cau tiep theo la tieng
        gi nen khong the buoc translator vao mot DirectionConfig co dinh.
        """
        key = f"{src_lang}2{tgt_lang}"
        if key not in self._translators:
            self._status(f"Dang tai model dich {src_lang} -> {tgt_lang}...")
            self._translators[key] = Translator(src_lang=src_lang, tgt_lang=tgt_lang)
        return self._translators[key]
