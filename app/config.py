"""Cau hinh trung tam cho toan bo pipeline.

App ho tro 2 CHIEU doc lap, co the bat/tat rieng:
  - EN->VI: bat am thanh cuoc hop (WASAPI loopback) -> ban nghe tieng Viet.
  - VI->EN: bat MIC cua ban -> doi tac nghe tieng Anh.
"""
from dataclasses import dataclass, field


@dataclass
class AudioConfig:
    # Dinh dang chuan ma VAD/Whisper can
    target_sample_rate: int = 16000
    target_channels: int = 1
    # webrtcvad chi nhan frame 10/20/30ms -> chon 30ms cho on dinh
    vad_frame_ms: int = 30

    # Nguong bat dau / ket thuc cau (mo ta trong HUONG_DAN_XAY_DUNG.md muc 3.2)
    start_ring_ms: int = 300       # ring buffer khi "chua bat dau cau"
    start_trigger_ratio: float = 0.6  # ty le frame co tieng noi de coi la bat dau

    end_ring_ms: int = 700
    """Bao lau im lang thi coi la HET CAU.

    Danh doi truc tiep giua do tre va do vun:
      - Qua ngan (450ms): cat nham vao cho ngap ngung giua cau -> ra cac manh vun
        kieu "Do you have" / "I also" / "Maybe I can tra-", dich thanh vo nghia.
      - Qua dai (>1s): cau tron ven hon nhung phai cho lau hon moi co ban dich.
    700ms: khoang nghi giua 2 cau thuong >700ms, con ngap ngung giua cau thuong
    200-500ms, nen tach duoc kha sach.
    """
    end_trigger_ratio: float = 0.6    # ty le frame im lang de coi la ket thuc

    max_segment_s: float = 8.0     # nguong cat cuong buc, tranh do tre don qua lon
    vad_aggressiveness: int = 2    # 0..3, cao hon = loc tap am manh hon


@dataclass
class SttConfig:
    """Dung chung cho ca 2 chieu - chi load 1 model Whisper duy nhat.

    Ngon ngu KHONG nam o day ma nam trong DirectionConfig, vi moi chieu
    nghe mot thu tieng khac nhau.
    """
    backend: str = "faster-whisper"  # "faster-whisper" (CUDA/CPU) | "mlx" (GPU Apple) - xem app/accel.py
    model_size: str = "small"      # "base" neu can nhanh hon, "medium" neu can chinh xac hon
    device: str = "cpu"
    compute_type: str = "int8"
    beam_size: int = 1
    vad_filter: bool = False       # da tu cat cau o buoc VAD rieng

    initial_prompt: str = ""
    """Goi y ngu canh cho Whisper - ten rieng, thuat ngu, cach viet uu tien.

    Whisper uu tien nghe ra dung cac tu trong prompt thay vi doan ra tu gan
    giong nhat. Cong cu manh nhat de xu ly giong noi co accent nang (vd. giong
    Anh kieu Nhat: "desk" nghe thanh "desuku", "strike" thanh "sutoraiku") - vi
    prompt neo Whisper ve dung tu tieng Anh du am thanh bi bien dang nhieu.

    Vi du: "Meeting about Q3 revenue, project Phoenix, with Tanaka-san and
    Suzuki-san from Yamamoto Corp." - liet ke ten nguoi, ten cong ty, thuat
    ngu du kien se xuat hien trong cuoc hop/video sap nghe.

    De trong = khong dung prompt (mac dinh, tuong thich nguoc). Chinh trong
    GUI truoc khi Bat, hoac sua truc tiep o day cho phien lam viec co dinh.
    """


@dataclass
class DirectionConfig:
    """Mo ta mot chieu dich hoan chinh."""
    key: str                # "en2vi" | "vi2en"
    label: str              # ten hien thi tren GUI
    source: str             # "loopback" (am thanh cuoc hop) | "mic" (giong cua ban)
    stt_language: str       # ngon ngu NGUON ma Whisper se nghe
    tgt_language: str       # ngon ngu DICH RA
    mt_backend: str = "nllb"        # "nllb" (chinh xac hon) | "marian" (nhe hon)
    mt_model: str | None = None     # de None = dung model mac dinh cua backend
    tts_onnx: str = ""      # giong Piper cho ngon ngu DICH
    tts_json: str = ""
    tts_length_scale: float = 1.0   # >1 = doc cham hon, <1 = doc nhanh hon
    enabled: bool = True
    speak: bool = True
    """Co doc ban dich thanh tieng khong.

    Tat di (chi hien text tren GUI) rat huu ich cho chieu Anh->Viet khi may khong
    du thiet bi phat rieng biet: ban nghe truc tiep giong goc cua doi tac va doc
    ban dich tren man hinh, nho vay tranh duoc vong lap 'ban dich bi loopback bat
    lai roi dich tiep'. Xem muc 'Dinh tuyen am thanh' trong README.
    """


def en_to_vi_direction() -> DirectionConfig:
    """Doi tac noi tieng Anh -> ban nghe tieng Viet qua tai nghe."""
    return DirectionConfig(
        key="en2vi",
        label="Anh -> Viet (nghe doi tac)",
        source="loopback",
        stt_language="en",
        tgt_language="vi",
        tts_onnx="models/piper/vi_VN-vais1000-medium.onnx",
        tts_json="models/piper/vi_VN-vais1000-medium.onnx.json",
    )


