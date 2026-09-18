"""Tu dien thuat ngu chuyen nganh (embedded / software / hardware) - bao ve
NLLB khoi dich sai nghiem trong cac cum tu ky thuat.

Da do thuc te (khong doan): NLLB-600M dich thuat ngu ky thuat RAT TE, khong
chi "chua sat nghia" nhu idiom ma con SAI HOAN TOAN, de gay hieu lam nghiem
trong cho ky su:

    "I2C bus"                    -> "xe BUYT I2C"        (bus = xe cho khach!)
    "ground plane"                -> "MAY BAY mat dat"     (plane = may bay!)
    "pull-up resistor"            -> "khang cu keo len"    (resistor = dien tro,
                                                             khong phai "khang cu")
    "watchdog timer"              -> "Thoi gian dong ho bao ve" (vo nghia)
    "interrupt service routine"   -> "thoi quen dich vu gian doan" (routine = habit)
    "two threads"                 -> "hai CHUOI"           (chuoi = string, sai)

Nguyen nhan: cac tu tieng Anh thong dung (bus, plane, routine, resistor...)
mang NGHIA KHAC HAN trong ngu canh ky thuat so voi nghia thong thuong, va
NLLB-600M (model nho, huan luyen chu yeu tren van ban trang trong) khong du
kha nang phan biet ngu canh de chon dung nghia.

Chien luoc: BAO VE cac cum tu ky thuat bang placeholder TRUOC khi dua vao MT,
dich cau voi placeholder (NLLB khong dung cham vao chuoi placeholder), roi
THAY THE LAI SAU khi dich xong. Uu tien khop CUM DAI truoc (longest-match-first)
de "ground plane" duoc bao ve nguyen cum, khong bi tach thanh "ground" + "plane"
roi dich rieng tung tu.

Moi thuat ngu anh xa toi MOT TRONG HAI:
  - None  : GIU NGUYEN tieng Anh (da la quy uoc chuan cua ky su Viet Nam, vd.
            "firmware", "bootloader", "kernel" - dich sang tieng Viet nghe
            gia tao hon la giu nguyen).
  - str   : thay bang tu tieng Viet co san, chuan nganh (vd. "resistor" ->
            "dien tro", "sensor" -> "cam bien" - day la thuat ngu ky thuat Viet
            THAT SU duoc dung, khong phai dich may moc).
"""
import re

# ---------------------------------------------------------------------------
# CUM TU (2+ tu) - PHAI kiem tra truoc cac tu don, vi NLLB hay dich sai theo
# nghia THONG THUONG cua tung tu rieng le khi chung dung ca cum ky thuat.
# ---------------------------------------------------------------------------
_PHRASES: dict[str, str | None] = {
    # Bus / giao tiep - "bus" hay bi dich thanh "xe buyt"
    "i2c bus": None,
    "spi bus": None,
    "can bus": None,
    "data bus": "bus dữ liệu",
    "address bus": "bus địa chỉ",
    "system bus": "bus hệ thống",

    # PCB / hardware - "plane" hay bi dich thanh "may bay"
    "ground plane": "lớp mass",
    "power plane": "lớp nguồn",

    # Dien tro/linh kien - "resistor" hay bi dich thanh "khang cu"
    "pull-up resistor": "điện trở pull-up",
    "pull-down resistor": "điện trở pull-down",
    "pull up resistor": "điện trở pull-up",
    "pull down resistor": "điện trở pull-down",
    "current limiting resistor": "điện trở hạn dòng",

    # Timer/watchdog - "watchdog timer" hay dich vo nghia
    "watchdog timer": "watchdog",
    "hardware watchdog": "watchdog phần cứng",

    # Ngat - "routine" hay bi dich thanh "thoi quen"
    "interrupt service routine": "trình phục vụ ngắt",
    "interrupt handler": "trình xử lý ngắt",
    "interrupt vector": "vector ngắt",

    # Concurrency - "thread" hay bi dich thanh "chuoi" (string)
    "race condition": "race condition",
    "shared buffer": "buffer dùng chung",
    "critical section": "vùng tới hạn",
    "deadlock": "deadlock",

    # Bo nho
    "buffer overflow": "tràn buffer",
    "stack overflow": "tràn stack",
    "memory leak": "rò rỉ bộ nhớ",
    "flash memory": "bộ nhớ flash",

    # Cac cum thuong gap khac
    "clock frequency": "tần số xung nhịp",
    "clock signal": "tín hiệu clock",
    "power supply": "nguồn cấp điện",
    "voltage regulator": "IC ổn áp",
    "signal integrity": "toàn vẹn tín hiệu",
    "root cause": "nguyên nhân gốc rễ",
}

