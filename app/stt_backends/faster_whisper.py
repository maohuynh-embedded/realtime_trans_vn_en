"""Backend faster-whisper (CTranslate2): CUDA float16 hoac CPU int8."""
import numpy as np
from faster_whisper import WhisperModel

from app.config import SttConfig
from app.stt_backends.base import RawTranscript


class FasterWhisperBackend:
    name = "faster-whisper"

    def __init__(self, cfg: SttConfig, model_ref: str):
        from app.platform_impl import runtime
        self.device, self.compute_type = cfg.device, cfg.compute_type
        self._cfg = cfg
        if cfg.device == "cuda":
            runtime.ensure_cuda_dlls()
        try:
            self.model = WhisperModel(model_ref, device=cfg.device, compute_type=cfg.compute_type)
        except Exception:
            if cfg.device != "cuda":
                raise
            # GPU khong dung duoc (thieu driver/DLL) -> lui ve CPU thay vi chet han
            self.device, self.compute_type = "cpu", "int8"
            self.model = WhisperModel(model_ref, device="cpu", compute_type="int8")

    def transcribe(self, audio_f32: np.ndarray, language: str,
                   initial_prompt: str | None) -> RawTranscript:
        segments, _info = self.model.transcribe(
            audio_f32,
            language=language,
            beam_size=self._cfg.beam_size,
            vad_filter=self._cfg.vad_filter,
            # Khong cho Whisper nhin cau truoc: neu no da bia 1 lan, dieu kien hoa
            # theo van ban truoc se khien no lap lai cai bia do mai.
            condition_on_previous_text=False,
            initial_prompt=initial_prompt,
        )
        segs = list(segments)
        if not segs:
            return RawTranscript("", 0.0, 0.0, empty=True)
        return RawTranscript(
            text=" ".join(s.text.strip() for s in segs).strip(),
            avg_logprob=float(np.mean([s.avg_logprob for s in segs])),
            no_speech_prob=float(np.mean([s.no_speech_prob for s in segs])),
        )

    def detect_language(self, audio_f32: np.ndarray) -> dict[str, float]:
        _lang, _prob, all_probs = self.model.detect_language(audio_f32)
        return dict(all_probs)

    def warmup(self) -> None:
        self.transcribe(np.zeros(8000, dtype=np.float32), "en", None)
