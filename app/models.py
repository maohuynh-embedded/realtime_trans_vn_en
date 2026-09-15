"""ModelHub: giu tat ca model va cho 2 chieu dung chung.

Whisper duoc load DUY NHAT 1 lan (ngon ngu truyen vao tung lan goi), con MT va
TTS thi moi chieu mot bo. Nho vay bat them chieu thu hai chi ton them ~400MB
thay vi gap doi toan bo.
"""
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
            self._status("Dang tai model STT (faster-whisper)...")
            self.stt = SpeechToText(self.cfg.stt)
        return self.stt

    def ensure_direction(self, direction: DirectionConfig) -> tuple[Translator, TextToSpeech]:
        """Load (neu chua co) model MT + TTS cho 1 chieu, roi tra ve."""
        if direction.key not in self._translators:
            self._status(f"Dang tai model dich {direction.label}...")
            self._translators[direction.key] = Translator(
                src_lang=direction.stt_language,
                tgt_lang=direction.tgt_language,
                backend=direction.mt_backend,
                model_name=direction.mt_model,
            )

        if direction.key not in self._tts:
            self._status(f"Dang tai giong doc {direction.label}...")
            self._tts[direction.key] = TextToSpeech(
                direction.tts_onnx, direction.tts_json, direction.tts_length_scale
            )

        return self._translators[direction.key], self._tts[direction.key]

    def warm_up(self, direction: DirectionConfig) -> None:
        """Chay thu 1 lan qua ca 3 model cua 1 chieu.

        Lan goi dau tien cua moi model cham hon han cac lan sau (vd. Piper: RTF 0.67
        lan dau vs 0.04 cac lan sau), nen "dot nong" truoc de cau dau tien khong bi
        tre bat thuong.
        """
        import numpy as np

        stt = self.ensure_stt()
        translator, tts = self.ensure_direction(direction)
        self._status(f"Dang lam nong {direction.label}...")
        try:
            silence = np.zeros(self.cfg.audio.target_sample_rate // 2, dtype=np.int16).tobytes()
            stt.transcribe_pcm16(silence, direction.stt_language, self.cfg.audio.target_sample_rate)
            warm_text = "xin chào" if direction.stt_language == "vi" else "hello"
            tts.synthesize(translator.translate(warm_text))
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
