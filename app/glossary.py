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

    # --- RTOS / embedded chuyen sau ---
    "context switch": "chuyển ngữ cảnh",
    "task scheduler": "bộ lập lịch",
    "priority inversion": "đảo ưu tiên",
    "stack pointer": "con trỏ stack",
    "program counter": "bộ đếm chương trình",
    "hard real-time": "thời gian thực cứng",
    "soft real-time": "thời gian thực mềm",
    "clock domain crossing": "chuyển miền xung nhịp",
    "bit banging": "bit banging",
    "nested interrupt": "ngắt lồng",
    "memory mapped io": "IO ánh xạ bộ nhớ",
    "direct memory access": "truy cập bộ nhớ trực tiếp",

    # --- Bo nho / hieu nang ---
    "cache line": "dòng cache",
    "cache miss": "cache miss",
    "page fault": "page fault",
    "virtual memory": "bộ nhớ ảo",

    # --- PCB / dien tu sau hon ---
    "surface mount": "dán bề mặt",
    "through hole": "xuyên lỗ",
    "trace width": "độ rộng đường mạch",
    "impedance matching": "phối hợp trở kháng",
    "decoupling capacitor": "tụ lọc nguồn",
    "bypass capacitor": "tụ bypass",
    "level shifter": "IC chuyển mức",
    "pull-up network": "mạng pull-up",

    # --- Mang / he thong ---
    "packet loss": "mất gói tin",
    "round trip time": "thời gian khứ hồi",
    "load balancer": "load balancer",
    "reverse proxy": "reverse proxy",
    "network interface card": "card mạng",

    # --- Git / quan ly ma nguon ---
    "pull request": "pull request",
    "merge conflict": "xung đột merge",
    "commit history": "lịch sử commit",
    "feature branch": "nhánh tính năng",
    "code review": "review code",

    # --- DevOps / cloud ---
    "continuous integration": "tích hợp liên tục",
    "continuous deployment": "triển khai liên tục",
    "container orchestration": "điều phối container",

    # --- Kiem thu ---
    "unit test": "unit test",
    "integration test": "integration test",
    "test coverage": "độ phủ kiểm thử",
    "mock object": "mock object",

    # --- Cau truc du lieu ---
    "linked list": "danh sách liên kết",
    "hash table": "bảng băm",
    "binary tree": "cây nhị phân",
    "priority queue": "hàng đợi ưu tiên",
}

