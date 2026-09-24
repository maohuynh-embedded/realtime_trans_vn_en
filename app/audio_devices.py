"""Liet ke va chon thiet bi audio - phan DUNG CHUNG cho moi nen tang.

- Mic va thiet bi phat: sounddevice (PortAudio) chay tren ca Windows lan macOS.
- Nguon 'am thanh he thong dang phat ra' (loopback) la phan phu thuoc he dieu
  hanh: nam trong windows/audio.py (WASAPI) va macos/audio.py (Core Audio tap),
  duoc chon boi app/platform_impl.py.
"""
import sounddevice as sd

from app.audio_types import InputDevice, LoopbackDevice, OutputDevice
from app.platform_impl import audio as _platform

__all__ = [
    "InputDevice", "LoopbackDevice", "OutputDevice",
    "list_loopback_devices", "get_default_loopback_device", "is_same_physical_device",
    "list_input_devices", "get_default_input_device",
    "list_output_devices", "get_default_output_device", "is_output_usable",
    "suggest_output_device", "suggest_output_for_virtual_mic", "print_devices",
]

# ---- Loopback: uy quyen cho nen tang ----
list_loopback_devices = _platform.list_loopback_devices
get_default_loopback_device = _platform.get_default_loopback_device
is_same_physical_device = _platform.is_same_physical_device


def _is_generic_alias(name: str) -> bool:
    return any(alias in name.lower() for alias in _platform.GENERIC_ALIASES)


def _host_api_ok(host_api: str) -> bool:
    return any(allowed.lower() in host_api.lower() for allowed in _platform.HOST_APIS)


# ---- Mic ----

def list_input_devices() -> list[InputDevice]:
    """Danh sach mic that, bo qua cac endpoint khong dung duoc/khong on dinh."""
    devices = []
    for idx, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] <= 0:
            continue
        host_api = sd.query_hostapis(dev["hostapi"])["name"]
        if not _host_api_ok(host_api):
            continue
        if _is_generic_alias(dev["name"]):
            continue
        devices.append(
            InputDevice(
                index=idx,
                name=dev["name"].replace("\n", " ").strip(),
                sample_rate=int(dev["default_samplerate"]),
                channels=int(dev["max_input_channels"]),
            )
        )
    return devices


def get_default_input_device() -> InputDevice:
    inputs = list_input_devices()
    default_idx = sd.default.device[0]
    for dev in inputs:
        if dev.index == default_idx:
            return dev
    default_name = sd.query_devices(default_idx)["name"].strip()
    for dev in inputs:
        if default_name.lower()[:20] in dev.name.lower():
            return dev
    if inputs:
        return inputs[0]
    raise RuntimeError("Khong tim thay mic nao.")


# ---- Thiet bi phat ----

def is_output_usable(index: int) -> bool:
    """Thu mo that su thiet bi phat.

    Nhieu endpoint duoc liet ke nhung KHONG co thiet bi cam vao (vd. jack tai nghe
    dang trong) - mo ra se bao 'Invalid device'. Phai thu mo moi biet chac.
    """
    try:
        dev = sd.query_devices(index)
        with sd.OutputStream(
            device=index,
            samplerate=int(dev["default_samplerate"]),
            channels=min(int(dev["max_output_channels"]), 2),
            dtype="float32",
        ):
            return True
    except Exception:
        return False


def list_output_devices(usable_only: bool = True) -> list[OutputDevice]:
    """Danh sach thiet bi phat - day la noi phat ban dich ra."""
    devices = []
    for idx, dev in enumerate(sd.query_devices()):
        if dev["max_output_channels"] <= 0:
            continue
        host_api = sd.query_hostapis(dev["hostapi"])["name"]
        if not _host_api_ok(host_api):
            continue
        if _is_generic_alias(dev["name"]):
            continue
        devices.append(
            OutputDevice(
                index=idx,
                name=dev["name"].replace("\n", " ").strip(),
                sample_rate=int(dev["default_samplerate"]),
                channels=min(int(dev["max_output_channels"]), 2),
                host_api=host_api,
            )
        )

    if usable_only:
        usable = [d for d in devices if is_output_usable(d.index)]
        if usable:
            return usable
    return devices


