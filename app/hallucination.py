"""Loc "ao giac" cua Whisper - khi gap im lang thi no BIA ra chu thay vi tra ve rong.

Trieu chung dien hinh (da gap that):
    Thanks for watching!
    Thanks for watching!
    you
    Thanks for watching!
    ...lap di lap lai

Nguyen nhan: Whisper duoc huan luyen tren rat nhieu phu de YouTube, nen khi dau
vao khong co tieng noi ro rang, no sinh ra cau pho bien nhat trong du lieu huan
luyen. Day la loi da biet cua Whisper, khong phai loi cau hinh.

Bon lop loc, di tu re den dat:
  1. Cong nang luong  - doan qua nho thi khong dua vao Whisper luon.
  2. no_speech_prob   - chinh Whisper tu bao "cho nay khong co tieng noi".
  3. avg_logprob      - do tu tin; qua thap nghia la dang doan mo.
  4. Danh sach den    - cac cau bia dac trung, chan thang.
"""
import re
import unicodedata

import numpy as np

# HAI TANG danh sach den - phan biet "chac chan la rac" voi "co the that".
#
# Bai hoc: ban dau gop chung mot danh sach thi "Yes." bi chan nham. Trong phong
# van/hop, "Yes", "No", "Thank you" la cau tra loi THAT va rat pho bien. Chung chi
# la rac khi Whisper dong thoi bao do tu tin thap.

# Tang A: gan nhu khong bao gio la loi noi that trong cuoc hop -> chan thang.
_ALWAYS_REJECT = {
    "thanks for watching",
    "thank you for watching",
    "thanks for watching everyone",
    "thanks for watching and see you next time",
    "subscribe",
    "please subscribe",
    "like and subscribe",
    "dont forget to subscribe",
    "see you in the next video",
    "see you next time",
    "music",
    "outro music",
    "applause",
    "silence",
    "cam on cac ban da xem",
    "cam on ban da xem",
    "dang ky kenh",
}

# Tang B: CO THE la loi noi that -> chi chan khi Whisper cung khong tu tin.
_SUSPICIOUS = {
    "you",
    "thank you",
    "thanks",
    "bye",
    "goodbye",
    "the end",
    "hen gap lai",
}

# Nguong long hon danh cho tang B
_SUSPICIOUS_NO_SPEECH = 0.30
_SUSPICIOUS_LOGPROB = -0.60

# Ky tu nhac - Whisper danh dau doan nhac, gan nhu luon la rac voi ta
_MUSIC_CHARS = ("♪", "♫", "♬", "♩")

# Nguong mac dinh
NO_SPEECH_MAX = 0.60      # tren nguong nay -> Whisper tu cho la khong co tieng noi
AVG_LOGPROB_MIN = -0.90   # duoi nguong nay -> dang doan mo
RMS_MIN = 0.006           # duoi nguong nay -> gan nhu im lang


def _strip_diacritics(text: str) -> str:
    """Bo dau tieng Viet: 'cam on cac ban da xem' khop voi 'cam on cac ban da xem'.

    Danh sach den viet khong dau, con Whisper tra ve co dau - neu khong bo dau
    truoc khi so thi cac muc tieng Viet trong danh sach KHONG BAO GIO khop.
    """
    decomposed = unicodedata.normalize("NFD", text)
    without_marks = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return without_marks.replace("đ", "d").replace("Đ", "D")


def _normalize(text: str) -> str:
    """Bo dau cau, bo dau tieng Viet, chuyen chu thuong - de so voi danh sach den."""
    text = _strip_diacritics(text.lower().strip())
    text = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def is_too_quiet(pcm16_bytes: bytes, rms_min: float = RMS_MIN) -> tuple[bool, float]:
    """Lop 1: doan co qua nho de chua tieng noi that khong."""
    audio = np.frombuffer(pcm16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    if audio.size == 0:
        return True, 0.0
    rms = float(np.sqrt(np.mean(audio ** 2)))
    return rms < rms_min, rms


def is_blacklisted(text: str, no_speech_prob: float = 0.0, avg_logprob: float = 0.0) -> bool:
    """Tang A chan thang; tang B va cau sieu ngan chi chan khi do tu tin thap."""
    if any(ch in text for ch in _MUSIC_CHARS):
        return True

    norm = _normalize(text)
    if not norm:
        return True

    if norm in _ALWAYS_REJECT:
        return True

    low_confidence = (
        (no_speech_prob == no_speech_prob and no_speech_prob > _SUSPICIOUS_NO_SPEECH)
        or (avg_logprob == avg_logprob and avg_logprob < _SUSPICIOUS_LOGPROB)
    )

    if norm in _SUSPICIOUS:
        return low_confidence

    # Cau sieu ngan ("yes", "no", "ok"): giu neu Whisper nghe chac chan
    if len(norm.split()) <= 1 and len(norm) <= 4:
        return low_confidence

    return False


def is_repetitive(text: str, min_repeats: int = 3) -> bool:
    """Bat truong hop mot cum tu lap lien tiep nhieu lan trong CUNG mot cau."""
    words = _normalize(text).split()
    if len(words) < min_repeats * 2:
        return False
    for size in (1, 2, 3):
        for start in range(len(words) - size * min_repeats + 1):
            block = words[start:start + size]
            repeats = 1
            pos = start + size
            while pos + size <= len(words) and words[pos:pos + size] == block:
                repeats += 1
                pos += size
            if repeats >= min_repeats:
                return True
    return False


def should_reject(
    text: str,
    no_speech_prob: float,
    avg_logprob: float,
    no_speech_max: float = NO_SPEECH_MAX,
    avg_logprob_min: float = AVG_LOGPROB_MIN,
) -> tuple[bool, str]:
    """Tong hop cac lop 2-4. Tra ve (co_loai_bo, ly_do)."""
    if not text.strip():
        return True, "rong"

    if is_blacklisted(text, no_speech_prob, avg_logprob):
        return True, "cau bia dac trung"

    if is_repetitive(text):
        return True, "lap cum tu"

    # no_speech_prob cua Whisper KHONG dang tin khi dung mot minh: cau that van
    # hay bi cham diem cao (da gap: mot cau tieng Viet ro rang bi cham 0.73 va
    # loai nham). Chi loai khi CA HAI dau hieu cung xau.
    bad_no_speech = no_speech_prob == no_speech_prob and no_speech_prob > no_speech_max
    bad_logprob = avg_logprob == avg_logprob and avg_logprob < avg_logprob_min

    if bad_no_speech and bad_logprob:
        return True, f"no_speech={no_speech_prob:.2f} va logprob={avg_logprob:.2f}"

    # Do tu tin cuc thap thi mot minh no cung du de ket luan dang doan mo
    if avg_logprob == avg_logprob and avg_logprob < avg_logprob_min - 0.4:
        return True, f"avg_logprob={avg_logprob:.2f} (rat thap)"

    return False, ""
