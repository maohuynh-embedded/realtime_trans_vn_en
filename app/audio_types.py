"""Kieu du lieu thiet bi audio - dung chung cho moi nen tang.

Tach rieng khoi audio_devices.py de windows/ va macos/ import duoc ma khong
gay vong import (audio_devices import nguoc lai lop nen tang).
"""
from dataclasses import dataclass


@dataclass
class LoopbackDevice:
    """Nguon 'am thanh he thong dang phat ra' (WASAPI loopback / Core Audio tap)."""
    index: int
    name: str
    sample_rate: int
    channels: int


@dataclass
class InputDevice:
    """Mic that (khong phai loopback) - nguon cho chieu Viet -> Anh."""
    index: int
    name: str
    sample_rate: int
    channels: int


@dataclass
class OutputDevice:
    index: int
    name: str
    sample_rate: int
    channels: int = 2
    host_api: str = ""
