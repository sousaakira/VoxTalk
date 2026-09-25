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
    def __init__(self, initial: str = "antigo") -> None:
        self.value = initial
        self.history: list[str] = []

    def get(self) -> str:
        return self.value

    def set(self, text: str) -> None:
        self.value = text
        self.history.append(text)


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


def test_restore_clipboard():
    clip = FakeClipboard("antigo")
    inj = ti.TextInjector(device_factory=FakeDevice, clipboard=clip, sleep=lambda _s: None)
    inj.inject("novo", combo="ctrl+v", restore_clipboard=True)
    assert clip.history == ["novo", "antigo"]


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
