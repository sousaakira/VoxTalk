import subprocess
import sys

import pytest

from voxtalk.hotkey import DEFAULT_HOTKEY, HOTKEY_LABEL, GlobalHotkey, hotkey_label

keyboard = pytest.importorskip("pynput.keyboard")


def _hotkey(combo=None):
    """GlobalHotkey com o módulo pynput já ligado, sem abrir listener real."""
    fired = []
    hotkey = GlobalHotkey(on_trigger=lambda: fired.append(1), combo=combo)
    hotkey._keyboard = keyboard
    return hotkey, fired


def test_label_is_readable_without_starting_the_listener():
    assert hotkey_label() == HOTKEY_LABEL


def test_default_combo_matches_press_of_default_key():
    hotkey, fired = _hotkey(combo=set(DEFAULT_HOTKEY))
    hotkey._on_press(keyboard.Key.f9)
    assert len(fired) == 1


def test_other_key_does_not_trigger():
    hotkey, fired = _hotkey()
    hotkey._on_press(keyboard.Key.f8)
    assert fired == []


def test_repeat_guard_and_rearm_on_release():
    hotkey, fired = _hotkey()
    hotkey._on_press(keyboard.Key.f9)
    hotkey._on_press(keyboard.Key.f9)  # segurar não repete
    assert len(fired) == 1
    hotkey._on_release(keyboard.Key.f9)
    hotkey._on_press(keyboard.Key.f9)
    assert len(fired) == 2


def test_modifier_left_and_right_normalize_to_the_same_key():
    hotkey, fired = _hotkey(combo={"ctrl", "a"})
    hotkey._on_press(keyboard.Key.ctrl_l)
    hotkey._on_press(keyboard.KeyCode.from_char("a"))
    assert len(fired) == 1
    hotkey._on_release(keyboard.Key.ctrl_l)
    hotkey._on_release(keyboard.KeyCode.from_char("a"))
    hotkey._on_press(keyboard.Key.ctrl_r)
    hotkey._on_press(keyboard.KeyCode.from_char("a"))
    assert len(fired) == 2


def test_extra_key_in_pressed_set_does_not_fire_combo():
    hotkey, fired = _hotkey(combo={"ctrl", "a"})
    hotkey._on_press(keyboard.Key.shift_l)
    hotkey._on_press(keyboard.Key.ctrl_l)
    hotkey._on_press(keyboard.KeyCode.from_char("a"))
    assert len(fired) == 1


def test_trigger_exception_does_not_kill_the_listener():
    def boom():
        raise RuntimeError("falhou")

    hotkey, _ = _hotkey()
    hotkey._on_trigger = boom
    hotkey._on_press(keyboard.Key.f9)  # não levanta
    hotkey._on_release(keyboard.Key.f9)
    hotkey._on_press(keyboard.Key.f9)


def test_app_imports_when_pynput_is_missing():
    """`pynput` é opcional (no GNOME/Wayland o atalho vem do gsettings)."""
    script = (
        "import builtins\n"
        "real = builtins.__import__\n"
        "def fake(name, *a, **k):\n"
        "    if name.split('.')[0] in ('pynput', 'evdev'):\n"
        "        raise ModuleNotFoundError(name)\n"
        "    return real(name, *a, **k)\n"
        "builtins.__import__ = fake\n"
        "import voxtalk.app\n"
        "from voxtalk.hotkey import hotkey_label\n"
        "print(hotkey_label())\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == HOTKEY_LABEL
