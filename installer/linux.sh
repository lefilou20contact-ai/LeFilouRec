#!/usr/bin/env bash
# Crée le .deb et l'AppImage à partir de dist/LeFilouRec (binaire PyInstaller unique).
# Usage : bash installer/linux.sh 1.0.0   (à lancer depuis la racine du dépôt)
set -euo pipefail
VER="${1:-0.0.0}"
BIN="dist/LeFilouRec"
DESKTOP="[Desktop Entry]
Type=Application
Name=LeFilou Rec
Comment=Enregistreur d'écran léger et configurable
Exec=EXECPATH
Icon=lefilourec
Categories=AudioVideo;Recorder;
Terminal=false"

# ---------- .deb ----------
D=pkg/deb
rm -rf pkg
mkdir -p "$D/DEBIAN" "$D/opt/lefilourec" "$D/usr/bin" "$D/usr/share/applications" \
  "$D/usr/share/icons/hicolor/256x256/apps"
install -m755 "$BIN" "$D/opt/lefilourec/LeFilouRec"
ln -s /opt/lefilourec/LeFilouRec "$D/usr/bin/lefilourec"
install -m644 icon.png "$D/usr/share/icons/hicolor/256x256/apps/lefilourec.png"
echo "${DESKTOP/EXECPATH//usr/bin/lefilourec}" > "$D/usr/share/applications/lefilourec.desktop"
cat > "$D/DEBIAN/control" <<EOT
Package: lefilourec
Version: $VER
Section: video
Priority: optional
Architecture: amd64
Depends: ffmpeg
Maintainer: LeFilou2.0 <noreply@users.noreply.github.com>
Description: Enregistreur d'écran léger et configurable
 Interface légère, encodage matériel via FFmpeg, raccourcis clavier.
EOT
dpkg-deb --build --root-owner-group "$D" LeFilouRec-linux-amd64.deb

# ---------- AppImage ----------
A=pkg/AppDir
mkdir -p "$A"
install -m755 "$BIN" "$A/LeFilouRec"
install -m644 icon.png "$A/lefilourec.png"
echo "${DESKTOP/EXECPATH/LeFilouRec}" > "$A/lefilourec.desktop"
cat > "$A/AppRun" <<'EOF'
#!/bin/sh
exec "$(dirname "$(readlink -f "$0")")/LeFilouRec" "$@"
EOF
chmod +x "$A/AppRun"

# Install appimagetool from Ubuntu when available; fall back to the official release.
if ! command -v appimagetool >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y appimagetool || true
fi

if command -v appimagetool >/dev/null 2>&1; then
  APPIMAGETOOL="$(command -v appimagetool)"
else
  APPIMAGETOOL="/tmp/appimagetool"
  curl --fail --location --retry 10 --retry-all-errors --retry-delay 5 \
    --connect-timeout 20 --max-time 300 -o "$APPIMAGETOOL" \
    "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
  chmod +x "$APPIMAGETOOL"
fi

ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGETOOL" "$A" LeFilouRec-linux-x86_64.AppImage
chmod +x LeFilouRec-linux-x86_64.AppImage
ls -la LeFilouRec-linux-*
