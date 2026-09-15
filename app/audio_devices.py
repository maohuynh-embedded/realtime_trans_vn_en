"""Liet ke va chon thiet bi audio.

- Input mac dinh: WASAPI loopback device tuong ung voi thiet bi PHAT mac dinh
  (bat am thanh cuoc hop dang phat ra loa/tai nghe), dung PyAudioWPatch.
  Khong can VB-CABLE, khong can driver, khong can quyen admin.
- Output mac dinh: thiet bi phat that (tai nghe) de phat ban dich, dung sounddevice.
"""
from dataclasses import dataclass
from typing import Optional

import pyaudiowpatch as pyaudio
import sounddevice as sd


@dataclass
class LoopbackDevice:
    index: int
    name: str
    sample_rate: int
    channels: int


def list_loopback_devices() -> list[LoopbackDevice]:
    """Tra ve danh sach cac WASAPI loopback device hien co."""
    devices = []
    with pyaudio.PyAudio() as p:
        for dev in p.get_loopback_device_info_generator():
            devices.append(
                LoopbackDevice(
                    index=dev["index"],
                    name=dev["name"],
                    sample_rate=int(dev["defaultSampleRate"]),
                    channels=int(dev["maxInputChannels"]),
                )
            )
    return devices


def get_default_loopback_device() -> LoopbackDevice:
    """Loopback device tuong ung voi thiet bi PHAT mac dinh cua Windows.

    Day la input ma pipeline se dung de bat am thanh cuoc hop.
    """
    with pyaudio.PyAudio() as p:
        default_speakers = p.get_default_wasapi_loopback()
        return LoopbackDevice(
            index=default_speakers["index"],
            name=default_speakers["name"],
            sample_rate=int(default_speakers["defaultSampleRate"]),
            channels=int(default_speakers["maxInputChannels"]),
        )


@dataclass
class InputDevice:
    """Mic that (khong phai loopback) - nguon cho chieu Viet -> Anh."""
    index: int
    name: str
    sample_rate: int
    channels: int


def list_input_devices() -> list[InputDevice]:
    """Danh sach mic that, bo qua cac endpoint Bluetooth hands-free 8kHz (chat luong qua thap)."""
    devices = []
    for idx, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] <= 0:
            continue
        host_api = sd.query_hostapis(dev["hostapi"])["name"]
        if "WASAPI" not in host_api and "DirectSound" not in host_api:
            continue  # bo MME/WDM-KS cho gon, 2 host API nay du dung va on dinh nhat
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


@dataclass
class OutputDevice:
    index: int
    name: str
    sample_rate: int
    channels: int = 2
    host_api: str = ""


# Cac "thiet bi" ao do Windows tao ra, tro toi thiet bi mac dinh chu khong phai
# phan cung that - chon chung se gay nham lan (vd. phat ra dung cho thiet bi dang
# bi loopback bat ma khong biet).
_GENERIC_ALIASES = (
    "primary sound driver",
    "primary sound capture driver",
    "microsoft sound mapper",
)


def _is_generic_alias(name: str) -> bool:
    return any(alias in name.lower() for alias in _GENERIC_ALIASES)


def is_output_usable(index: int) -> bool:
    """Thu mo that su thiet bi phat.

    Windows liet ke ca nhung endpoint KHONG co thiet bi cam vao (vd. jack tai nghe
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
    """Danh sach thiet bi phat - day la noi phat ban dich ra.

    Bo cac host API khong dung de phat duoc on dinh (WDM-KS thuong la endpoint
    phan cung tho, hay bao 'Invalid device' khi jack dang trong).
    """
    devices = []
    for idx, dev in enumerate(sd.query_devices()):
        if dev["max_output_channels"] <= 0:
            continue
        host_api = sd.query_hostapis(dev["hostapi"])["name"]
        if "WASAPI" not in host_api and "DirectSound" not in host_api:
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
    """Chon output device. Neu co name_hint thi tim theo ten, khong thi dung default cua he thong."""
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


def _normalize_device_name(name: str) -> str:
    return name.replace("[Loopback]", "").strip().lower()


def is_same_physical_device(loopback: LoopbackDevice, output: OutputDevice) -> bool:
    """True neu output device chinh la thiet bi dang bi loopback bat.

    Neu trung nhau se sinh vong lap: ban dich phat ra loa -> loopback bat lai ->
    dich tiep (xem muc 8 cua HUONG_DAN_XAY_DUNG.md). Phai canh bao nguoi dung.
    """
    return _normalize_device_name(loopback.name) == _normalize_device_name(output.name)


def _card_name(name: str) -> str:
    """Lay ten CARD tu ten endpoint, vd 'Speakers (Realtek(R) Audio)' -> 'realtek(r) audio'.

    Dung de phan biet 'card khac han' voi 'endpoint khac cua cung 1 card'.
    """
    inner = name.replace("[Loopback]", "").strip()
    if "(" in inner and ")" in inner:
        inner = inner[inner.index("(") + 1: inner.rindex(")")]
    return inner.strip().lower()


def suggest_output_device(loopback: LoopbackDevice) -> OutputDevice:
    """Chon noi phat ban dich, KHAC thiet bi dang bi loopback bat (tranh vong lap).

    Uu tien theo thu tu:
      1. Card VAT LY khac han (vd. dang loopback Realtek -> phat ra Maonocaster).
         Endpoint khac cua cung 1 card van co the bi Stereo Mix/loopback bat lai.
      2. Ten co ve tai nghe.
    Chi xet cac thiet bi THUC SU mo duoc (da loc trong list_output_devices).
    """
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


def suggest_output_for_virtual_mic(virtual_mic) -> "OutputDevice | None":
    """Chon thiet bi PHAT sao cho mic ao dang chon nghe duoc no.

    Mic ao kieu "Stereo Mix" chi bat am thanh cua CHINH CARD no thuoc ve:
    Stereo Mix (Realtek) chi nghe duoc tieng phat ra Speakers (Realtek), khong
    nghe duoc tieng phat ra Maonocaster. Chon nham cap la khong co tin hieu nao
    di qua, du ca hai thiet bi deu hoat dong binh thuong.

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