def vi_to_en_direction() -> DirectionConfig:
    """Ban noi tieng Viet -> doi tac nghe tieng Anh.

    Luu y: output cua chieu nay phai duoc dinh tuyen vao app hop lam MIC
    (xem README muc 'Dua tieng Anh vao Zoom/Teams'), khong phai phat ra tai nghe cua ban.
    """
    return DirectionConfig(
        key="vi2en",
        label="Viet -> Anh (doi tac nghe)",
        source="mic",
        stt_language="vi",
        tgt_language="en",
        tts_onnx="models/piper/en_US-lessac-medium.onnx",
        tts_json="models/piper/en_US-lessac-medium.onnx.json",
        enabled=False,   # mac dinh TAT, bat bang nut tren GUI khi can noi
    )


def listen_vi_to_en_direction() -> DirectionConfig:
    """Nghe am thanh may phat ra la TIENG VIET -> dich sang tieng Anh.

    Khac vi_to_en_direction() o cho NGUON la loopback chu khong phai mic: dung khi
    nguoi khac noi tieng Viet qua Discord/Zoom va ban muon ban dich tieng Anh.

    Ly do can cai nay: tai lieu goc gia dinh nguon LUON la tieng Anh nen co dinh
    language="en". Neu nguon thuc te la tieng Viet, Whisper bi ep phien am tieng
    Viet thanh tieng Anh -> ra rac -> bo loc ao giac loai sach -> app im lang
    hoan toan ma khong bao gi. Da gap dung loi nay.
    """
    return DirectionConfig(
        key="en2vi",          # giu key de GUI khong phai doi khung
        label="Viet -> Anh (nghe am thanh may)",
        source="loopback",
        stt_language="vi",
        tgt_language="en",
        tts_onnx="models/piper/en_US-lessac-medium.onnx",
        tts_json="models/piper/en_US-lessac-medium.onnx.json",
    )


def auto_listen_direction() -> DirectionConfig:
    """Tu nhan dien ngon ngu TUNG CAU, dich moi thu sang tieng Viet.

    Dung khi cuoc noi chuyen NOI LAN Anh voi Viet (vd. choi game voi ban: cau
    tieng Viet xen cau tieng Anh, xen thuat ngu game). Ep mot ngon ngu co dinh
    cho ca phien thi kieu gi cung sai mot nua.

    Cau nao von da la tieng Viet thi giu nguyen, khong dich - chi cac cau tieng
    Anh moi duoc dich sang Viet.

    Danh doi: them ~0.1-0.3s moi cau cho buoc doan ngon ngu, va cau qua ngan
    thi doan de sai.
    """
    return DirectionConfig(
        key="en2vi",
        label="Tu nhan dien (Anh + Viet lan lon) -> Viet",
        source="loopback",
        stt_language="auto",
        tgt_language="vi",
        tts_onnx="models/piper/vi_VN-vais1000-medium.onnx",
        tts_json="models/piper/vi_VN-vais1000-medium.onnx.json",
    )


# Cac cap ngon ngu chon duoc cho khung "nghe am thanh may"
LISTEN_DIRECTIONS = {
    "en2vi": ("Nghe tieng ANH  ->  dich sang Viet", en_to_vi_direction),
    "vi2en": ("Nghe tieng VIET ->  dich sang Anh", listen_vi_to_en_direction),
    "auto": ("TU NHAN DIEN (Anh + Viet lan lon)", auto_listen_direction),
}


@dataclass
class AppConfig:
    audio: AudioConfig = field(default_factory=AudioConfig)
    stt: SttConfig = field(default_factory=SttConfig)
    en2vi: DirectionConfig = field(default_factory=en_to_vi_direction)
    vi2en: DirectionConfig = field(default_factory=vi_to_en_direction)


def default_config(auto_hardware: bool = True) -> AppConfig:
    """Tao cau hinh mac dinh.

    auto_hardware=True se tu do phan cung (GPU/CPU) va chinh SttConfig cho phu hop,
    de cung bo code chay toi uu tren ca may co GPU lan may chi co CPU.
    """
    cfg = AppConfig()
    if auto_hardware:
        from app.hardware import apply_to
        apply_to(cfg)
    return cfg


# ---------------------------------------------------------------------------
# Preset ngu canh chuyen nganh cho Whisper (initial_prompt) - danh cho hop/
# video ve embedded, phan mem, phan cung. Nhet danh sach thuat ngu vao day de
# Whisper UU TIEN nghe ra dung cac tu nay thay vi doan ra tu gan giong nhat.
#
# Chi anh huong STT (nghe ra chu gi); phan BAO VE khoi dich sai thuat ngu nam
# o app/glossary.py (buoc MT, khac loi).
#
# De MAC DINH TAT (initial_prompt="") vi nhet san tu vung ky thuat co the lam
# lech nhe cach Whisper nghe cac cuoc hop KHONG lien quan ky thuat - bat len
# bang --tech (CLI) hoac o GUI khi biet truoc noi dung se nghe la ky thuat.
DOMAIN_PROMPTS: dict[str, str] = {
    "embedded_sw_hw": (
        "Technical discussion about embedded systems, software, and hardware "
        "engineering. Topics include UART, SPI, I2C, GPIO, PWM, ADC, DAC, DMA, "
        "MCU, CPU, FPGA, ASIC, RTOS, firmware, bootloader, kernel, driver, "
        "interrupt service routine, watchdog timer, race condition, mutex, "
        "semaphore, buffer overflow, memory leak, PCB, ground plane, resistor, "
        "capacitor, transistor, JTAG, SWD, datasheet, register, toolchain, "
        "compiler, debugger, GitHub, pull request, API, SDK."
    ),
}


def apply_domain_prompt(cfg: AppConfig, domain: str = "embedded_sw_hw") -> None:
    """Bat initial_prompt theo linh vuc cho SttConfig (mac dinh: embedded/sw/hw)."""
    cfg.stt.initial_prompt = DOMAIN_PROMPTS.get(domain, "")
