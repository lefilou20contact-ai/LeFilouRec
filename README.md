# LeFilou Rec

Enregistreur d'écran **léger** et **entièrement configurable** (Windows, Linux, macOS).
Interface Tkinter (quelques dizaines de Mo de RAM) ; la capture et l'encodage sont faits par FFmpeg,
avec encodeur matériel (NVENC, QuickSync, AMF, VAAPI, VideoToolbox) quand il est disponible, sinon x264 `ultrafast`.

## Compiler sur GitHub
1. Pousse ces fichiers dans un dépôt (`recorder.py`, `make_icon.py`, `requirements.txt`, `installer/`, `.github/`).
2. Pousse un tag : `git tag v1.0.0 && git push origin v1.0.0` (trois nombres). Le workflow **Build** crée une release avec les installateurs :
   - Windows : `LeFilouRec-Setup-windows.exe` (installateur, raccourcis, désinstallation, FFmpeg inclus)
   - Linux : `LeFilouRec-linux-amd64.deb` (installe FFmpeg automatiquement) et `LeFilouRec-linux-x86_64.AppImage` (`chmod +x` puis lancer)
   - macOS : `LeFilouRec-macos.dmg` (glisser dans Applications)
3. Sans tag, « Run workflow » donne les mêmes fichiers dans l'onglet Actions (artefacts zippés par GitHub).

## Télécommande Android
1. Sur le PC : onglet **Télécommande** > cocher « Activer la télécommande » > *Sauvegarder les réglages*. L'adresse et le PIN s'affichent en bas de l'onglet « Enregistrer ».
2. Sur le téléphone (même Wi-Fi) : installe `LeFilouRemote.apk` (release GitHub), entre l'adresse du PC. Sans APK, ouvre simplement cette adresse dans le navigateur.
3. Depuis le téléphone : démarrer / arrêter, capture d'écran, état et RAM du PC.
- Si le téléphone ne donne plus signe de vie, une alerte s'affiche sur le PC avec la cause probable : RAM du PC proche de la saturation, ou autre chose (Wi-Fi, veille du téléphone). L'enregistrement continue sans le téléphone.
- Sécurité : désactivée par défaut, protégée par PIN (5 essais ratés = blocage 1 min), réseau local uniquement, trafic non chiffré. Ne l'expose jamais sur Internet.
- Si le PC est vraiment gelé par manque de RAM, l'alerte peut n'apparaître qu'une fois la mémoire libérée.

## FFmpeg
- **Windows** : `ffmpeg.exe` est inclus dans le zip.
- **Linux** : le `.deb` installe FFmpeg tout seul ; avec l'AppImage : `sudo apt install ffmpeg`.
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
