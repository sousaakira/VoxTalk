import struct

import pytest

from voxtalk import text_injector as ti


class FakeDevice:
    def __init__(self) -> None:
        self.events: list[tuple[int, int, int]] = []
        self.closed = False

    def emit(self, etype: int, code: int, value: int) -> None:
        self.events.append((etype, code, value))

    def close(self) -> None:
        self.closed = True


class FakeClipboard:
    def __init__(self, initial: str = "antigo", holds: bool = True) -> None:
        self.value = initial
        self.holds = holds
        self.history: list[str] = []

    def get(self) -> str:
        return self.value

    def set(self, text: str) -> None:
        self.value = text
        self.history.append(text)

    def holds_text(self, text: str) -> bool:
        return self.holds and self.value == text


def _keys(events):
    return [(code, value) for etype, code, value in events if etype == ti.EV_KEY]


def test_ctrl_v_sequence():
    dev = FakeDevice()
    clip = FakeClipboard()
    inj = ti.TextInjector(device_factory=lambda: dev, clipboard=clip, sleep=lambda _s: None)
    inj.inject("olá ç", combo="ctrl+v", restore_clipboard=False)
    assert clip.value == "olá ç"
    assert _keys(dev.events) == [
        (ti.KEY_LEFTCTRL, 1),
        (ti.KEY_V, 1),
        (ti.KEY_V, 0),
        (ti.KEY_LEFTCTRL, 0),
    ]
    assert (ti.EV_SYN, ti.SYN_REPORT, 0) in dev.events


def test_ctrl_shift_v_sequence():
    dev = FakeDevice()
    inj = ti.TextInjector(device_factory=lambda: dev, clipboard=FakeClipboard(), sleep=lambda _s: None)
    inj.inject("x", combo="ctrl+shift+v", restore_clipboard=False)
    assert _keys(dev.events) == [
        (ti.KEY_LEFTCTRL, 1),
        (ti.KEY_LEFTSHIFT, 1),
        (ti.KEY_V, 1),
        (ti.KEY_V, 0),
        (ti.KEY_LEFTSHIFT, 0),
        (ti.KEY_LEFTCTRL, 0),
    ]


@pytest.mark.parametrize("terminal, expected", [(True, ti.KEY_LEFTSHIFT), (False, None)])
def test_auto_combo_uses_ctrl_shift_v_in_terminals(terminal, expected):
    dev = FakeDevice()
    inj = ti.TextInjector(
        device_factory=lambda: dev,
        clipboard=FakeClipboard(),
        sleep=lambda _s: None,
        is_terminal=lambda: terminal,
    )
    inj.inject("x", combo="auto", restore_clipboard=False)
    pressed = [code for code, value in _keys(dev.events) if value == 1]
    assert pressed == [c for c in (ti.KEY_LEFTCTRL, expected, ti.KEY_V) if c is not None]


def test_auto_combo_falls_back_to_ctrl_v_when_detection_fails():
    def boom() -> bool:
        raise RuntimeError("sem X")

    dev = FakeDevice()
    inj = ti.TextInjector(
        device_factory=lambda: dev, clipboard=FakeClipboard(), sleep=lambda _s: None, is_terminal=boom
    )
    inj.inject("x", combo="auto", restore_clipboard=False)
    assert ti.KEY_LEFTSHIFT not in [code for code, _v in _keys(dev.events)]


@pytest.mark.parametrize(
    "wm_class, expected",
    [
        ('"gnome-terminal-server", "Gnome-terminal"', True),
        ('"kitty", "kitty"', True),
        ('"google-chrome", "Google-chrome"', False),
        (None, False),
    ],
)
def test_focused_is_terminal(wm_class, expected):
    assert ti.focused_is_terminal(lambda: wm_class and wm_class.lower()) is expected


def test_restore_clipboard():
    clip = FakeClipboard("antigo")
    inj = ti.TextInjector(device_factory=FakeDevice, clipboard=clip, sleep=lambda _s: None)
    inj.inject("novo", combo="ctrl+v", restore_clipboard=True)
    assert clip.history == ["novo", "antigo"]


def test_restore_skipped_when_previous_had_only_an_image():
    """Clipboard só de imagem -> paste() devolve "": restaurar apagaria o usuário."""
    clip = FakeClipboard("")
    inj = ti.TextInjector(device_factory=FakeDevice, clipboard=clip, sleep=lambda _s: None)
    inj.inject("novo", combo="ctrl+v", restore_clipboard=True)
    assert clip.history == ["novo"]


