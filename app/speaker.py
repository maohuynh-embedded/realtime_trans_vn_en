"""Nhan dien NGUOI NOI va GIOI TINH cho tung cau.

Muc dich: trong cuoc phong van / cuoc hop, phan biet duoc ai dang hoi va ai dang
tra loi, kem nam/nu -> ban doc phu de biet ngay dong nao la cua ai.

Hai viec doc lap:

1) GIOI TINH - uoc luong tu cao do giong noi (F0).
   Giong nam thuong 85-180 Hz, giong nu 165-255 Hz. Dung thuat toan tu tuong quan
   (autocorrelation) tren cac doan CO tieng noi, lay trung vi de bo nhieu.
   Khong can model, chay tuc thi.

2) NGUOI NOI - gom cum truc tuyen (online clustering) theo dac trung giong.
   Moi cau duoc rut ra mot "dau van tay giong noi", so voi cac nguoi da gap:
   giong nhau thi gan cung nhan, khac han thi tao nguoi moi.
   Dung dac trung nhe (thong ke MFCC + F0) thay vi model nhung mang nhu pyannote,
   de khong lam tang do tre cua pipeline.
"""
from dataclasses import dataclass

import numpy as np

# Nguong phan biet nam/nu theo F0 trung vi (Hz).
# Khoang 165-180 la vung chong lan, nen tra ve "?" cho trung thuc.
_F0_MALE_MAX = 155.0
_F0_FEMALE_MIN = 190.0

_F0_MIN, _F0_MAX = 70.0, 350.0   # khoang F0 hop ly cua giong nguoi


@dataclass
class SpeakerInfo:
    speaker_id: int           # 1, 2, 3... theo thu tu xuat hien
    gender: str               # "nam" | "nu" | "?"
    f0_median: float          # cao do trung vi (Hz), 0 neu khong do duoc

    @property
    def label(self) -> str:
        """Nhan hien thi, vd. 'Nguoi 1 (nam)'."""
        g = f" ({self.gender})" if self.gender != "?" else ""
        return f"Nguoi {self.speaker_id}{g}"


def _frame_f0(frame: np.ndarray, sample_rate: int) -> float:
    """Uoc luong F0 cua 1 khung bang tu tuong quan. Tra ve 0 neu khong tin cay."""
    frame = frame - frame.mean()
    energy = float(np.sqrt(np.mean(frame ** 2)))
    if energy < 0.005:
        return 0.0   # qua nho, coi nhu im lang

    corr = np.correlate(frame, frame, mode="full")[len(frame) - 1:]
    if corr[0] <= 0:
        return 0.0
    corr = corr / corr[0]

    min_lag = int(sample_rate / _F0_MAX)
    max_lag = int(sample_rate / _F0_MIN)
    if max_lag >= len(corr):
        return 0.0

    segment = corr[min_lag:max_lag]
    if segment.size == 0:
        return 0.0
    peak_idx = int(np.argmax(segment))
    peak_val = float(segment[peak_idx])
    if peak_val < 0.3:
        return 0.0   # khong tuan hoan ro -> khong phai nguyen am huu thanh

    return sample_rate / (min_lag + peak_idx)


