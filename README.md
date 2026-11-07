# LeFilou Rec

Enregistreur d'écran **léger** et **entièrement configurable** (Windows, Linux, macOS).
Interface Tkinter (quelques dizaines de Mo de RAM) ; la capture et l'encodage sont faits par FFmpeg,
avec encodeur matériel (NVENC, QuickSync, AMF, VAAPI, VideoToolbox) quand il est disponible, sinon x264 `ultrafast`.

## Compiler sur GitHub
1. Crée un dépôt et pousse ces fichiers (`recorder.py`, `requirements.txt`, `.github/`).
2. Onglet **Actions** > **Build** > *Run workflow* (ou pousse un tag `v1.0.0` pour créer une release avec les 3 versions).
3. Télécharge les artefacts : `LeFilouRec-windows.zip`, `LeFilouRec-linux.tar.gz`, `LeFilouRec-macos.zip`.

## FFmpeg
- **Windows** : `ffmpeg.exe` est inclus dans le zip.
- **Linux** : `sudo apt install ffmpeg` (le programme utilise celui du système).
- **macOS** : `brew install ffmpeg`.
- Sinon, indique le chemin dans *Performances > Chemin de FFmpeg*.

## Réglages pour jouer à Minecraft avec 4 Go de RAM
- Encodeur **Auto** (NVENC / QuickSync / AMF si ta machine en a un) ; clique sur *Détecter encodeurs* pour vérifier.
- 30 images/s, sortie en 720p, preset `ultrafast`, 2 threads, priorité « inférieure à la normale ».
- Windows : garde la méthode **ddagrab** (capture par le GPU).
- Format MKV : le fichier reste lisible même si tout plante.

## Fonctions
Zone (écran / région / fenêtre Windows), FPS, curseur, redimensionnement, encodeur, preset, CRF ou débit,
audio système + micro (mélangés ou pistes séparées), volumes, MKV/MP4/MOV, découpage automatique,
nom de fichier avec codes date, dossier, captures d'écran, raccourcis globaux personnalisables,
compte à rebours, bip, réduction auto, priorité, threads, arguments FFmpeg libres,
import/export de profils JSON, bouton « Voir la commande FFmpeg ».

## Limites connues
- **Linux** : capture via X11 (`x11grab`). Sous Wayland pur, utilise une session X11 ; les raccourcis globaux demandent aussi X11.
- **Windows, son du système** : FFmpeg ne capture pas le son système nativement ; il faut un périphérique « Mixage stéréo » ou `virtual-audio-capturer`.
- **macOS** : autorise *Enregistrement d'écran* et *Accessibilité* (raccourcis) ; son système via BlackHole/Loopback. Application non signée : clic droit > Ouvrir.
- Pas de pause (FFmpeg ne sait pas mettre en pause) : utilise le découpage ou arrête/redémarre.
- Seuls Linux/x264 ont été testés de bout en bout ; Windows et macOS sont écrits d'après la documentation FFmpeg, à vérifier sur ta machine.
- Le FFmpeg inclus sous Windows est une build GPL (BtbN).
