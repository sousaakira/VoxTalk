import threading

from voxtalk.ipc import InstanceServer, send_command


def test_send_command_without_server_returns_false(tmp_path):
    assert send_command("toggle", tmp_path / "none.sock") is False


def test_server_receives_command(tmp_path):
    path = tmp_path / "vox.sock"
    received = []
    got = threading.Event()

    def on_command(cmd: str) -> None:
        received.append(cmd)
        got.set()

    server = InstanceServer(path, on_command)
    assert server.start() is True
    try:
        assert send_command("toggle", path) is True
        assert got.wait(2)
        assert received == ["toggle"]
    finally:
        server.stop()
    assert not path.exists()


def test_second_server_detects_running_instance(tmp_path):
    path = tmp_path / "vox.sock"
    first = InstanceServer(path, lambda _c: None)
    assert first.start() is True
    try:
        second = InstanceServer(path, lambda _c: None)
        assert second.start() is False
    finally:
        first.stop()


def test_stale_socket_file_is_replaced(tmp_path):
    import socket

    path = tmp_path / "vox.sock"
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(str(path))
    stale.close()  # arquivo fica, ninguém escutando
    server = InstanceServer(path, lambda _c: None)
    assert server.start() is True
    server.stop()
