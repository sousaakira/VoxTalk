# VoxTalk

App desktop: atalho no teclado → microfone → texto.

**Padrão: STT local Parakeet TDT v3** (mesmo motor do Orca via `sherpa-onnx`, ~670 MB).  
**Opcional: nuvem OpenAI** (GPT-4o mini / GPT-4o Transcribe) em Configurações.

## Como funciona

1. Inicie o VoxTalk.
2. Na primeira vez com motor local, baixe o modelo Parakeet (~670 MB).
3. Pressione **F9** (ou **Gravar**).
4. Fale; o balão no canto mostra o nível do mic.
5. Ao parar, o texto aparece no balão e na janela (com “Copiar automaticamente”, vai para a área de transferência).

## Configurações

| Opção | Descrição |
|-------|-----------|
| Motor local | Parakeet TDT v3 (offline após o download) |
| Motor nuvem | OpenAI Transcribe — precisa de chave API e internet |
| Idioma | Hint para a nuvem / rótulo na UI |

Config fica em `~/.config/voxtalk/config.json`.  
Modelos em `~/.local/share/voxtalk/models/`.

## Requisitos

- Linux
- Python 3.10+
- Microfone
- ~670 MB de disco para o modelo local (primeira vez)
- PortAudio: `sudo apt install libportaudio2`
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
```

## Atalhos

| Ação | Teclas |
|------|--------|
| Iniciar / parar gravação | `F9` |

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
  bubble.py / hotkey.py
```
