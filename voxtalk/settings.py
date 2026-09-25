"""Persistência de configuração do VoxTalk (~/.config/voxtalk/config.json)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Literal

Engine = Literal["local", "openai"]
OpenAiModel = Literal["gpt-4o-mini-transcribe", "gpt-4o-transcribe"]
PasteCombo = Literal["auto", "ctrl+v", "ctrl+shift+v"]

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "voxtalk"
CONFIG_PATH = CONFIG_DIR / "config.json"
DEFAULT_MODELS_DIR = (
    Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    / "voxtalk"
    / "models"
)

PARAKEET_MODEL_ID = "parakeet-tdt-0.6b-v3-int8"


@dataclass
class AppSettings:
    engine: Engine = "local"
    openai_model: OpenAiModel = "gpt-4o-mini-transcribe"
    openai_api_key: str = ""
    language: str = "pt-BR"
    auto_copy: bool = True
    models_dir: str = ""
    insert_into_focused: bool = True
    paste_combo: PasteCombo = "auto"  # auto: Ctrl+Shift+V em terminais
    shortcut: str = "F9"  # formato de acelerador do GNOME: "F9", "<Super>h"…
    gnome_shortcut: bool = True

    def resolved_models_dir(self) -> Path:
        raw = (self.models_dir or "").strip()
        return Path(raw).expanduser() if raw else DEFAULT_MODELS_DIR

    def parakeet_dir(self) -> Path:
        return self.resolved_models_dir() / PARAKEET_MODEL_ID


def _coerce(data: dict[str, Any]) -> AppSettings:
    known = {f.name for f in fields(AppSettings)}
    kwargs = {k: v for k, v in data.items() if k in known}
    settings = AppSettings(**kwargs)
    if settings.engine not in ("local", "openai"):
        settings.engine = "local"
    if settings.openai_model not in (
        "gpt-4o-mini-transcribe",
        "gpt-4o-transcribe",
    ):
        settings.openai_model = "gpt-4o-mini-transcribe"
    if settings.paste_combo not in ("auto", "ctrl+v", "ctrl+shift+v"):
        settings.paste_combo = "auto"
    if not str(settings.shortcut).strip():
        settings.shortcut = "F9"
    return settings


def load_settings() -> AppSettings:
    if not CONFIG_PATH.is_file():
        return AppSettings()
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return AppSettings()
        return _coerce(data)
    except (OSError, json.JSONDecodeError):
        return AppSettings()


def save_settings(settings: AppSettings) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = asdict(settings)
    CONFIG_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass
