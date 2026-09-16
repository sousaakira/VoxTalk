"""STT em nuvem via OpenAI Audio Transcriptions (mesmo caminho remoto do Orca)."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
import wave
from typing import Literal

import numpy as np

OpenAiModel = Literal["gpt-4o-mini-transcribe", "gpt-4o-transcribe"]

OPENAI_URL = "https://api.openai.com/v1/audio/transcriptions"
SAMPLE_RATE = 16_000


def _pcm16_wav(samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak > 0:
        samples = samples / peak * 0.95
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def _sanitize_error(message: str) -> str:
    import re

    message = re.sub(r"\bsk-[A-Za-z0-9_-]+", "[redacted]", message)
    message = re.sub(
        r"\bBearer\s+[A-Za-z0-9._~+/=-]+",
        "Bearer [redacted]",
        message,
        flags=re.I,
    )
    return message.strip() or "OpenAI transcription request failed"


def transcribe_openai(
    audio: np.ndarray,
    *,
    api_key: str,
    model: OpenAiModel = "gpt-4o-mini-transcribe",
    language: str | None = None,
) -> str:
    key = (api_key or "").strip()
    if not key:
        raise RuntimeError(
            "Chave da API OpenAI não configurada. "
            "Abra Configurações e cole a chave, ou volte para o modo local."
        )
    if audio.size == 0:
        return ""

    wav = _pcm16_wav(np.ascontiguousarray(audio, dtype=np.float32))
    boundary = "----VoxTalkBoundary7MA4YWxkTrZu0gW"
    lang = (language or "").strip()
    # OpenAI espera código curto (pt, en…); locale pt-BR → pt
    lang_code = lang.split("-")[0].lower() if lang else ""

    fields: list[tuple[str, str]] = [
        ("model", model),
        ("response_format", "json"),
    ]
    if lang_code:
        fields.append(("language", lang_code))

    body = io.BytesIO()
    for name, value in fields:
        body.write(f"--{boundary}\r\n".encode())
        body.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.write(f"{value}\r\n".encode())

    body.write(f"--{boundary}\r\n".encode())
    body.write(
        b'Content-Disposition: form-data; name="file"; filename="dictation.wav"\r\n'
    )
    body.write(b"Content-Type: audio/wav\r\n\r\n")
    body.write(wav)
    body.write(b"\r\n")
    body.write(f"--{boundary}--\r\n".encode())
    payload = body.getvalue()

    req = urllib.request.Request(
        OPENAI_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "VoxTalk/0.1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            err = json.loads(detail)
            msg = err.get("error", {}).get("message") or detail
        except json.JSONDecodeError:
            msg = detail or str(exc)
        raise RuntimeError(
            f"OpenAI transcription failed: {_sanitize_error(str(msg))}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Falha ao contactar OpenAI: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Resposta OpenAI inválida") from exc

    text = data.get("text")
    if isinstance(text, str):
        return text.strip()
    err = data.get("error") or {}
    if isinstance(err, dict) and isinstance(err.get("message"), str):
        raise RuntimeError(_sanitize_error(err["message"]))
    raise RuntimeError("OpenAI transcription response did not include text")
