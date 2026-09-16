"""STT local via sherpa-onnx + Parakeet TDT v3 (mesmo stack do Orca)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from .audio_chunker import split_offline_audio
from .model_manager import model_ready
from .settings import AppSettings


class LocalParakeetTranscriber:
    SAMPLE_RATE = 16_000

    def __init__(self) -> None:
        self._recognizer = None
        self._model_dir: Optional[Path] = None

    def is_ready(self, settings: AppSettings) -> bool:
        return model_ready(settings)

    def unload(self) -> None:
        self._recognizer = None
        self._model_dir = None

    def ensure_loaded(self, settings: AppSettings) -> None:
        model_dir = settings.parakeet_dir()
        if self._recognizer is not None and self._model_dir == model_dir:
            return
        if not model_ready(settings):
            raise RuntimeError(
                "Modelo Parakeet ainda não está instalado. "
                "Abra Configurações e baixe o modelo local (~670 MB)."
            )
        try:
            import sherpa_onnx
        except ImportError as exc:
            raise RuntimeError(
                "Pacote sherpa-onnx não instalado. "
                "Rode: pip install sherpa-onnx"
            ) from exc

        encoder = str(model_dir / "encoder.int8.onnx")
        decoder = str(model_dir / "decoder.int8.onnx")
        joiner = str(model_dir / "joiner.int8.onnx")
        tokens = str(model_dir / "tokens.txt")

        self._recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder,
            decoder,
            joiner,
            tokens,
            num_threads=2,
            sample_rate=self.SAMPLE_RATE,
            feature_dim=80,
            decoding_method="greedy_search",
            provider="cpu",
            debug=False,
            model_type="nemo_transducer",
        )
        self._model_dir = model_dir

    def transcribe(self, audio: np.ndarray, settings: AppSettings) -> str:
        self.ensure_loaded(settings)
        assert self._recognizer is not None

        if audio.size == 0:
            return ""

        peak = float(np.max(np.abs(audio)))
        if peak > 0:
            audio = audio / peak * 0.95

        parts: list[str] = []
        for chunk in split_offline_audio(audio, self.SAMPLE_RATE):
            stream = self._recognizer.create_stream()
            # sherpa espera list[float] ou array 1-D float32
            samples = np.ascontiguousarray(chunk, dtype=np.float32)
            stream.accept_waveform(self.SAMPLE_RATE, samples)
            self._recognizer.decode_stream(stream)
            text = (stream.result.text or "").strip()
            if text:
                parts.append(text)

        return " ".join(parts).strip()
