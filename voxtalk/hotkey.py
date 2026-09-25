"""Listener de atalho global (funciona com a janela em segundo plano).

O `pynput` só é importado quando o listener é de fato iniciado: no GNOME/Wayland
o atalho vem do gsettings e o pacote não precisa estar instalado.
"""

from __future__ import annotations

from typing import Any, Callable, Optional


# Tecla padrão: F9 (pouco usada pelo sistema; troque em DEFAULT_HOTKEY se quiser)
DEFAULT_HOTKEY = {"f9"}
HOTKEY_LABEL = "F9"


class GlobalHotkey:
    """Dispara um callback quando a combinação/tecla é pressionada."""

    def __init__(
        self,
        on_trigger: Callable[[], None],
        combo: Optional[set] = None,
    ) -> None:
        self._on_trigger = on_trigger
        self._combo = combo or set(DEFAULT_HOTKEY)
        self._pressed: set = set()
        self._keyboard: Any = None
        self._listener: Optional[Any] = None
        self._fired = False

    def start(self) -> None:
        if self._listener is not None:
            return
        from pynput import keyboard

        self._keyboard = keyboard
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _normalize(self, key) -> object:
        """Reduz a tecla a uma string estável ('f9', 'ctrl', 'a'…), para que o
        combo padrão possa ser escrito sem depender do pynput instalado."""
        keyboard = self._keyboard
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            key = keyboard.Key.ctrl
        elif key in (keyboard.Key.shift_l, keyboard.Key.shift_r):
            key = keyboard.Key.shift
        elif key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
            key = keyboard.Key.alt
        if isinstance(key, keyboard.Key):
            return key.name
        return getattr(key, "char", key)

    def _on_press(self, key) -> None:
        k = self._normalize(key)
        self._pressed.add(k)
        if self._combo.issubset(self._pressed) and not self._fired:
            self._fired = True
            try:
                self._on_trigger()
            except Exception:
                pass

    def _on_release(self, key) -> None:
        k = self._normalize(key)
        self._pressed.discard(k)
        if not self._combo.issubset(self._pressed):
            self._fired = False


def hotkey_label() -> str:
    return HOTKEY_LABEL
