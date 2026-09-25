"""Insere o texto no app em foco: área de transferência + Ctrl+V por teclado virtual.

Usa /dev/uinput direto (fcntl + struct, sem dependência compilada). Funciona no
Wayland/GNOME, onde xdotool/wtype não chegam. Colar (em vez de digitar) preserva
acentos e independe do layout do teclado.
"""

from __future__ import annotations

import fcntl
import os
import re
import shutil
import struct
import subprocess
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
    def holds_text(self, text: str) -> bool: ...


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


def _selection_targets() -> Optional[list[str]]:
    """Targets anunciados pela seleção CLIPBOARD (X11: xclip, Wayland: wl-paste).

    None quando não há como perguntar — não é motivo para bloquear a injeção.
    """
    probes = (
        ["xclip", "-o", "-selection", "clipboard", "-t", "TARGETS"],
        ["wl-paste", "--list-types"],
    )
    for cmd in probes:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode != 0:
            continue
        if "TARGETS" in proc.stdout.split() and "utf8" not in proc.stdout.lower():
            continue  # resposta de erro do X11, não é a lista de targets
        return proc.stdout.split()
    return None


IMAGE_TARGETS = ("image", "pixmap", "bitmap")

# WM_CLASS de emuladores de terminal: neles Ctrl+V chega ao programa como ^V
# (o opencode trata isso como "colar imagem"; outros TUIs simplesmente ignoram).
TERMINAL_CLASSES = (
    "term",  # gnome-terminal, xterm, urxvt, xfce4-terminal, terminator…
    "konsole", "kitty", "alacritty", "wezterm", "tilix", "foot", "ptyxis", "kgx",
    "ghostty", "guake", "yakuake", "tabby", "hyper", "blackbox", "st-256color", "rio",
)


def _active_window_class() -> Optional[str]:
    """WM_CLASS da janela em foco (X11/XWayland via xprop). None se não der para saber."""
    try:
        root = subprocess.run(
            ["xprop", "-root", "_NET_ACTIVE_WINDOW"], capture_output=True, text=True, timeout=1
        )
        match = re.search(r"window id # (0x[0-9a-fA-F]+)", root.stdout)
        if not match or int(match.group(1), 16) == 0:
            return None
        win = subprocess.run(
            ["xprop", "-id", match.group(1), "WM_CLASS"], capture_output=True, text=True, timeout=1
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if win.returncode != 0 or "=" not in win.stdout:
        return None
    return win.stdout.split("=", 1)[1].strip().lower()


def focused_is_terminal(window_class: Callable[[], Optional[str]] = _active_window_class) -> bool:
    wm_class = window_class()
    return bool(wm_class) and any(name in wm_class for name in TERMINAL_CLASSES)


def prefer_xsel() -> None:
    """No X11, usa o xsel como backend do pyperclip em vez do xclip.

    O xclip, quando dono da seleção, responde a QUALQUER target com o texto:
    `xclip -t image/png -o` devolve os bytes do texto com sucesso. O opencode
    pergunta por image/png antes de ler texto e cola "[Image 1]". O xsel recusa
    targets que não tem.
    """
    if os.environ.get("WAYLAND_DISPLAY") or not os.environ.get("DISPLAY"):
        return
    if shutil.which("xsel"):
        pyperclip.set_clipboard("xsel")


class PyperclipClipboard:
    def __init__(self) -> None:
        prefer_xsel()

    def get(self) -> str:
        return pyperclip.paste()

    def set(self, text: str) -> None:
        pyperclip.copy(text)

    def holds_text(self, text: str) -> bool:
        """True se a seleção CLIPBOARD é só texto e é a que acabamos de escrever."""
        try:
            targets = _selection_targets()
            if targets is None:
                return pyperclip.paste() == text
            lowered = [t.lower() for t in targets]
            if any(marker in t for t in lowered for marker in IMAGE_TARGETS):
                return False
            return pyperclip.paste() == text
        except Exception:
            return True  # não saber não pode ser motivo para não colar


class TextInjector:
    # Espera antes de restaurar a área de transferência (o app alvo lê de forma assíncrona)
    RESTORE_DELAY = 0.4
    KEY_DELAY = 0.01
    # Tentativas de assumir a seleção CLIPBOARD como texto puro
    SET_ATTEMPTS = 3
    SET_RETRY_DELAY = 0.05

    def __init__(
        self,
        device_factory: Callable[[], Device] = UinputKeyboard,
        clipboard: Optional[Clipboard] = None,
        sleep: Callable[[float], None] = time.sleep,
        is_terminal: Callable[[], bool] = focused_is_terminal,
    ) -> None:
        self._device_factory = device_factory
        self._clipboard = clipboard or PyperclipClipboard()
        self._sleep = sleep
        self._is_terminal = is_terminal
        self._device: Optional[Device] = None

    def inject(self, text: str, combo: str = "auto", restore_clipboard: bool = False) -> None:
        """Cola `text` no app em foco. Levanta InjectionUnavailable sem uinput.

        combo="auto" usa Ctrl+Shift+V quando a janela em foco é um terminal.
        """
        combo = self._resolve_combo(combo)
        previous = None
        if restore_clipboard:
            try:
                previous = self._clipboard.get()
            except Exception:
                previous = None
            # Um clipboard só de imagem não tem texto: guardar "" apagaria o que o
            # usuário tinha copiado, então nesse caso não há o que restaurar.
            if previous is not None and not previous.strip():
                previous = None
        self._set_text_reliably(text)
        device = self._ensure_device()
        self._press(device, COMBOS[combo])
        if previous is not None:
            self._sleep(self.RESTORE_DELAY)
            self._clipboard.set(previous)

    def _resolve_combo(self, combo: str) -> str:
        if combo in COMBOS:
            return combo
        try:
            return "ctrl+shift+v" if self._is_terminal() else "ctrl+v"
        except Exception:
            return "ctrl+v"

    def _set_text_reliably(self, text: str) -> None:
        """Garante que o clipboard é TEXTO PURO antes de mandar o Ctrl+V.

        Outro app pode sequestrar a seleção CLIPBOARD e anunciar targets de imagem
        (application/x-qt-image, image/png, PIXMAP…). Apps como o opencode colam a
        imagem e descartam o texto quando existem, então confirmamos e repetimos.
        """
        for attempt in range(self.SET_ATTEMPTS):
            self._clipboard.set(text)
            if self._clipboard.holds_text(text):
                return
            self._sleep(self.SET_RETRY_DELAY * (attempt + 1))
        # Último recurso: um app teimoso sequestrou a seleção. O texto ainda está
        # no clipboard do nosso lado, então colamos assim mesmo.
        self._clipboard.set(text)

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