def test_restore_skipped_when_previous_is_blank():
    clip = FakeClipboard("   \n  ")
    inj = ti.TextInjector(device_factory=FakeDevice, clipboard=clip, sleep=lambda _s: None)
    inj.inject("novo", combo="ctrl+v", restore_clipboard=True)
    assert clip.history == ["novo"]


def test_retries_while_another_app_holds_the_selection():
    """Um app que sequestra a seleção é reexpulso antes do Ctrl+V."""
    class Hijack(FakeClipboard):
        def __init__(self):
            super().__init__()
            self.tentativas = 0

        def holds_text(self, text: str) -> bool:
            self.tentativas += 1
            return self.tentativas >= 3

    clip = Hijack()
    dev = FakeDevice()
    inj = ti.TextInjector(device_factory=lambda: dev, clipboard=clip, sleep=lambda _s: None)
    inj.inject("olá", combo="ctrl+v", restore_clipboard=False)
    assert clip.tentativas == 3
    assert clip.value == "olá"
    assert _keys(dev.events)[0] == (ti.KEY_LEFTCTRL, 1)


def test_gives_up_pressing_paste_after_retrying():
    class AlwaysHijacked(FakeClipboard):
        def holds_text(self, text: str) -> bool:
            return False

    clip = AlwaysHijacked()
    dev = FakeDevice()
    inj = ti.TextInjector(device_factory=lambda: dev, clipboard=clip, sleep=lambda _s: None)
    inj.inject("olá", combo="ctrl+v", restore_clipboard=False)
    assert clip.history == ["olá"] * (ti.TextInjector.SET_ATTEMPTS + 1)
    assert _keys(dev.events)  # o Ctrl+V sai mesmo assim


def test_selection_targets_detects_image_advertising(monkeypatch):
    monkeypatch.setattr(
        ti.subprocess,
        "run",
        lambda *a, **k: type(
            "P", (), {"returncode": 0, "stdout": "TARGETS image/png UTF8_STRING\n"}
        )(),
    )
    assert "image/png" in (ti._selection_targets() or [])


def test_holds_text_rejects_a_selection_that_offers_images(monkeypatch):
    monkeypatch.setattr(ti, "_selection_targets", lambda: ["image/png", "UTF8_STRING"])
    clip = ti.PyperclipClipboard()
    clip.set("olá")
    assert clip.holds_text("olá") is False


def test_holds_text_accepts_a_text_only_selection(monkeypatch):
    monkeypatch.setattr(ti, "_selection_targets", lambda: ["TARGETS", "UTF8_STRING"])
    clip = ti.PyperclipClipboard()
    clip.set("olá")
    assert clip.holds_text("olá") is True


def test_device_created_once():
    created = []

    def factory():
        created.append(1)
        return FakeDevice()

    inj = ti.TextInjector(device_factory=factory, clipboard=FakeClipboard(), sleep=lambda _s: None)
    inj.inject("a", combo="ctrl+v", restore_clipboard=False)
    inj.inject("b", combo="ctrl+v", restore_clipboard=False)
    assert created == [1]


def test_permission_error_is_wrapped():
    def factory():
        raise PermissionError(13, "denied", "/dev/uinput")

    clip = FakeClipboard()
    inj = ti.TextInjector(device_factory=factory, clipboard=clip, sleep=lambda _s: None)
    with pytest.raises(ti.InjectionUnavailable):
        inj.inject("a", combo="ctrl+v", restore_clipboard=False)
    assert clip.value == "a"  # texto continua copiado como fallback


def test_ioctl_numbers_match_kernel():
    assert ti.UI_DEV_CREATE == 0x5501
    assert ti.UI_DEV_DESTROY == 0x5502
    assert ti.UI_SET_EVBIT == 0x40045564
    assert ti.UI_SET_KEYBIT == 0x40045565
    assert ti.UI_DEV_SETUP == 0x405C5503


def test_event_struct_size():
    assert struct.calcsize(ti.INPUT_EVENT_FMT) == 24


def test_prefer_xsel_on_x11(monkeypatch):
    chosen = []
    monkeypatch.setenv("DISPLAY", ":1")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(ti.shutil, "which", lambda name: "/usr/bin/xsel")
    monkeypatch.setattr(ti.pyperclip, "set_clipboard", chosen.append)
    ti.prefer_xsel()
    assert chosen == ["xsel"]


def test_prefer_xsel_leaves_wayland_alone(monkeypatch):
    chosen = []
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setattr(ti.pyperclip, "set_clipboard", chosen.append)
    ti.prefer_xsel()
    assert chosen == []
