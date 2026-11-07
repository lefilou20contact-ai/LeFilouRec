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
rm -rf pkg && mkdir -p $D/DEBIAN $D/opt/lefilourec $D/usr/bin $D/usr/share/applications \
  $D/usr/share/icons/hicolor/256x256/apps
install -m755 "$BIN" $D/opt/lefilourec/LeFilouRec
ln -s /opt/lefilourec/LeFilouRec $D/usr/bin/lefilourec
install -m644 icon.png $D/usr/share/icons/hicolor/256x256/apps/lefilourec.png
echo "${DESKTOP/EXECPATH//usr/bin/lefilourec}" > $D/usr/share/applications/lefilourec.desktop
cat > $D/DEBIAN/control <<EOT
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
dpkg-deb --build --root-owner-group $D LeFilouRec-linux-amd64.deb

# ---------- AppImage ----------
A=pkg/AppDir
mkdir -p $A
install -m755 "$BIN" $A/LeFilouRec
install -m644 icon.png $A/lefilourec.png
echo "${DESKTOP/EXECPATH/LeFilouRec}" > $A/lefilourec.desktop
printf '#!/bin/sh\nexec "$(dirname "$(readlink -f "$0")")/LeFilouRec" "$@"\n' > $A/AppRun
chmod +x $A/AppRun
if [ ! -x pkg/appimagetool ]; then
  curl -fsSL -o pkg/appimagetool \
    https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
  chmod +x pkg/appimagetool
fi
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 pkg/appimagetool $A LeFilouRec-linux-x86_64.AppImage
chmod +x LeFilouRec-linux-x86_64.AppImage
ls -la LeFilouRec-linux-*
