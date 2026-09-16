"""Listener de atalho global (funciona com a janela em segundo plano)."""

from __future__ import annotations

from typing import Callable, Optional

from pynput import keyboard


# Tecla padrão: F9 (pouco usada pelo sistema; troque em DEFAULT_HOTKEY se quiser)
DEFAULT_HOTKEY = {keyboard.Key.f9}
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
        self._listener: Optional[keyboard.Listener] = None
        self._fired = False

    def start(self) -> None:
        if self._listener is not None:
            return
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
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            return keyboard.Key.ctrl
        if key in (keyboard.Key.shift_l, keyboard.Key.shift_r):
            return keyboard.Key.shift
        if key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
            return keyboard.Key.alt
        return key

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
