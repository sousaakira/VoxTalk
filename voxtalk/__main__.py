"""python -m voxtalk [--toggle]"""

import sys


def main() -> None:
    if "--toggle" in sys.argv[1:]:
        # Chamado pelo atalho do GNOME: avisa a instância aberta, sem carregar Qt
        from voxtalk.ipc import send_command

        if send_command("toggle"):
            return
    from voxtalk.app import run

    run()


if __name__ == "__main__":
    main()
