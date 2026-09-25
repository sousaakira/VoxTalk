# VoxTalk

App desktop: atalho no teclado → microfone → texto.

**Padrão: STT local Parakeet TDT v3** (mesmo motor do Orca via `sherpa-onnx`, ~670 MB).  
**Opcional: nuvem OpenAI** (GPT-4o mini / GPT-4o Transcribe) em Configurações.

## Como funciona

1. Inicie o VoxTalk.
2. Na primeira vez com motor local, baixe o modelo Parakeet (~670 MB).
3. Pressione **F9** (ou **Gravar**).
4. Fale; o balão no canto mostra o nível do mic.
5. Ao parar, o texto é **colado no app que está em foco** (editor, navegador, chat…) e também aparece no balão e na janela.

### Inserir no app em foco

Por padrão o VoxTalk põe o texto na área de transferência e simula **Ctrl+V** com um teclado
virtual (`/dev/uinput`). Funciona no Wayland/GNOME, preserva acentos e não depende do layout.

- Terminais costumam colar com **Ctrl+Shift+V** — mude em Configurações → *Colar com*.
- Com “Copiar automaticamente” desligado, a área de transferência anterior é restaurada depois de colar.
- Se a janela do VoxTalk estiver em foco, nada é colado (o texto fica só na janela).

O `/dev/uinput` precisa ser gravável pelo seu usuário. Em muitas distros já é (ACL do systemd-logind).
Se o VoxTalk avisar “Sem acesso a /dev/uinput”:

```bash
echo 'KERNEL=="uinput", TAG+="uaccess"' | sudo tee /etc/udev/rules.d/60-voxtalk-uinput.rules
sudo udevadm control --reload-rules && sudo udevadm trigger /dev/uinput
```

### Atalho global no GNOME (Wayland)

No GNOME o VoxTalk registra sozinho um **atalho personalizado** (Configurações do sistema →
Teclado → Atalhos personalizados → “VoxTalk”) que executa `voxtalk --toggle`. Esse comando
avisa a instância aberta para iniciar/parar a gravação. A tecla (padrão **F9**) muda em
Configurações do VoxTalk, no formato do GNOME: `F9`, `<Super>h`, `<Ctrl><Alt>space`.

Em outros ambientes X11 o atalho usa `pynput` (opcional: `pip install -r requirements-x11.txt`,
que precisa de `python3-dev` para compilar o `evdev`).

## Configurações

| Opção | Descrição |
|-------|-----------|
| Motor local | Parakeet TDT v3 (offline após o download) |
| Motor nuvem | OpenAI Transcribe — precisa de chave API e internet |
| Idioma | Hint para a nuvem / rótulo na UI |
| Inserir no app em foco | Cola o texto onde o cursor está (Ctrl+V ou Ctrl+Shift+V) |
| Atalho (GNOME) | Registra/remove o atalho global e escolhe a tecla |

Config fica em `~/.config/voxtalk/config.json`.  
Modelos em `~/.local/share/voxtalk/models/`.

## Requisitos

- Linux
- Python 3.10+
- Microfone
- ~670 MB de disco para o modelo local (primeira vez)
- PortAudio: `sudo apt install libportaudio2`
- Wayland: `sudo apt install wl-clipboard` (área de transferência)
- Nuvem: chave OpenAI (só se escolher esse motor)

## Pacote .deb

```bash
chmod +x packaging/build-deb.sh
./packaging/build-deb.sh
sudo apt install ./dist/voxtalk_0.2.1_amd64.deb
```

## Desenvolvimento

```bash
cd VoxTalk
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./run.sh
.venv/bin/pip install pytest && .venv/bin/python -m pytest
```

## Atalhos

| Ação | Teclas |
|------|--------|
| Iniciar / parar gravação | `F9` (configurável no GNOME) |
| Alternar de fora (scripts) | `voxtalk --toggle` |

## Estrutura

```
voxtalk/
  app.py               # UI + tray
  settings.py          # config persistida
  settings_dialog.py   # motor local/nuvem + download
  model_catalog.py     # Parakeet (hashes iguais ao Orca)
  model_manager.py     # download + verificação
  local_transcriber.py # sherpa-onnx Parakeet
  cloud_transcriber.py # OpenAI Transcriptions
  transcriber.py       # fachada híbrida
  recorder.py          # microfone
  bubble.py / hotkey.py # balão + atalho pynput (X11 fora do GNOME)
  gnome_shortcut.py    # atalho personalizado do GNOME → voxtalk --toggle
  ipc.py               # instância única + comandos via socket Unix
  text_injector.py     # cola no app em foco via /dev/uinput
```
