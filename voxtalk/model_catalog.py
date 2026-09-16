"""Catálogo do modelo local Parakeet (mesmos arquivos/hashes do Orca)."""

from __future__ import annotations

from dataclasses import dataclass

# Pinned revision + SHA-256 — mirror of orca/src/main/speech/model-download-catalog.ts
_HF_REPO = "csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8"
_HF_REV = "2bda32ec70b097a55adaa07d9a7173915b43cc78"


@dataclass(frozen=True)
class ModelFile:
    name: str
    url: str
    size_bytes: int
    sha256: str


def _hf_url(name: str) -> str:
    from urllib.parse import quote

    return (
        f"https://huggingface.co/{_HF_REPO}/resolve/{_HF_REV}/"
        f"{quote(name)}?download=true"
    )


PARAKEET_FILES: tuple[ModelFile, ...] = (
    ModelFile(
        name="encoder.int8.onnx",
        url=_hf_url("encoder.int8.onnx"),
        size_bytes=652_184_281,
        sha256="acfc2b4456377e15d04f0243af540b7fe7c992f8d898d751cf134c3a55fd2247",
    ),
    ModelFile(
        name="decoder.int8.onnx",
        url=_hf_url("decoder.int8.onnx"),
        size_bytes=11_845_275,
        sha256="179e50c43d1a9de79c8a24149a2f9bac6eb5981823f2a2ed88d655b24248db4e",
    ),
    ModelFile(
        name="joiner.int8.onnx",
        url=_hf_url("joiner.int8.onnx"),
        size_bytes=6_355_277,
        sha256="3164c13fc2821009440d20fcb5fdc78bff28b4db2f8d0f0b329101719c0948b3",
    ),
    ModelFile(
        name="tokens.txt",
        url=_hf_url("tokens.txt"),
        size_bytes=93_939,
        sha256="d58544679ea4bc6ac563d1f545eb7d474bd6cfa467f0a6e2c1dc1c7d37e3c35d",
    ),
)

PARAKEET_TOTAL_BYTES = sum(f.size_bytes for f in PARAKEET_FILES)
PARAKEET_LABEL = "Parakeet TDT v3"
PARAKEET_DESCRIPTION = (
    "Modelo local do Orca (~670 MB). Alta precisão em português e outras "
    "línguas europeias, com pontuação e maiúsculas."
)
