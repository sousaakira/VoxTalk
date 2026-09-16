"""Divide áudio longo em pedaços ~30s (mesma ideia do OfflineAudioChunker do Orca)."""

from __future__ import annotations

import numpy as np

CHUNK_SECONDS = 30
SPLIT_SEARCH_SECONDS = 5
SPLIT_ENERGY_WINDOW_SECONDS = 0.1


def split_offline_audio(audio: np.ndarray, sample_rate: int = 16_000) -> list[np.ndarray]:
    """Corta em silêncios próximos do limite de 30s para não partir palavras."""
    if audio.size == 0:
        return []
    limit = max(1, int(CHUNK_SECONDS * sample_rate))
    if audio.size <= limit:
        return [audio]

    search = int(SPLIT_SEARCH_SECONDS * sample_rate)
    window = max(1, int(SPLIT_ENERGY_WINDOW_SECONDS * sample_rate))
    hop = max(1, window // 2)

    chunks: list[np.ndarray] = []
    offset = 0
    while offset < audio.size:
        remaining = audio.size - offset
        if remaining <= limit:
            chunks.append(audio[offset:])
            break

        end = offset + limit
        search_start = max(offset, end - search)
        best_idx = end
        best_energy = float("inf")
        for start in range(search_start, end - window + 1, hop):
            piece = audio[start : start + window]
            energy = float(np.mean(np.square(piece)))
            if energy < best_energy:
                best_energy = energy
                best_idx = start + window // 2

        chunks.append(audio[offset:best_idx])
        offset = best_idx

    return [c for c in chunks if c.size > 0]
