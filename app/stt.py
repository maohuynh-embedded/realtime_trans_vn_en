"""Buoc [3] Speech-to-Text.

Mot instance dung chung cho ca 2 chieu - ngon ngu truyen vao tung lan goi,
tiet kiem RAM va thoi gian load so voi load 2 model rieng.

Viec chay model nam trong backend cam duoc (app/stt_backends/): faster-whisper
(CUDA/CPU) hoac MLX (GPU Apple). Lop nay lo phan DUNG CHUNG: bo loc ao giac,
chuan hoa am thanh, doan ngon ngu trong tap ung vien.
"""
import numpy as np

from app.config import SttConfig
from app.hallucination import is_too_quiet, should_reject
from app.stt_backends import create_backend


class SpeechToText:
    def __init__(self, cfg: SttConfig):
        self.backend = create_backend(cfg)
        # Backend co the tu lui (vd. CUDA hong -> CPU): phan anh cau hinh THUC.
        from dataclasses import replace
        self.cfg = replace(cfg, device=self.backend.device, compute_type=self.backend.compute_type)
        # Bien dich kernel / nap bo nho ngay bay gio, khong doi toi cau that dau tien.
        try:
            self.backend.warmup()
        except Exception:
            pass

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
        # Lop 1: qua nho thi khong chay model luon - vua nhanh vua tranh bia chu
        too_quiet, rms = is_too_quiet(pcm16_bytes)
        if too_quiet:
            if reject_cb:
                reject_cb(f"qua nho (RMS={rms:.4f})")
            return ""

        audio_f32 = np.frombuffer(pcm16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        raw = self.backend.transcribe(audio_f32, language, self.cfg.initial_prompt or None)

        if raw.empty:
            if reject_cb:
                reject_cb("khong co doan nao")
            return ""

        # Lop 2-4
        reject, reason = should_reject(raw.text, raw.no_speech_prob, raw.avg_logprob)
        if reject:
            if reject_cb:
                reject_cb(f"{reason}: {raw.text[:40]!r}")
            return ""

        return raw.text

    def detect_language(self, pcm16_bytes: bytes, candidates=("en", "vi")) -> tuple[str, float]:
        """Doan ngon ngu cua MOT cau, gioi han trong `candidates`.

        Vi sao gioi han: de Whisper tu do trong 99 ngon ngu thi tieng Viet hay bi
        nham sang tieng Trung/Thai, con tieng Anh giong Viet hay bi nham sang cac
        thu tieng khac. Biet truoc cuoc noi chuyen chi co Anh + Viet thi chi can
        so xac suat giua hai cai do -> on dinh hon han.
        """
        audio = np.frombuffer(pcm16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        scores = self.backend.detect_language(audio)
        best = max(candidates, key=lambda c: scores.get(c, 0.0))
        return best, float(scores.get(best, 0.0))

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