# ---------------------------------------------------------------------------
# TU DON - kiem tra sau khi da xu ly het cum tu o tren.
# ---------------------------------------------------------------------------
_WORDS: dict[str, str | None] = {
    # --- Giao tiep / giao thuc: giu nguyen (quy uoc pho bien) ---
    "uart": None, "spi": None, "i2c": None, "usb": None,
    # LUU Y: KHONG dua "can" (giao thuc CAN bus) vao day rieng le - da gap
    # loi that: khop trung voi dong tu "can" ("Can you...") vi so khop khong
    # phan biet hoa-thuong, lam hong ca cau ("Can you open..." -> "Can ban
    # mo..."). "CAN bus" van duoc bao ve qua cum "can bus" trong _PHRASES,
    # chi khong bao ve duoc khi dung "CAN" mot minh (hiem gap hon nhieu).
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
    "oscillator": "bộ dao động",
    "crystal": "thạch anh",
    "inductor": "cuộn cảm",
    "potentiometer": "biến trở",
    "relay": "rơ-le",
    "solenoid": "solenoid",
    "connector": "đầu nối",

    # --- Mang / giao thuc: giu nguyen (quy uoc pho bien) ---
    "socket": None, "packet": None, "gateway": None, "router": None,
    "firewall": None, "vpn": None, "dns": None, "dhcp": None,
    "ssl": None, "tls": None, "ssh": None, "ftp": None, "port": None,

    # --- Git / quan ly phien ban: giu nguyen ---
    # LUU Y: "commit"/"branch"/"merge"/"rebase"/"clone"/"fork"/"stash" O DAY
    # DA BI BO - deu la tu VUA danh tu VUA dong tu. Da do thuc te: bao ve
    # "rebase" dung mot minh lam CAU SUP HOAN TOAN khi no dung o vi tri dong
    # tu dau cau menh lenh ("Please rebase your..." -> "Lam on... ..dua ra
    # con truoc khi ..." - NLLB mat phuong huong ngu phap, sinh dau "..." thay
    # vi noi dung). Van duoc bao ve khi nam trong CUM co san ("merge conflict",
    # "feature branch" trong _PHRASES) - o do co du ngu canh xung quanh nen
    # an toan hon. Danh tu THUAN TUY (repository) thi giu lai duoc.
    "repository": None,

    # --- DevOps / cloud: giu nguyen ---
    "docker": None, "kubernetes": None, "container": None,
    "microservice": None, "pipeline": None, "deployment": None,
    "rollback": None,

    # --- Nen tang lap trinh: giu nguyen (thuat ngu CS chuan) ---
    "stack": None, "heap": None, "recursion": None, "iterator": None,
    "generic": None, "template": None, "inheritance": None,
    "polymorphism": None, "encapsulation": None, "abstraction": None,
    "queue": None,

    # --- "False friend" - tu tieng Anh thong dung nhung mang nghia ky thuat
    # KHAC HAN nghia thuong ngay, NLLB de bi nham sang nghia thuong ngay.
    # CHI giu lai o day cac tu THUONG DUNG NHU DANH TU trong cau ky thuat
    # (bus, plane, frame, buffer, driver, host, routine) - cac tu vua danh tu
    # vua dong tu de gay sup cau nhu "rebase" (mount, pipe, stream, flag,
    # handle, cache) DA BO, cung ly do nhu tren.
    "driver": None,     # trinh dieu khien, khong phai "tai xe"
    "host": None,       # may chu/thiet bi chinh, khong phai "chu nha"
    "frame": None,      # khung du lieu/anh, khong phai "khung tranh"
    "buffer": None,     # vung dem du lieu, khong phai "vung dem va cham"
    "bus": None,        # bus du lieu, khong phai "xe buyt"
    "plane": None,      # lop/mat phang, khong phai "may bay"
    "routine": None,    # chuong trinh con, khong phai "thoi quen"
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


# So tu TOI THIEU trong CAU GOC de con bao ve bang placeholder. Da do thuc te
# (khong doan): cau qua ngan khong du "ngu canh that" xung quanh placeholder
# khien NLLB mat phuong huong, sinh ra noi dung SAI HOAN TOAN thay vi chi
# khong dich duoc thuat ngu:
#
#   4 tu  "The __0__ is stuck."                    -> "- Co may bi mac ket."  HONG
#   7 tu  "The __0__ on this board is stuck."       -> giu dung placeholder    OK
#   9 tu  "Check the __0__ on this board..."        -> giu dung placeholder    OK
#
# Chon dung 7 (diem du lieu THAP NHAT da xac nhan AN TOAN o tren, khong noi
# suy them) lam nguong. Duoi nguong nay, BO QUA bao ve hoan toan - cau ngan
# van dich duoc, chi co the sai rieng thuat ngu (rui ro CU, da biet, khong
# nghiem trong), con hon nguy co MAT HET NOI DUNG (rui ro MOI, do chinh viec
# bao ve gay ra). Da thu nguong 6 truoc va van HONG voi cau 6 tu that
# ("I missed the bus this morning." -> mat het "bus"), nen khong ha thap hon 7.
MIN_WORDS_FOR_PROTECTION = 7


def protect_terms(text: str) -> tuple[str, list[str]]:
    """Thay cac thuat ngu biet truoc bang placeholder, tra ve (text_moi, restore_list).

    restore_list[i] la GIA TRI CAN THAY VAO ban dich sau nay (tu tieng Viet neu
    co, hoac nguyen van tieng Anh goc neu can giu nguyen).

    Cau qua NGAN (duoi MIN_WORDS_FOR_PROTECTION tu) se KHONG duoc bao ve - xem
    ghi chu o MIN_WORDS_FOR_PROTECTION ve ly do.
    """
    if len(text.split()) < MIN_WORDS_FOR_PROTECTION:
        return text, []

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
