"""Insere o texto no app em foco: área de transferência + Ctrl+V por teclado virtual.

Usa /dev/uinput direto (fcntl + struct, sem dependência compilada). Funciona no
Wayland/GNOME, onde xdotool/wtype não chegam. Colar (em vez de digitar) preserva
acentos e independe do layout do teclado.
"""

from __future__ import annotations

import fcntl
import os
import struct
import time
from typing import Callable, Optional, Protocol

import pyperclip

EV_SYN = 0x00
EV_KEY = 0x01
SYN_REPORT = 0
KEY_LEFTCTRL = 29
KEY_LEFTSHIFT = 42
KEY_V = 47

INPUT_EVENT_FMT = "llHHi"  # struct input_event (timeval + type + code + value)
_UINPUT_SETUP_FMT = "HHHH80sI"  # struct uinput_setup
BUS_VIRTUAL = 0x06


def _ioc(direction: int, nr: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (ord("U") << 8) | nr


UI_DEV_CREATE = _ioc(0, 1, 0)
UI_DEV_DESTROY = _ioc(0, 2, 0)
UI_DEV_SETUP = _ioc(1, 3, struct.calcsize(_UINPUT_SETUP_FMT))
UI_SET_EVBIT = _ioc(1, 100, 4)
UI_SET_KEYBIT = _ioc(1, 101, 4)

COMBOS = {
    "ctrl+v": (KEY_LEFTCTRL, KEY_V),
    "ctrl+shift+v": (KEY_LEFTCTRL, KEY_LEFTSHIFT, KEY_V),
}


class InjectionUnavailable(RuntimeError):
    """Sem acesso ao /dev/uinput — o texto fica só na área de transferência."""


class Device(Protocol):
    def emit(self, etype: int, code: int, value: int) -> None: ...
    def close(self) -> None: ...


class Clipboard(Protocol):
    def get(self) -> str: ...
    def set(self, text: str) -> None: ...


class UinputKeyboard:
    """Teclado virtual mínimo (só as teclas de colar)."""

    # O compositor leva um instante para adotar um dispositivo recém-criado
    SETTLE_SECONDS = 0.3

    def __init__(self, path: str = "/dev/uinput") -> None:
        self._fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
        try:
            fcntl.ioctl(self._fd, UI_SET_EVBIT, EV_KEY)
            for key in (KEY_LEFTCTRL, KEY_LEFTSHIFT, KEY_V):
                fcntl.ioctl(self._fd, UI_SET_KEYBIT, key)
            setup = struct.pack(
                _UINPUT_SETUP_FMT, BUS_VIRTUAL, 0x1209, 0x5654, 1, b"VoxTalk virtual keyboard", 0
            )
            fcntl.ioctl(self._fd, UI_DEV_SETUP, setup)
            fcntl.ioctl(self._fd, UI_DEV_CREATE)
        except OSError:
            os.close(self._fd)
            raise
        time.sleep(self.SETTLE_SECONDS)

    def emit(self, etype: int, code: int, value: int) -> None:
        os.write(self._fd, struct.pack(INPUT_EVENT_FMT, 0, 0, etype, code, value))

    def close(self) -> None:
        try:
            fcntl.ioctl(self._fd, UI_DEV_DESTROY)
        finally:
            os.close(self._fd)


class PyperclipClipboard:
    def get(self) -> str:
        return pyperclip.paste()

    def set(self, text: str) -> None:
        pyperclip.copy(text)


class TextInjector:
    # Espera antes de restaurar a área de transferência (o app alvo lê de forma assíncrona)
    RESTORE_DELAY = 0.4
    KEY_DELAY = 0.01

    def __init__(
        self,
        device_factory: Callable[[], Device] = UinputKeyboard,
        clipboard: Optional[Clipboard] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._device_factory = device_factory
        self._clipboard = clipboard or PyperclipClipboard()
        self._sleep = sleep
        self._device: Optional[Device] = None

    def inject(self, text: str, combo: str = "ctrl+v", restore_clipboard: bool = False) -> None:
        """Cola `text` no app em foco. Levanta InjectionUnavailable sem uinput."""
        previous = None
        if restore_clipboard:
            try:
                previous = self._clipboard.get()
            except Exception:
                previous = None
        self._clipboard.set(text)
        device = self._ensure_device()
        self._press(device, COMBOS.get(combo, COMBOS["ctrl+v"]))
        if previous is not None:
            self._sleep(self.RESTORE_DELAY)
            self._clipboard.set(previous)

    def close(self) -> None:
        if self._device is not None:
            try:
                self._device.close()
            except OSError:
                pass
            self._device = None

    def _ensure_device(self) -> Device:
        if self._device is None:
            try:
                self._device = self._device_factory()
            except OSError as exc:
                raise InjectionUnavailable(
                    f"Sem acesso a /dev/uinput ({exc.strerror or exc}). "
                    "O texto ficou na área de transferência — veja o README."
                ) from exc
        return self._device

    def _press(self, device: Device, keys: tuple[int, ...]) -> None:
        for key in keys:
            device.emit(EV_KEY, key, 1)
            device.emit(EV_SYN, SYN_REPORT, 0)
            self._sleep(self.KEY_DELAY)
        for key in reversed(keys):
            device.emit(EV_KEY, key, 0)
            device.emit(EV_SYN, SYN_REPORT, 0)
            self._sleep(self.KEY_DELAY)
