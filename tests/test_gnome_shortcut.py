from voxtalk import gnome_shortcut as gs


class FakeGsettings:
    def __init__(self, paths: str = "@as []") -> None:
        self.values = {(gs.MEDIA_KEYS_SCHEMA, "custom-keybindings"): paths}
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> str:
        self.calls.append(args)
        op = args[0]
        if op == "get":
            schema, key = args[1], args[2]
            return self.values.get((schema, key), "''") + "\n"
        if op == "set":
            self.values[(args[1], args[2])] = args[3]
            return ""
        if op == "reset":
            self.values.pop((args[1], args[2]), None)
            return ""
        raise AssertionError(args)


def test_parse_and_format_paths():
    assert gs.parse_paths("@as []") == []
    assert gs.parse_paths("['/a/', '/b/']") == ["/a/", "/b/"]
    assert gs.format_paths(["/a/", "/b/"]) == "['/a/', '/b/']"
    assert gs.format_paths([]) == "@as []"


def test_is_gnome():
    assert gs.is_gnome({"XDG_CURRENT_DESKTOP": "ubuntu:GNOME"})
    assert not gs.is_gnome({"XDG_CURRENT_DESKTOP": "KDE"})
    assert not gs.is_gnome({})


def test_register_appends_path_and_sets_keys():
    fake = FakeGsettings("['/org/x/asense/']")
    gs.register("F9", "voxtalk --toggle", run=fake)
    assert gs.parse_paths(fake.values[(gs.MEDIA_KEYS_SCHEMA, "custom-keybindings")]) == [
        "/org/x/asense/",
        gs.KEYBINDING_PATH,
    ]
    schema = f"{gs.CUSTOM_SCHEMA}:{gs.KEYBINDING_PATH}"
    assert fake.values[(schema, "name")] == "'VoxTalk'"
    assert fake.values[(schema, "command")] == "'voxtalk --toggle'"
    assert fake.values[(schema, "binding")] == "'F9'"


def test_register_is_idempotent():
    fake = FakeGsettings(f"['{gs.KEYBINDING_PATH}']")
    gs.register("<Super>h", "cmd", run=fake)
    assert gs.parse_paths(fake.values[(gs.MEDIA_KEYS_SCHEMA, "custom-keybindings")]) == [
        gs.KEYBINDING_PATH
    ]


def test_unregister_removes_path_and_keeps_others():
    fake = FakeGsettings(f"['/org/x/asense/', '{gs.KEYBINDING_PATH}']")
    gs.unregister(run=fake)
    assert gs.parse_paths(fake.values[(gs.MEDIA_KEYS_SCHEMA, "custom-keybindings")]) == [
        "/org/x/asense/"
    ]


def test_quote_escapes_single_quotes():
    assert gs.gvariant_str("it's") == "'it\\'s'"


def test_toggle_command_uses_absolute_python():
    cmd = gs.toggle_command(python="/opt/v/bin/python", package_root="/opt/voxtalk")
    assert cmd == "env PYTHONPATH=/opt/voxtalk /opt/v/bin/python -m voxtalk --toggle"
