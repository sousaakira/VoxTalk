"""Download e verificação do modelo Parakeet local."""

from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from .model_catalog import PARAKEET_FILES, PARAKEET_TOTAL_BYTES, ModelFile
from .settings import AppSettings, PARAKEET_MODEL_ID

ProgressCb = Callable[[float, str], None]  # 0–1, status message

# Why: F9 called model_ready on the UI thread; full SHA-256 of ~670 MB took ~2s
# before the recording bubble appeared. Hot path only checks name+size.
_ready_cache: dict[str, tuple[tuple[tuple[str, int], ...], bool]] = {}


def model_ready(settings: AppSettings) -> bool:
    """Fast check for UI/hotkey — existence + exact size, no hashing."""
    model_dir = settings.parakeet_dir()
    fingerprint = tuple((f.name, f.size_bytes) for f in PARAKEET_FILES)
    cache_key = str(model_dir)
    cached = _ready_cache.get(cache_key)
    if cached is not None and cached[0] == fingerprint and cached[1]:
        # Re-validate cheaply in case files were deleted.
        if all(_present(model_dir / f.name, f) for f in PARAKEET_FILES):
            return True
        _ready_cache.pop(cache_key, None)

    ready = all(_present(model_dir / f.name, f) for f in PARAKEET_FILES)
    _ready_cache[cache_key] = (fingerprint, ready)
    return ready


def invalidate_ready_cache(settings: Optional[AppSettings] = None) -> None:
    if settings is None:
        _ready_cache.clear()
        return
    _ready_cache.pop(str(settings.parakeet_dir()), None)


def model_status_label(settings: AppSettings) -> str:
    if model_ready(settings):
        return f"Pronto ({PARAKEET_MODEL_ID})"
    model_dir = settings.parakeet_dir()
    if not model_dir.exists():
        return "Não baixado (~670 MB)"
    present = sum(1 for f in PARAKEET_FILES if (model_dir / f.name).is_file())
    return f"Incompleto ({present}/{len(PARAKEET_FILES)} ficheiros)"


def _present(path: Path, meta: ModelFile) -> bool:
    try:
        return path.is_file() and path.stat().st_size == meta.size_bytes
    except OSError:
        return False


def _file_hash_ok(path: Path, meta: ModelFile) -> bool:
    if not _present(path, meta):
        return False
    return _sha256(path) == meta.sha256


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def ensure_parakeet(
    settings: AppSettings,
    progress: Optional[ProgressCb] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Path:
    """Garante o modelo no disco (SHA-256 só aqui / re-download)."""
    model_dir = settings.parakeet_dir()
    model_dir.mkdir(parents=True, exist_ok=True)
    done_bytes = 0

    for meta in PARAKEET_FILES:
        dest = model_dir / meta.name
        if _file_hash_ok(dest, meta):
            done_bytes += meta.size_bytes
            if progress:
                progress(
                    done_bytes / PARAKEET_TOTAL_BYTES,
                    f"OK: {meta.name}",
                )
            continue

        partial = dest.with_suffix(dest.suffix + ".partial")
        if progress:
            progress(
                done_bytes / PARAKEET_TOTAL_BYTES,
                f"A baixar {meta.name}…",
            )
        _download_file(
            meta.url,
            partial,
            meta.size_bytes,
            base_done=done_bytes,
            progress=progress,
            cancel_check=cancel_check,
        )
        digest = _sha256(partial)
        if digest != meta.sha256:
            partial.unlink(missing_ok=True)
            raise RuntimeError(
                f"Checksum inválido para {meta.name}: esperado "
                f"{meta.sha256[:12]}…, obtido {digest[:12]}…"
            )
        partial.replace(dest)
        done_bytes += meta.size_bytes
        if progress:
            progress(done_bytes / PARAKEET_TOTAL_BYTES, f"OK: {meta.name}")

    invalidate_ready_cache(settings)
    model_ready(settings)  # warm cache
    if progress:
        progress(1.0, "Modelo local pronto")
    return model_dir


def _download_file(
    url: str,
    dest: Path,
    expected_size: int,
    *,
    base_done: int,
    progress: Optional[ProgressCb],
    cancel_check: Optional[Callable[[], bool]],
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "VoxTalk/0.1 (Parakeet model download)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, dest.open("wb") as out:
            received = 0
            while True:
                if cancel_check and cancel_check():
                    raise RuntimeError("Download cancelado")
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                out.write(chunk)
                received += len(chunk)
                if progress:
                    total = base_done + min(received, expected_size)
                    progress(
                        min(0.999, total / PARAKEET_TOTAL_BYTES),
                        f"A baixar {dest.name} ({received // (1024 * 1024)} MB)…",
                    )
    except urllib.error.URLError as exc:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"Falha no download de {dest.name}: {exc}") from exc
