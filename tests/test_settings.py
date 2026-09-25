from voxtalk.settings import AppSettings, _coerce


def test_defaults_enable_insert_and_gnome_shortcut():
    s = AppSettings()
    assert s.insert_into_focused is True
    assert s.paste_combo == "auto"
    assert s.shortcut == "F9"
    assert s.gnome_shortcut is True


def test_coerce_fixes_invalid_values():
    s = _coerce({"paste_combo": "alt+v", "shortcut": "  "})
    assert s.paste_combo == "auto"
    assert s.shortcut == "F9"


def test_old_config_without_new_keys_loads():
    s = _coerce({"engine": "local", "auto_copy": False})
    assert s.auto_copy is False
    assert s.insert_into_focused is True
