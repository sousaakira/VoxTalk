#!/usr/bin/env bash
# Gera o pacote .deb do VoxTalk para instalar no sistema.
# Uso: ./packaging/build-deb.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${VOXTALK_VERSION:-0.2.2}"
ARCH="$(dpkg --print-architecture)"
PKG_NAME="voxtalk"
DEB_NAME="${PKG_NAME}_${VERSION}_${ARCH}.deb"
OUT_DIR="${ROOT}/dist"
STAGE="${OUT_DIR}/stage"

echo "==> Preparando staging em ${STAGE}"
rm -rf "${STAGE}"
mkdir -p \
  "${STAGE}/DEBIAN" \
  "${STAGE}/opt/voxtalk" \
  "${STAGE}/usr/bin" \
  "${STAGE}/usr/share/applications" \
  "${STAGE}/usr/share/icons/hicolor/scalable/apps" \
  "${STAGE}/usr/share/doc/${PKG_NAME}"

echo "==> Copiando código"
cp -a "${ROOT}/voxtalk" "${STAGE}/opt/voxtalk/"
cp -a "${ROOT}/requirements.txt" "${STAGE}/opt/voxtalk/"
cp -a "${ROOT}/pyproject.toml" "${STAGE}/opt/voxtalk/"
# remove caches
find "${STAGE}/opt/voxtalk" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
find "${STAGE}/opt/voxtalk" -type f -name '*.pyc' -delete 2>/dev/null || true

echo "==> Criando venv com dependências (inclui sherpa-onnx)"
python3 -m venv "${STAGE}/opt/voxtalk/venv"
"${STAGE}/opt/voxtalk/venv/bin/pip" install --upgrade pip -q
"${STAGE}/opt/voxtalk/venv/bin/pip" install -r "${ROOT}/requirements.txt"

echo "==> Launcher, desktop e ícone"
install -m 755 "${ROOT}/packaging/voxtalk-launcher" "${STAGE}/usr/bin/voxtalk"
install -m 644 "${ROOT}/packaging/voxtalk.desktop" "${STAGE}/usr/share/applications/voxtalk.desktop"
install -m 644 "${ROOT}/packaging/voxtalk.svg" "${STAGE}/usr/share/icons/hicolor/scalable/apps/voxtalk.svg"
install -m 644 "${ROOT}/README.md" "${STAGE}/usr/share/doc/${PKG_NAME}/README.md"

# Garante que o módulo é importável pelo python do venv
"${STAGE}/opt/voxtalk/venv/bin/pip" install -q --no-deps -e "${STAGE}/opt/voxtalk" 2>/dev/null || true

# copyright curto
cat > "${STAGE}/usr/share/doc/${PKG_NAME}/copyright" <<EOF
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: VoxTalk
Files: *
Copyright: $(date +%Y) VoxTalk contributors
License: MIT
EOF

INSTALLED_SIZE="$(du -sk "${STAGE}/opt" "${STAGE}/usr" | awk '{s+=$1} END {print s}')"

cat > "${STAGE}/DEBIAN/control" <<EOF
Package: ${PKG_NAME}
Version: ${VERSION}
Section: sound
Priority: optional
Architecture: ${ARCH}
Installed-Size: ${INSTALLED_SIZE}
Depends: python3 (>= 3.10), libportaudio2, libxcb-xinerama0
Recommends: wl-clipboard, xsel, xclip, libnotify-bin
Maintainer: VoxTalk <voxtalk@local>
Description: Ditado por voz desktop (Parakeet local + OpenAI opcional)
 VoxTalk grava o microfone com o atalho F9 e transcreve a fala
 em texto. Padrao: Parakeet TDT v3 local (mesmo motor do Orca).
 Opcional: nuvem OpenAI Transcribe. Inclui balao flutuante e atalho global.
EOF

cat > "${STAGE}/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q /usr/share/icons/hicolor 2>/dev/null || true
fi
exit 0
EOF
chmod 755 "${STAGE}/DEBIAN/postinst"

cat > "${STAGE}/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = remove ] || [ "$1" = purge ]; then
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
  fi
fi
exit 0
EOF
chmod 755 "${STAGE}/DEBIAN/postrm"

echo "==> Empacotando ${DEB_NAME}"
mkdir -p "${OUT_DIR}"
dpkg-deb -Zgzip --root-owner-group --build "${STAGE}" "${OUT_DIR}/${DEB_NAME}"

echo
echo "Pronto: ${OUT_DIR}/${DEB_NAME}"
echo "Instalar com:"
echo "  sudo apt install ./${OUT_DIR}/${DEB_NAME}"
echo "  # ou: sudo dpkg -i ${OUT_DIR}/${DEB_NAME} && sudo apt-get install -f"
echo "Remover com:"
echo "  sudo apt remove ${PKG_NAME}"
