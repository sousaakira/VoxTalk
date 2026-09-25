"""Registra o atalho global como "atalho personalizado" do GNOME (funciona no Wayland).

O GNOME executa `voxtalk --toggle`, que avisa a instância aberta via socket (ipc.py).
"""

from __future__ import annotations

import ast
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Callable, Mapping, Optional

MEDIA_KEYS_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
CUSTOM_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
KEYBINDING_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/voxtalk/"

Runner = Callable[[list[str]], str]


def _gsettings(args: list[str]) -> str:
    return subprocess.run(
        ["gsettings", *args], check=True, capture_output=True, text=True, timeout=5
    ).stdout


def is_gnome(env: Optional[Mapping[str, str]] = None) -> bool:
    env = os.environ if env is None else env
    desktops = env.get("XDG_CURRENT_DESKTOP", "").upper().split(":")
    return "GNOME" in desktops


def parse_paths(raw: str) -> list[str]:
    raw = raw.strip()
    if raw.startswith("@as"):
        raw = raw[3:].strip()
    return [str(p) for p in ast.literal_eval(raw)] if raw else []


def format_paths(paths: list[str]) -> str:
    if not paths:
        return "@as []"
    return "[" + ", ".join(gvariant_str(p) for p in paths) + "]"


def gvariant_str(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def toggle_command(python: Optional[str] = None, package_root: Optional[str] = None) -> str:
    """Comando absoluto (o GNOME não herda o cwd nem o venv do app)."""
    python = python or sys.executable
    package_root = package_root or str(Path(__file__).resolve().parent.parent)
    return " ".join(
        [
            "env",
            "PYTHONPATH=" + shlex.quote(package_root),
            shlex.quote(python),
            "-m",
            "voxtalk",
            "--toggle",
        ]
    )


def _custom_schema() -> str:
    return f"{CUSTOM_SCHEMA}:{KEYBINDING_PATH}"


def register(binding: str, command: str, run: Runner = _gsettings) -> None:
    """Cria/atualiza o atalho. `binding` no formato do GNOME: 'F9', '<Super>h'…"""
    paths = parse_paths(run(["get", MEDIA_KEYS_SCHEMA, "custom-keybindings"]))
    schema = _custom_schema()
    run(["set", schema, "name", gvariant_str("VoxTalk")])
    run(["set", schema, "command", gvariant_str(command)])
    run(["set", schema, "binding", gvariant_str(binding)])
    if KEYBINDING_PATH not in paths:
        run(["set", MEDIA_KEYS_SCHEMA, "custom-keybindings", format_paths(paths + [KEYBINDING_PATH])])


def unregister(run: Runner = _gsettings) -> None:
    paths = parse_paths(run(["get", MEDIA_KEYS_SCHEMA, "custom-keybindings"]))
    if KEYBINDING_PATH in paths:
        paths.remove(KEYBINDING_PATH)
        run(["set", MEDIA_KEYS_SCHEMA, "custom-keybindings", format_paths(paths)])
    schema = _custom_schema()
    for key in ("name", "command", "binding"):
        run(["reset", schema, key])
