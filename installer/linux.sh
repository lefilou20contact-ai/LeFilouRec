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

APPIMAGETOOL_URLS=(
  "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
  "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
)

if [ ! -x pkg/appimagetool ]; then
  mkdir -p pkg
  for url in "${APPIMAGETOOL_URLS[@]}"; do
    echo "Téléchargement de appimagetool depuis: $url"
    if curl --fail --location --retry 5 --retry-all-errors --retry-delay 5 \
      --connect-timeout 20 --max-time 300 -o pkg/appimagetool "$url"; then
      break
    fi
    echo "Échec du téléchargement depuis $url, tentative suivante..." >&2
    rm -f pkg/appimagetool
  done
fi

if [ ! -x pkg/appimagetool ]; then
  echo "Impossible de télécharger appimagetool. Vérifie la disponibilité du binaire sur GitHub." >&2
  exit 1
fi

chmod +x pkg/appimagetool
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 pkg/appimagetool $A LeFilouRec-linux-x86_64.AppImage
chmod +x LeFilouRec-linux-x86_64.AppImage
ls -la LeFilouRec-linux-*