# ---------------------------------------------------------------------------
# TU DON - kiem tra sau khi da xu ly het cum tu o tren.
# ---------------------------------------------------------------------------
_WORDS: dict[str, str | None] = {
    # --- Giao tiep / giao thuc: giu nguyen (quy uoc pho bien) ---
    "uart": None, "spi": None, "i2c": None, "usb": None, "can": None,
    "lin": None, "rs232": None, "rs485": None, "ethernet": None,
    "wifi": None, "bluetooth": None, "ble": None, "lora": None,
    "zigbee": None, "mqtt": None, "tcp": None, "udp": None,
    "http": None, "json": None, "sda": None, "scl": None,
    "jtag": None, "swd": None, "hdmi": None, "sata": None, "pcie": None,

    # --- Vi xu ly / bo nho: giu nguyen ---
    "mcu": None, "cpu": None, "gpu": None, "fpga": None, "asic": None,
    "ram": None, "rom": None, "eeprom": None, "nand": None, "nor": None,
    "sram": None, "dram": None, "ddr": None,

    # --- Chan/tin hieu: giu nguyen ---
    "gpio": None, "pwm": None, "adc": None, "dac": None, "dma": None,
    "isr": None, "nvic": None, "crc": None, "emi": None, "esd": None,

    # --- Phan mem nhung: giu nguyen (thuat ngu chuan cua ky su) ---
    "firmware": None, "bootloader": None, "kernel": None, "rtos": None,
    "toolchain": None, "makefile": None, "compiler": None,
    "linker": None, "debugger": None, "watchdog": None, "bitmask": None,
    "checksum": None, "endianness": None, "mutex": None, "semaphore": None,
    "callback": None, "struct": None, "enum": None, "typedef": None,
    "pointer": None, "hal": None, "bsp": None, "sdk": None, "api": None,

    # --- Co ban dich tieng Viet chuan nganh, dung duoc ---
    "resistor": "điện trở",
    "capacitor": "tụ điện",
    "transistor": "transistor",
    "diode": "diode",
    "sensor": "cảm biến",
    "actuator": "cơ cấu chấp hành",
    "oscilloscope": "máy hiện sóng",
    "multimeter": "đồng hồ vạn năng",
    "microcontroller": "vi điều khiển",
    "motherboard": "bo mạch chủ",
    "breadboard": "board test",
    "datasheet": "datasheet",
    "register": "thanh ghi",
    "voltage": "điện áp",
    "current": "dòng điện",
    "ground": "mass",
    "thread": "luồng",
    "threads": "các luồng",
}


def _build_pattern(terms: dict) -> "re.Pattern | None":
    if not terms:
        return None
    # Sap xep dai truoc - regex alternation uu tien khop dau tien khop duoc,
    # nen phai dat cum/tu DAI hon len truoc de tranh khop nham phan con lai
    # cua mot cum dai hon (vd. "pull-up resistor" phai thu truoc "resistor").
    escaped = sorted((re.escape(t) for t in terms), key=len, reverse=True)
    return re.compile(r"(?<![\w-])(" + "|".join(escaped) + r")(?![\w-])", re.IGNORECASE)


_PHRASE_PATTERN = _build_pattern(_PHRASES)
_WORD_PATTERN = _build_pattern(_WORDS)

_PLACEHOLDER_FMT = "__{}__"

# Vi sao dung "__N__" thay vi chuoi dai kieu "XTERMPLHXX0XX":
# da do thuc te, chuoi alnum dai (11+ ky tu la) bi SentencePiece tokenizer cua
# NLLB tach thanh nhieu manh va doi khi LAM HONG khi sinh lai (chen khoang
# trang giua, mat ky tu - vd "XTERMPLHXX2XX" -> "XTERMP LHXX2XX"). Da thu 5
# dinh dang khac nhau; "__N__" (gach duoi kep) la dinh dang NGAN, PHO BIEN
# trong du lieu huan luyen (quy uoc dat ten bien lap trinh) nen duoc giu
# nguyen VEN 6/6 lan trong 1 cau co toi 6 placeholder cung luc - dang tin cay
# hon han cac lua chon khac da thu (chuoi dai, so khoanh tron, ngoac vuong kep).


def protect_terms(text: str) -> tuple[str, list[str]]:
    """Thay cac thuat ngu biet truoc bang placeholder, tra ve (text_moi, restore_list).

    restore_list[i] la GIA TRI CAN THAY VAO ban dich sau nay (tu tieng Viet neu
    co, hoac nguyen van tieng Anh goc neu can giu nguyen).
    """
    restore: list[str] = []

    def _sub(match: "re.Match", table: dict) -> str:
        original = match.group(0)
        viet = table.get(original.lower())
        replacement = viet if viet is not None else original  # None -> giu nguyen ban goc
        idx = len(restore)
        restore.append(replacement)
        return _PLACEHOLDER_FMT.format(idx)

    if _PHRASE_PATTERN is not None:
        text = _PHRASE_PATTERN.sub(lambda m: _sub(m, _PHRASES), text)
    if _WORD_PATTERN is not None:
        text = _WORD_PATTERN.sub(lambda m: _sub(m, _WORDS), text)

    return text, restore


def restore_terms(translated_text: str, restore: list[str]) -> str:
    """Thay placeholder trong ban dich bang gia tri that su.

    NLLB doi khi them khoang trang/doi hoa-thuong trong placeholder (vd.
    "Xtermplhxx0Xx") - regex khop khong phan biet hoa-thuong de van bat duoc.
    """
    def _repl(match: "re.Match") -> str:
        idx = int(match.group(1))
        return restore[idx] if 0 <= idx < len(restore) else match.group(0)

    return re.sub(r"_{1,3}(\d+)_{1,3}", _repl, translated_text)