def get_default_output_device(name_hint: str = "") -> OutputDevice:
    """Chon output device. Co name_hint thi tim theo ten, khong thi dung default cua he thong."""
    outputs = list_output_devices()
    if name_hint:
        for dev in outputs:
            if name_hint.lower() in dev.name.lower():
                return dev
    default_idx = sd.default.device[1]
    for dev in outputs:
        if dev.index == default_idx:
            return dev
    if outputs:
        return outputs[0]
    raise RuntimeError("Khong tim thay thiet bi output nao.")


def _card_name(name: str) -> str:
    """Lay ten CARD tu ten endpoint, vd 'Speakers (Realtek(R) Audio)' -> 'realtek(r) audio'.

    Dung de phan biet 'card khac han' voi 'endpoint khac cua cung 1 card'.
    Ten khong co ngoac (vd. 'BlackHole 2ch') thi giu nguyen ca ten.
    """
    inner = name.replace("[Loopback]", "").strip()
    if "(" in inner and ")" in inner:
        inner = inner[inner.index("(") + 1: inner.rindex(")")]
    return inner.strip().lower()


def suggest_output_device(loopback: LoopbackDevice) -> OutputDevice:
    """Chon noi phat ban dich, tranh vong lap voi thiet bi dang bi loopback bat.

    Nen tang tu bao ve khoi vong lap (macOS loai tru tien trinh cua app khoi tap)
    thi dung luon thiet bi mac dinh cua he thong. Nguoc lai (Windows), uu tien
    theo thu tu:
      1. Card VAT LY khac han thiet bi dang loopback.
      2. Ten co ve tai nghe.
    Chi xet cac thiet bi THUC SU mo duoc.
    """
    if _platform.PREFER_DEFAULT_OUTPUT:
        return get_default_output_device()

    outputs = list_output_devices()
    candidates = [d for d in outputs if not is_same_physical_device(loopback, d)]
    if not candidates:
        return get_default_output_device()

    lb_card = _card_name(loopback.name)
    other_card = [d for d in candidates if _card_name(d.name) != lb_card]
    pool = other_card or candidates

    for keyword in ("headphone", "headset", "tai nghe", "airpods"):
        for dev in pool:
            if keyword in dev.name.lower():
                return dev
    return pool[0]


def suggest_output_for_virtual_mic(virtual_mic) -> "OutputDevice | None":
    """Chon thiet bi PHAT sao cho mic ao dang chon nghe duoc no.

    Windows: 'Stereo Mix' chi bat am thanh cua CHINH CARD no thuoc ve. macOS: mic ao
    kieu BlackHole co dau vao va dau ra cung ten. Ca hai truong hop deu ghep theo ten card.

    Tra ve None neu khong tim duoc output cung card.
    """
    mic_card = _card_name(virtual_mic.name)
    outputs = list_output_devices()

    same_card = [d for d in outputs if _card_name(d.name) == mic_card]
    if not same_card:
        return None

    # Uu tien "Speakers" hon "Digital Output" (SPDIF thuong khong ra Stereo Mix)
    for dev in same_card:
        if "speaker" in dev.name.lower():
            return dev
    return same_card[0]


def print_devices() -> None:
    """Ho tro debug: `python -m app.audio_devices` de in danh sach thiet bi."""
    print("=== Loopback (input) devices ===")
    for d in list_loopback_devices():
        print(f"  [{d.index}] {d.name}  ({d.sample_rate} Hz, {d.channels} ch)")
    default_lb = get_default_loopback_device()
    print(f"--> Default loopback: [{default_lb.index}] {default_lb.name}")

    print("\n=== Input devices (mic - nguon cho chieu Viet->Anh) ===")
    for d in list_input_devices():
        print(f"  [{d.index}] {d.name}  ({d.sample_rate} Hz, {d.channels} ch)")
    try:
        default_in = get_default_input_device()
        print(f"--> Default mic: [{default_in.index}] {default_in.name}")
    except RuntimeError as exc:
        print(f"--> {exc}")

    print("\n=== Output devices ===")
    for d in list_output_devices():
        print(f"  [{d.index}] {d.name}  ({d.sample_rate} Hz)")
    default_out = get_default_output_device()
    print(f"--> Default output: [{default_out.index}] {default_out.name}")


if __name__ == "__main__":
    print_devices()
