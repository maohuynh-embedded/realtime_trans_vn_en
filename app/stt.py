"""Buoc [3] Speech-to-Text bang faster-whisper (CTranslate2, CPU int8).

Mot instance dung chung cho ca 2 chieu - ngon ngu truyen vao tung lan goi,
tiet kiem RAM va thoi gian load so voi load 2 model rieng.
"""
from dataclasses import replace

import numpy as np
from faster_whisper import WhisperModel

from app.config import SttConfig
from app.cuda_setup import ensure_cuda_dlls
from app.hallucination import is_too_quiet, should_reject


class SpeechToText:
    def __init__(self, cfg: SttConfig):
        self.cfg = cfg
        if cfg.device == "cuda":
            ensure_cuda_dlls()
        try:
            self.model = WhisperModel(
                cfg.model_size,
                device=cfg.device,
                compute_type=cfg.compute_type,
            )
        except Exception:
            if cfg.device != "cuda":
                raise
            # GPU khong dung duoc (thieu driver/DLL) -> lui ve CPU thay vi chet han
            self.cfg = replace(cfg, device="cpu", compute_type="int8")
            self.model = WhisperModel(
                self.cfg.model_size,
                device="cpu",
                compute_type="int8",
            )

    def transcribe_pcm16(
        self,
        pcm16_bytes: bytes,
        language: str,
        sample_rate: int = 16000,
        reject_cb=None,
    ) -> str:
        """Nhan PCM16 mono bytes (dau ra cua VAD), tra ve text o ngon ngu `language`.

        Co dinh `language` (khong de Whisper tu doan) de giam tre va tang do chinh xac.

        Tra ve CHUOI RONG neu doan audio khong co tieng noi that. Khi gap im lang,
        Whisper khong tra ve rong ma BIA ra cau quen thuoc tu du lieu huan luyen
        ("Thanks for watching!", "you", ...) - xem app/hallucination.py. `reject_cb`
        neu co se duoc goi voi ly do loai bo, tien cho viec chan doan.
        """
        # Lop 1: qua nho thi khong chay Whisper luon - vua nhanh vua tranh bia chu
        too_quiet, rms = is_too_quiet(pcm16_bytes)
        if too_quiet:
            if reject_cb:
                reject_cb(f"qua nho (RMS={rms:.4f})")
            return ""

        audio_f32 = np.frombuffer(pcm16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _info = self.model.transcribe(
            audio_f32,
            language=language,
            beam_size=self.cfg.beam_size,
            vad_filter=self.cfg.vad_filter,
            # Khong cho Whisper nhin cau truoc: neu no da bia 1 lan, dieu kien hoa
            # theo van ban truoc se khien no lap lai cai bia do mai.
            condition_on_previous_text=False,
        )

        segs = list(segments)
        if not segs:
            if reject_cb:
                reject_cb("khong co doan nao")
            return ""

        text = " ".join(seg.text.strip() for seg in segs).strip()
        avg_logprob = float(np.mean([s.avg_logprob for s in segs]))
        no_speech = float(np.mean([s.no_speech_prob for s in segs]))

        # Lop 2-4
        reject, reason = should_reject(text, no_speech, avg_logprob)
        if reject:
            if reject_cb:
                reject_cb(f"{reason}: {text[:40]!r}")
            return ""

        return text

    def detect_language(self, pcm16_bytes: bytes, candidates=("en", "vi")) -> tuple[str, float]:
        """Doan ngon ngu cua MOT cau, gioi han trong `candidates`.

        Vi sao gioi han: de Whisper tu do trong 99 ngon ngu thi tieng Viet hay bi
        nham sang tieng Trung/Thai, con tieng Anh giong Viet hay bi nham sang cac
        thu tieng khac. Biet truoc cuoc noi chuyen chi co Anh + Viet thi chi can
        so xac suat giua hai cai do -> on dinh hon han.
        """
        audio = np.frombuffer(pcm16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        lang, prob, all_probs = self.model.detect_language(audio)

        scores = dict(all_probs)
        best = max(candidates, key=lambda c: scores.get(c, 0.0))
        return best, float(scores.get(best, prob if best == lang else 0.0))

    def transcribe_auto(
        self,
        pcm16_bytes: bytes,
        candidates=("en", "vi"),
        sample_rate: int = 16000,
        reject_cb=None,
    ) -> tuple[str, str]:
        """Tu doan ngon ngu roi phien am. Tra ve (van_ban, ngon_ngu_doan_duoc).

        Dung cho cuoc noi chuyen NOI LAN nhieu thu tieng (vd. choi game voi ban,
        cau tieng Viet xen cau tieng Anh). Ep mot ngon ngu co dinh cho ca phien
        thi kieu gi cung sai mot nua.
        """
        too_quiet, rms = is_too_quiet(pcm16_bytes)
        if too_quiet:
            if reject_cb:
                reject_cb(f"qua nho (RMS={rms:.4f})")
            return "", ""

        try:
            lang, _prob = self.detect_language(pcm16_bytes, candidates)
        except Exception:
            lang = candidates[0]

        text = self.transcribe_pcm16(pcm16_bytes, lang, sample_rate, reject_cb=reject_cb)
        return text, lang
