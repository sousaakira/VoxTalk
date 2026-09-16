"""Fachada de transcrição: local (Parakeet) ou nuvem (OpenAI)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .cloud_transcriber import transcribe_openai
from .local_transcriber import LocalParakeetTranscriber
from .model_catalog import PARAKEET_DESCRIPTION, PARAKEET_LABEL
from .settings import AppSettings

# Mantido para a UI de idioma (hint na nuvem / rótulos).
LANGUAGES: dict[str, str] = {
    "pt-BR": "Português (Brasil)",
    "pt-PT": "Português (Portugal)",
    "en-US": "English (US)",
    "en-GB": "English (UK)",
    "es-ES": "Español",
    "fr-FR": "Français",
    "de-DE": "Deutsch",
    "it-IT": "Italiano",
    "ja-JP": "日本語",
    "zh-CN": "中文",
}

ENGINE_LABELS = {
    "local": f"Local — {PARAKEET_LABEL}",
    "openai": "Nuvem — OpenAI Transcribe",
}


@dataclass
class TranscriptResult:
    text: str
    language: str
    engine: str
    language_probability: float = 1.0


class HybridTranscriber:
    """Padrão: Parakeet local (Orca). Opcional: GPT-4o(-mini) Transcribe."""

    SAMPLE_RATE = 16_000

    def __init__(self) -> None:
        self._local = LocalParakeetTranscriber()

    def unload_local(self) -> None:
        self._local.unload()

    def transcribe(self, audio: np.ndarray, settings: AppSettings) -> TranscriptResult:
        lang = settings.language if settings.language in LANGUAGES else "pt-BR"
        if settings.engine == "openai":
            text = transcribe_openai(
                audio,
                api_key=settings.openai_api_key,
                model=settings.openai_model,
                language=lang,
            )
            return TranscriptResult(text=text, language=lang, engine="openai")

        text = self._local.transcribe(audio, settings)
        return TranscriptResult(text=text, language=lang, engine="local")


# Compat: app antigo importava LightTranscriber
LightTranscriber = HybridTranscriber

__all__ = [
    "ENGINE_LABELS",
    "HybridTranscriber",
    "LANGUAGES",
    "LightTranscriber",
    "PARAKEET_DESCRIPTION",
    "PARAKEET_LABEL",
    "TranscriptResult",
]
