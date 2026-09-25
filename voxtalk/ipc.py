"""Instância única + comandos externos (ex.: `voxtalk --toggle`) via socket Unix.

Python puro (sem Qt) para o `--toggle` responder rápido quando chamado pelo
atalho do GNOME.
"""

from __future__ import annotations

import os
import socket
import threading
from pathlib import Path
from typing import Callable, Optional


def default_socket_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/voxtalk-{os.getuid()}"
    Path(runtime).mkdir(mode=0o700, parents=True, exist_ok=True)
    return Path(runtime) / "voxtalk.sock"


def send_command(command: str, path: Optional[Path] = None, timeout: float = 1.0) -> bool:
    """Envia um comando para a instância em execução. False se não houver nenhuma."""
    path = path or default_socket_path()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(str(path))
            sock.sendall(command.encode("utf-8") + b"\n")
        return True
    except OSError:
        return False


class InstanceServer:
    """Escuta comandos num socket Unix e chama `on_command` (numa thread própria)."""

    def __init__(self, path: Path, on_command: Callable[[str], None]) -> None:
        self._path = Path(path)
        self._on_command = on_command
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        """False se outra instância já está escutando neste socket."""
        if self._path.exists():
            if send_command("ping", self._path):
                return False
            self._path.unlink()  # socket órfão de uma execução que caiu
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(str(self._path))
        os.chmod(self._path, 0o600)
        sock.listen(4)
        self._sock = sock
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        sock, self._sock = self._sock, None
        if sock is None:
            return
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        sock.close()
        if self._thread is not None:
            self._thread.join(timeout=1)
        try:
            self._path.unlink()
        except FileNotFoundError:
            pass

    def _serve(self) -> None:
        while self._sock is not None:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            with conn:
                conn.settimeout(1.0)
                try:
                    data = conn.recv(256)
                except OSError:
                    continue
            command = data.decode("utf-8", "replace").strip()
            if command and command != "ping":
                try:
                    self._on_command(command)
                except Exception:
                    pass