def estimate_f0(pcm16_bytes: bytes, sample_rate: int = 16000) -> float:
    """F0 trung vi cua ca cau (Hz). 0 neu khong do duoc."""
    audio = np.frombuffer(pcm16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    if audio.size < sample_rate // 10:
        return 0.0

    win = int(sample_rate * 0.04)    # khung 40ms
    hop = int(sample_rate * 0.02)
    values = []
    for start in range(0, len(audio) - win, hop):
        f0 = _frame_f0(audio[start:start + win], sample_rate)
        if f0 > 0:
            values.append(f0)

    if len(values) < 5:
        return 0.0
    return float(np.median(values))


def guess_gender(f0_median: float) -> str:
    if f0_median <= 0:
        return "?"
    if f0_median < _F0_MALE_MAX:
        return "nam"
    if f0_median > _F0_FEMALE_MIN:
        return "nu"
    return "?"


class _EcapaEmbedder:
    """Dac trung giong noi bang ECAPA-TDNN (speechbrain/spkrec-ecapa-voxceleb).

    Da thu tu che dac trung pho + F0 nhung KHONG DU chinh xac: no gop ca giong nam
    96Hz voi giong nu 195Hz vao cung mot nguoi. ECAPA la model chuyen cho viec nay
    (huan luyen tren VoxCeleb), chi ~80MB va chay rat nhanh, nen dung han no.
    """

    _instance = None

    def __init__(self):
        import torch
        from speechbrain.inference.speaker import EncoderClassifier
        from speechbrain.utils.fetching import LocalStrategy

        self.torch = torch
        # speechbrain can dang "cuda:0", khong nhan "cuda" tran
        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.model = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="models/ecapa",
            run_opts={"device": self.device},
            # Windows khong tao duoc symlink neu khong bat Developer Mode ->
            # speechbrain canh bao va co the that bai. COPY thi luon chay duoc.
            local_strategy=LocalStrategy.COPY,
        )

    @classmethod
    def get(cls):
        """Tai model 1 lan duy nhat. Tra ve None neu khong dung duoc."""
        if cls._instance is None:
            try:
                cls._instance = cls()
            except Exception:
                cls._instance = False
        return cls._instance or None

    def embed(self, pcm16_bytes: bytes, sample_rate: int) -> np.ndarray:
        audio = np.frombuffer(pcm16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        wav = self.torch.from_numpy(audio).unsqueeze(0).to(self.device)
        with self.torch.no_grad():
            emb = self.model.encode_batch(wav).squeeze().cpu().numpy()
        return emb.astype(np.float32)


def _voice_fingerprint(pcm16_bytes: bytes, sample_rate: int, f0: float) -> np.ndarray:
    """Dac trung du phong khi khong tai duoc ECAPA (pho + F0).

    Kem chinh xac hon han ECAPA - chi dung khi may khong tai duoc model.
    """
    audio = np.frombuffer(pcm16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    if audio.size < 512:
        return np.zeros(21, dtype=np.float32)

    # Pho cong suat trung binh tren cac khung
    win = 1024
    hop = 512
    spec_sum = np.zeros(win // 2 + 1)
    n = 0
    window = np.hanning(win)
    for start in range(0, len(audio) - win, hop):
        seg = audio[start:start + win] * window
        spec_sum += np.abs(np.fft.rfft(seg)) ** 2
        n += 1
    if n == 0:
        return np.zeros(21, dtype=np.float32)
    spec = spec_sum / n

    # Gop thanh 20 bang theo thang log tan so
    freqs = np.fft.rfftfreq(win, 1 / sample_rate)
    edges = np.logspace(np.log10(80), np.log10(min(7000, sample_rate / 2)), 21)
    bands = []
    for i in range(20):
        mask = (freqs >= edges[i]) & (freqs < edges[i + 1])
        bands.append(spec[mask].mean() if mask.any() else 0.0)

    bands = np.log(np.array(bands) + 1e-10)
    bands = (bands - bands.mean()) / (bands.std() + 1e-6)   # chuan hoa, bot anh huong am luong

    # F0 chuan hoa la chieu thu 21 - rat co ich de tach nam/nu
    f0_norm = (f0 - 150.0) / 100.0 if f0 > 0 else 0.0
    return np.append(bands, f0_norm * 2.0).astype(np.float32)   # nhan 2 de F0 co trong so cao hon


class SpeakerTracker:
    """Gom cum truc tuyen: moi cau -> gan vao nguoi da biet, hoac tao nguoi moi."""

    def __init__(self, threshold: float | None = None, max_speakers: int = 8):
        self._embedder = _EcapaEmbedder.get()
        # Nguong khac nhau cho 2 loai dac trung: ECAPA tach bach hon nhieu
        if threshold is None:
            threshold = 0.45 if self._embedder else 0.12
        self.threshold = threshold      # khoang cach cosine toi da de coi la cung nguoi
        self.max_speakers = max_speakers

        self._centroids: list[np.ndarray] = []
        self._counts: list[int] = []
        self._f0_sums: list[float] = []
        self._f0_counts: list[int] = []

    @property
    def using_ecapa(self) -> bool:
        return self._embedder is not None

    def identify(self, pcm16_bytes: bytes, sample_rate: int = 16000) -> SpeakerInfo:
        f0 = estimate_f0(pcm16_bytes, sample_rate)
        if self._embedder is not None:
            try:
                fp = self._embedder.embed(pcm16_bytes, sample_rate)
            except Exception:
                fp = _voice_fingerprint(pcm16_bytes, sample_rate, f0)
        else:
            fp = _voice_fingerprint(pcm16_bytes, sample_rate, f0)

        if not np.any(fp):
            return SpeakerInfo(speaker_id=1, gender=guess_gender(f0), f0_median=f0)

        idx = self._match(fp)
        if idx is None:
            if len(self._centroids) < self.max_speakers:
                self._centroids.append(fp.copy())
                self._counts.append(1)
                self._f0_sums.append(f0 if f0 > 0 else 0.0)
                self._f0_counts.append(1 if f0 > 0 else 0)
                idx = len(self._centroids) - 1
            else:
                idx = self._nearest(fp)[0]
                self._update(idx, fp, f0)
        else:
            self._update(idx, fp, f0)

        # Gioi tinh quyet dinh theo F0 TRUNG BINH cua nguoi do (on dinh hon 1 cau le)
        avg_f0 = (self._f0_sums[idx] / self._f0_counts[idx]) if self._f0_counts[idx] else f0
        return SpeakerInfo(speaker_id=idx + 1, gender=guess_gender(avg_f0), f0_median=avg_f0)

    # ---- noi bo ----

    def _nearest(self, fp: np.ndarray) -> tuple[int, float]:
        best_idx, best_dist = 0, float("inf")
        for i, c in enumerate(self._centroids):
            denom = (np.linalg.norm(fp) * np.linalg.norm(c)) + 1e-9
            dist = 1.0 - float(np.dot(fp, c) / denom)
            if dist < best_dist:
                best_idx, best_dist = i, dist
        return best_idx, best_dist

    def _match(self, fp: np.ndarray) -> int | None:
        if not self._centroids:
            return None
        idx, dist = self._nearest(fp)
        return idx if dist <= self.threshold else None

    def _update(self, idx: int, fp: np.ndarray, f0: float) -> None:
        n = self._counts[idx]
        self._centroids[idx] = (self._centroids[idx] * n + fp) / (n + 1)
        self._counts[idx] = n + 1
        if f0 > 0:
            self._f0_sums[idx] += f0
            self._f0_counts[idx] += 1

    def reset(self) -> None:
        self._centroids.clear()
        self._counts.clear()
        self._f0_sums.clear()
        self._f0_counts.clear()
