"""Captura de áudio do microfone."""

from __future__ import annotations

from typing import Optional

import numpy as np
import sounddevice as sd


class MicrophoneRecorder:
    """Grava áudio em mono 16 kHz (formato padrão para STT)."""

    SAMPLE_RATE = 16_000
    CHANNELS = 1

    def __init__(self) -> None:
        self._chunks: list[np.ndarray] = []
        self._stream: Optional[sd.InputStream] = None
        self._recording = False

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start(self) -> None:
        if self._recording:
            return
        self._chunks = []
        self._recording = True

        def _callback(indata, frames, time, status) -> None:  # noqa: ARG001
            if status:
                # Overflow/underflow ocasional — segue gravando.
                pass
            if self._recording:
                self._chunks.append(indata.copy())

        self._stream = sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            channels=self.CHANNELS,
            dtype="float32",
            callback=_callback,
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        """Para a gravação e devolve o áudio como array float32 mono."""
        self._recording = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        if not self._chunks:
            return np.zeros(0, dtype=np.float32)

        audio = np.concatenate(self._chunks, axis=0).reshape(-1)
        self._chunks = []
        return audio

    def level(self) -> float:
        """Nível RMS aproximado do último chunk (0–1), para UI."""
        if not self._chunks:
            return 0.0
        chunk = self._chunks[-1].reshape(-1)
        rms = float(np.sqrt(np.mean(np.square(chunk))))
        return min(1.0, rms * 8.0)
