#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LeFilou Rec - enregistreur d'écran ultra léger et entièrement configurable.

Interface Tkinter (quelques dizaines de Mo de RAM) + FFmpeg pour la capture et
l'encodage (encodeurs matériels NVENC / QuickSync / AMF / VAAPI / VideoToolbox
ou x264 en secours). Aucun traitement vidéo n'est fait en Python.
"""
import collections
import glob
import hmac
import http.server
import json
import os
import queue
import re
import shlex
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

APP = "LeFilouRec"
VERSION = "1.0.0"
PLAT = "win" if sys.platform.startswith("win") else ("mac" if sys.platform == "darwin" else "linux")
NOWIN = 0x08000000  # CREATE_NO_WINDOW (Windows)

if PLAT == "win":  # coordonnées d'écran réelles malgré la mise à l'échelle Windows
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


# --------------------------------------------------------------------------- #
#  Configuration
# --------------------------------------------------------------------------- #
def config_dir():
    if PLAT == "win":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    elif PLAT == "mac":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    d = os.path.join(base, APP)
    os.makedirs(d, exist_ok=True)
    return d


CONFIG_DIR = config_dir()
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
LOG_FILE = os.path.join(CONFIG_DIR, "ffmpeg.log")

ICON_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAQAAAAEACAYAAABccqhmAAAGfklEQVR42u3cwU0rMBBFUVfCErGm/3pYpwMQNRARz9yD9Ar4"
    "nnnHDvninAE/b2/v3yLTcvwouwgUlF4EBkovEsfAsEWCEBiuSBACwxQJQmB4IlEIDEwkiIAhiUQhMBiRKAIGIhJFwCBEoggY"
    "gEgUAQcvEkXAgYtEEXDQIlEEHLBIFAEHKxJFwIGKhBFwmCJRABykSBQBBygSRsDhiUQBcHAiYQQcmkgUAAcmEkbAYYlEAXBQ"
    "ImEEHJJIFAAHtCePx+OpcaYBBBxOu+RwAIADUnYoFAFwMAoPhDACDkXpYQAAUXoY1ABwIEoPgzACDkPpYQAAUXwQAEAUHwQA"
    "EMUHwX4AHITigyCMgEPYW3z/RgGA/4fvHAQAG5be+UAAALHFdmYgAEBskZ2hMwRAbGmdq3MFQGxJnbFzBoCFFOcOgMISOl8z"
    "AEBw8ZyteQAguGzO1WwAYLnErABQWCglNTcAWCIxPwBUlkcZzRIAFkbMFACVRVE68wWA5RBzBoClEPMGwOplUCqzB4AFGJmv"
    "j88/xQ48AGDw+4u+GQYIxAAoDPy/Cz8dBAgAYPygbyv9NAwAEABg25CnlH4KBhBYDMCm4U4v/s0QQGAhABuGuq30N2MAgUUA"
    "TB9mpfi3QQABACg/BACg/IpfhqCMwFF+xQdBF4EkAMoPgQ37lAZgkthKPQOC4ivgKL/yQ6CLwPH0V34IdD8KHOVXfgh0ETie"
    "/ooPgu5HgeP2V34IdF8BR/mVHwJdBACg/BAAgPIrPwSKCKwFQPkhUNjB9QDcqq/itRDY+go4bn8AAKD7Cjhuf+WHQPcVcNz+"
    "yg+B7ivguP2VHwLdV8Bx+ys/BLqvgOP2BwAAuq+A4/ZXfgh0XwEAUH4IAED5AQCAIgIAUH4IAGAuAG5/mfQKAIDbX7wCAHDz"
    "YSoMBAAQfv4rCwAqHwOO21/5IdB9BQAAAAAAgOc/AABQ/Bhw3P7KD4HuKwAAAAAAADz/FQMCxY8BAAAAAADg+a8UACh+DDhu"
    "f+WHQPcVAAAAAAAAABAAACAIgCJAAADhXwAqAQDKvwg8nv9KAIDuKwAASgAAAPj8LxAAAAAEAAAAgAAAAAAQAADAV4ACgK1f"
    "BR7fAAgAut8EHM9/kU8AAEAAAAAACAAAAAABAAAAIAAAAAAEAAAAgAAAAAAQAAAAAAIAAABAAAAAAAgAAAAAAQAAACAAAAAA"
    "BAAAAIAAAAAAEAAAwB8EEX8QBAD+JJi4/cMA+BggAPBXgQEgAAAAAAQAAACAAAAAvgkQ3wAAAAACAAD4GCC+AlwJgN8DiM//"
    "7wDwMUA8/wEAAAEAAAAgAAAABGR5+QHgFSBufwAAQAAAAAiI5z8AACAASAFw0/NJQZS/8vwfDYBXgLj9AQAAAcAGAHwMEM9/"
    "AHgFiNsfAF4BsvP2B8Cg55TiKP/m5/8KALwCxO0PAAjI9bc/ALwCxO0PAK8AcfsD4KmHCwG5ufwA8AoQtz8AvALE7Q+AsdIq"
    "WLf8227/lQBAQPnd/ksAuFlchWuVf+PtvxYArwAAuP2XAOAVIG5/AEBARpUfABAQ5QdAZRAKua/8AIAABJR/bfkzAEBA+Tfu"
    "Wg6ASSor68zil27/kQBAQPntFwAgoPye/lUAIKD8yh8HYOJTTanvLH7x6Z8GAALK7/ZfAMDkwSn7HcUvl38FANMHqPh2BwAv"
    "HCIElB8AELji36D49gUAhroSA3sCAMMNQmA/AGDIMQzsBQBGD3rCsJXeTgDAwF8Ggl0AgMEHYLADe8u/HgAL0I7ZA+BpiwAC"
    "8waApVAwcwaA5VA08wVAeklAYKYAsDAKaJYAqC8OCMwPAJZIMc0NAPVlAoFZAcByWS6zAYBFs2zmAQBLZ/HMAAAW0BI6dwBY"
    "SAvpnAFgOdtL6lwBYGFjS+sMAWCBY4vszAAAgthiOx8AQCCy9M4BACC4NP6NAgAQrIydexIAvz8OAgSKHy0/AECg+ABwICBQ"
    "fAAICBQfAAIDpe8AAAEYKH24/ACAgdIDwMHAQOmrAEAACAofLj8AoKDsAHBAcFDyKgAQEAmXHwAicQAgIBIuPwBE4gBAQCRc"
    "fgCIxAGAgEi4/AAQiQMAAZFw+SEgEi8/AETiAEBAJFx+CIjEyw8BkXj5ISASLz8EROLlh4BIvPwQEImXHwIi8fJDQCRefgiI"
    "xMsPApF48SEgovwgEKkXHwQiig8CEcUHgYjiw0BE6WEgSu8HCqLsL/75ATh8oLOibX9TAAAAAElFTkSuQmCC")

PRESETS = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow"]
ALL_HW = ["h264_nvenc", "hevc_nvenc", "h264_qsv", "hevc_qsv", "h264_amf", "hevc_amf",
          "h264_vaapi", "hevc_vaapi", "h264_videotoolbox", "hevc_videotoolbox"]

DEFAULTS = {
    # Vidéo
    "capture_mode": "screen", "region_x": 0, "region_y": 0, "region_w": 1280, "region_h": 720,
    "window_title": "", "monitor_index": 0, "mac_screen_index": 1, "win_capture": "auto",
    "fps": 30, "cursor": True, "out_height": 0,
    "encoder": "auto", "preset": "ultrafast", "rc_mode": "crf", "quality": 23, "bitrate": 6000,
    "gop_seconds": 2, "vaapi_device": "/dev/dri/renderD128",
    # Audio
    "audio_system_on": PLAT == "linux",
    "audio_system_dev": "@DEFAULT_MONITOR@" if PLAT == "linux" else "",
    "audio_system_vol": 100,
    "audio_mic_on": False, "audio_mic_dev": "default" if PLAT == "linux" else "", "audio_mic_vol": 100,
    "audio_separate": False, "audio_codec": "aac", "audio_bitrate": 160,
    # Sortie
    "output_dir": os.path.join(os.path.expanduser("~"), "Movies" if PLAT == "mac" else "Videos", APP),
    "filename_pattern": "Rec_%Y-%m-%d_%H-%M-%S", "container": "mkv", "mp4_fragmented": True,
    "split_minutes": 0, "screenshot_dir": "", "screenshot_format": "png", "open_folder_after": False,
    # Raccourcis & comportement
    "hotkeys_enabled": True, "hotkey_record": "<ctrl>+<alt>+r", "hotkey_screenshot": "<ctrl>+<alt>+s",
    "countdown": 0, "minimize_on_start": True, "beep": True,
    # Performances & avancé
    "priority": "below", "threads": 2, "rtbuf_mb": 64, "thread_queue": 512, "log_level": "warning",
    "ffmpeg_path": "", "extra_output_args": "", "dep_prompt": True,
    # Télécommande (téléphone)
    "remote_enabled": False, "remote_port": 8765, "remote_pin": "", "remote_notify": True,
    "ram_warn": 90, "remote_timeout": 8,
}

CHOICES = {
    "capture_mode": [("screen", "Écran principal"), ("region", "Région personnalisée"),
                     ("window", "Fenêtre par titre (Windows)")],
    "win_capture": [("auto", "Auto (ddagrab si disponible)"), ("ddagrab", "ddagrab (GPU, très léger)"),
                    ("gdigrab", "gdigrab (compatible)")],
    "out_height": [(0, "Résolution d'origine"), (1440, "1440p"), (1080, "1080p"), (720, "720p"),
                   (480, "480p"), (360, "360p")],
    "encoder": [("auto", "Auto (matériel si possible)"),
                ("libx264", "x264 - H.264 (CPU)"), ("libx265", "x265 - HEVC (CPU)"),
                ("h264_nvenc", "NVENC H.264 (Nvidia)"), ("hevc_nvenc", "NVENC HEVC (Nvidia)"),
                ("h264_qsv", "QuickSync H.264 (Intel)"), ("hevc_qsv", "QuickSync HEVC (Intel)"),
                ("h264_amf", "AMF H.264 (AMD)"), ("hevc_amf", "AMF HEVC (AMD)"),
                ("h264_vaapi", "VAAPI H.264 (Linux)"), ("hevc_vaapi", "VAAPI HEVC (Linux)"),
                ("h264_videotoolbox", "VideoToolbox H.264 (macOS)"),
                ("hevc_videotoolbox", "VideoToolbox HEVC (macOS)")],
    "preset": [(p, p) for p in PRESETS],
    "rc_mode": [("crf", "Qualité constante"), ("bitrate", "Débit fixe (kbps)")],
    "audio_codec": [("aac", "AAC"), ("libopus", "Opus"), ("flac", "FLAC (MKV uniquement)")],
    "container": [("mkv", "MKV (le plus sûr en cas de crash)"), ("mp4", "MP4"), ("mov", "MOV")],
    "screenshot_format": [("png", "PNG"), ("jpg", "JPEG")],
    "priority": [("normal", "Normale"), ("below", "Inférieure à la normale (conseillé)"), ("low", "Basse")],
    "log_level": [("error", "error"), ("warning", "warning"), ("info", "info")],
}

def SECTION(title):
    return ("__section__", title, "section", "")


# (clé, libellé, type, aide)
SCHEMA = [
    ("Vidéo", [
        SECTION("Capture"),
        ("capture_mode", "Zone à capturer", "choice", "Écran principal, région ou fenêtre."),
        ("region_x", "Région : X", "int", "Utilisé en mode région."),
        ("region_y", "Région : Y", "int", ""),
        ("region_w", "Région : largeur", "int", ""),
        ("region_h", "Région : hauteur", "int", ""),
        ("window_title", "Titre de la fenêtre", "str", "Titre exact (Windows, mode fenêtre)."),
        ("monitor_index", "Moniteur (ddagrab)", "int", "0 = premier moniteur. Windows."),
        ("mac_screen_index", "Écran (macOS)", "int", "Index avfoundation (souvent 1)."),
        ("win_capture", "Méthode de capture (Windows)", "choice", "ddagrab utilise le GPU : très peu de CPU."),
        ("fps", "Images par seconde", "int", "30 conseillé pour économiser les ressources."),
        ("cursor", "Capturer le curseur", "bool", ""),
        SECTION("Encodage"),
        ("out_height", "Redimensionner la sortie", "choice", "Réduire la résolution diminue fortement la charge."),
        ("encoder", "Encodeur", "choice", "Un encodeur matériel décharge le processeur."),
        ("preset", "Vitesse (preset)", "choice", "ultrafast = CPU minimal, fichiers plus gros."),
        ("rc_mode", "Contrôle du débit", "choice", ""),
        ("quality", "Qualité (CRF/CQ/QP)", "int", "Plus bas = meilleure qualité. 20-28 typique."),
        ("bitrate", "Débit vidéo (kbps)", "int", "Si « Débit fixe »."),
        ("gop_seconds", "Image clé toutes les (s)", "int", ""),
        ("vaapi_device", "Périphérique VAAPI (Linux)", "str", ""),
    ]),
    ("Audio", [
        SECTION("Son du système"),
        ("audio_system_on", "Enregistrer le son du système", "bool", ""),
        ("audio_system_dev", "Périphérique son système", "devchoice",
         "Windows : « Mixage stéréo » ou virtual-audio-capturer. Linux : @DEFAULT_MONITOR@. macOS : BlackHole/Loopback."),
        ("audio_system_vol", "Volume son système (%)", "int", ""),
        SECTION("Micro"),
        ("audio_mic_on", "Enregistrer le micro", "bool", ""),
        ("audio_mic_dev", "Périphérique micro", "devchoice", ""),
        ("audio_mic_vol", "Volume micro (%)", "int", ""),
        SECTION("Format audio"),
        ("audio_separate", "Pistes audio séparées", "bool", "Sinon les deux sources sont mélangées."),
        ("audio_codec", "Codec audio", "choice", ""),
        ("audio_bitrate", "Débit audio (kbps)", "int", ""),
    ]),
    ("Sortie", [
        SECTION("Enregistrements"),
        ("output_dir", "Dossier d'enregistrement", "dir", ""),
        ("filename_pattern", "Nom du fichier", "str", "Codes date : %Y %m %d %H %M %S"),
        ("container", "Format", "choice", ""),
        ("mp4_fragmented", "MP4/MOV résistant aux crashs", "bool", "Fichier lisible même si l'enregistrement plante."),
        ("split_minutes", "Découper tous les (min)", "int", "0 = un seul fichier."),
        ("open_folder_after", "Ouvrir le dossier à la fin", "bool", ""),
        SECTION("Captures d'écran"),
        ("screenshot_dir", "Dossier des captures d'écran", "dir", "Vide = dossier d'enregistrement."),
        ("screenshot_format", "Format des captures", "choice", ""),
    ]),
    ("Raccourcis", [
        SECTION("Raccourcis globaux"),
        ("hotkeys_enabled", "Activer les raccourcis globaux", "bool", "Utilise pynput (X11 sous Linux)."),
        ("hotkey_record", "Démarrer / arrêter", "hotkey", ""),
        ("hotkey_screenshot", "Capture d'écran", "hotkey", ""),
        SECTION("Comportement"),
        ("countdown", "Compte à rebours (s)", "int", "0 = démarrage immédiat."),
        ("minimize_on_start", "Réduire la fenêtre au démarrage", "bool", ""),
        ("beep", "Bip au démarrage / à l'arrêt", "bool", ""),
    ]),
    ("Performances", [
        SECTION("Priorité et mémoire"),
        ("priority", "Priorité de FFmpeg", "choice", "« Basse » peut perdre des images si le CPU est saturé."),
        ("threads", "Threads de l'encodeur CPU", "int", "0 = automatique. 2 est un bon compromis."),
        ("rtbuf_mb", "Tampon temps réel (Mo)", "int", "Capture Windows (gdigrab/dshow)."),
        ("thread_queue", "File d'attente d'entrée", "int", ""),
        SECTION("FFmpeg"),
        ("log_level", "Niveau de log FFmpeg", "choice", ""),
        ("ffmpeg_path", "Chemin de FFmpeg", "file", "Vide = automatique."),
        ("extra_output_args", "Arguments FFmpeg supplémentaires", "str", "Ajoutés avant le fichier de sortie."),
        ("dep_prompt", "Proposer d'installer les composants manquants", "bool", "FFmpeg, etc. Un mot de passe peut être demandé."),
    ]),
    ("Télécommande", [
        SECTION("Téléphone"),
        ("remote_enabled", "Activer la télécommande", "bool", "Le téléphone doit être sur le même Wi-Fi que le PC."),
        ("remote_port", "Port", "int", "Change-le si 8765 est déjà pris."),
        ("remote_pin", "Code PIN", "str", "Demandé par le téléphone (4 caractères minimum)."),
        SECTION("Alertes"),
        ("remote_notify", "Alerter sur le PC si le téléphone se déconnecte", "bool", "Fenêtre + bip, avec la cause probable."),
        ("ram_warn", "Seuil d'alerte mémoire (%)", "int", "Alerte quand la RAM du PC dépasse ce seuil."),
        ("remote_timeout", "Délai avant « déconnecté » (s)", "int", "Sans nouvelles du téléphone pendant ce temps."),
    ]),
]
KIND = {k: kind for _, fields in SCHEMA for k, _, kind, _ in fields if kind != "section"}

MISSING_FFMPEG = {
    "win": "ffmpeg.exe est introuvable. Il doit se trouver à côté de LeFilouRec.exe (inclus dans le zip), "
           "ou indique son chemin dans Performances > Chemin de FFmpeg.",
    "linux": "FFmpeg est introuvable. Installe-le :\n  sudo apt install ffmpeg\n(ou le paquet équivalent de ta distribution).",
    "mac": "FFmpeg est introuvable. Installe-le avec Homebrew :\n  brew install ffmpeg",
}


class MissingFFmpeg(RuntimeError):
    pass


DEP_LABELS = {"ffmpeg": "FFmpeg (obligatoire)", "pactl": "pactl (liste des périphériques audio)",
              "xrandr": "xrandr (détection de l'écran)"}
LINUX_PKGS = {  # commande -> paquet selon le gestionnaire de paquets
    "ffmpeg": {"apt-get": "ffmpeg", "dnf": "ffmpeg-free", "pacman": "ffmpeg", "zypper": "ffmpeg"},
    "pactl": {"apt-get": "pulseaudio-utils", "dnf": "pulseaudio-utils", "pacman": "libpulse",
              "zypper": "pulseaudio-utils"},
    "xrandr": {"apt-get": "x11-xserver-utils", "dnf": "xrandr", "pacman": "xorg-xrandr", "zypper": "xrandr"},
}


def install_command(missing):
    """Commande d'installation (avec fenêtre graphique de mot de passe), ou None."""
    if PLAT == "linux":
        pm = next((p for p in ("apt-get", "dnf", "pacman", "zypper") if shutil.which(p)), None)
        if not pm or not shutil.which("pkexec"):
            return None
        names = " ".join(LINUX_PKGS[m][pm] for m in missing if m in LINUX_PKGS)
        inner = {"apt-get": f"apt-get update; DEBIAN_FRONTEND=noninteractive apt-get install -y {names}",
                 "dnf": f"dnf install -y {names}",
                 "pacman": f"pacman -S --noconfirm --needed {names}",
                 "zypper": f"zypper --non-interactive install {names}"}[pm]
        return ["pkexec", "sh", "-c", inner]
    if "ffmpeg" not in missing:
        return None
    if PLAT == "win" and shutil.which("winget"):
        return ["winget", "install", "-e", "--id", "Gyan.FFmpeg",
                "--accept-source-agreements", "--accept-package-agreements"]
    if PLAT == "mac":
        brew = next((p for p in ("/opt/homebrew/bin/brew", "/usr/local/bin/brew") if os.path.isfile(p)), None)
        if brew:
            return [brew, "install", "ffmpeg"]
    return None


def load_config(path=CONFIG_FILE):
    cfg = dict(DEFAULTS)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for k, v in data.items():
            if k in DEFAULTS and isinstance(v, type(DEFAULTS[k])):
                cfg[k] = v
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg, path=CONFIG_FILE):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


def choice_label(key, val):
    for k, label in CHOICES[key]:
        if str(k) == str(val):
            return label
    return CHOICES[key][0][1]


def choice_value(key, label):
    for k, lab in CHOICES[key]:
        if lab == label:
            return k
    return DEFAULTS[key]


# --------------------------------------------------------------------------- #
#  FFmpeg : détection, capacités, construction de la commande
# --------------------------------------------------------------------------- #
def run(cmd, timeout=15):
    kw = {"creationflags": NOWIN} if PLAT == "win" else {}
    try:
        return subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                              timeout=timeout, stdin=subprocess.DEVNULL, **kw)
    except Exception:
        return None


def find_ffmpeg(custom=""):
    if custom and os.path.isfile(custom):
        return custom
    name = "ffmpeg.exe" if PLAT == "win" else "ffmpeg"
    here = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
        else os.path.dirname(os.path.abspath(__file__))
    dirs = [here, os.path.join(here, "bin"), os.path.join(here, "_internal")]
    if PLAT != "win":
        dirs += ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"]
    else:
        dirs.append(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Links"))
    for d in dirs:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return shutil.which("ffmpeg")


class Caps:
    """Encodeurs / filtres disponibles dans le FFmpeg utilisé."""

    def __init__(self, ff):
        self.encoders, self.filters, self.hw_ok = set(), set(), {}
        r = run([ff, "-hide_banner", "-encoders"])
        for line in (r.stdout.splitlines() if r else []):
            p = line.split()
            if len(p) >= 2 and p[0].startswith("V"):
                self.encoders.add(p[1])
        r = run([ff, "-hide_banner", "-filters"])
        for line in (r.stdout.splitlines() if r else []):
            p = line.split()
            if len(p) >= 2:
                self.filters.add(p[1])


def family(enc):
    if enc == "libx264":
        return "x264"
    if enc == "libx265":
        return "x265"
    return enc.split("_", 1)[1]


def is_hevc(enc):
    return enc == "libx265" or enc.startswith("hevc")


def probe(ff, enc, vaapi_dev):
    """Teste réellement un encodeur (la présence dans -encoders ne garantit pas le matériel)."""
    cmd = [ff, "-hide_banner", "-loglevel", "error"]
    vf = "format=nv12"
    if enc.endswith("_vaapi"):
        cmd += ["-vaapi_device", vaapi_dev]
        vf += ",hwupload"
    cmd += ["-f", "lavfi", "-i", "color=c=black:s=320x240:r=10:d=0.5", "-vf", vf,
            "-frames:v", "5", "-c:v", enc, "-f", "null", "-"]
    r = run(cmd, 25)
    return bool(r and r.returncode == 0)


def pick_auto(ff, caps, cfg):
    order = {"win": ["h264_nvenc", "h264_amf", "h264_qsv"],
             "linux": ["h264_nvenc", "h264_vaapi", "h264_qsv"],
             "mac": ["h264_videotoolbox"]}[PLAT]
    for enc in order:
        if enc in caps.encoders:
            if enc not in caps.hw_ok:
                caps.hw_ok[enc] = probe(ff, enc, cfg["vaapi_device"])
            if caps.hw_ok[enc]:
                return enc
    return "libx264"


def primary_geometry(root):
    """(largeur, hauteur, x, y) de l'écran principal en pixels."""
    if PLAT == "win":
        try:
            u = ctypes.windll.user32
            return u.GetSystemMetrics(0), u.GetSystemMetrics(1), 0, 0
        except Exception:
            pass
    elif PLAT == "linux":
        r = run(["xrandr", "--current"], 5)
        if r and r.stdout:
            lines = [l for l in r.stdout.splitlines() if " connected" in l]
            lines.sort(key=lambda l: " primary " not in l)
            for l in lines:
                m = re.search(r"(\d+)x(\d+)\+(\d+)\+(\d+)", l)
                if m:
                    return tuple(int(v) for v in m.groups())
    return root.winfo_screenwidth(), root.winfo_screenheight(), 0, 0


def list_audio_devices(ff):
    names = []
    if PLAT == "win" and ff:
        r = run([ff, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"])
        text = r.stderr if r else ""
        names = re.findall(r'"([^"]+)"\s+\(audio\)', text)
        if not names:  # anciens FFmpeg
            sect = text.split("DirectShow audio devices", 1)[-1] if "DirectShow audio devices" in text else ""
            names = [n for n in re.findall(r'"([^"]+)"', sect) if not n.startswith("@device")]
    elif PLAT == "linux":
        names = ["@DEFAULT_MONITOR@", "default"]
        r = run(["pactl", "list", "short", "sources"], 5)
        for line in (r.stdout.splitlines() if r else []):
            p = line.split("\t")
            if len(p) > 1:
                names.append(p[1])
    elif PLAT == "mac" and ff:
        r = run([ff, "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""])
        audio = False
        for line in (r.stderr.splitlines() if r else []):
            low = line.lower()
            if "audio devices" in low:
                audio = True
            elif "video devices" in low:
                audio = False
            elif audio:
                m = re.search(r"\[(\d+)\]\s+(.+)$", line)
                if m:
                    names.append(f"{m.group(1)}: {m.group(2)}")
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def video_input(caps, cfg, geom):
    """Arguments d'entrée vidéo + filtres propres à la méthode de capture."""
    fps, cur, mode = max(1, cfg["fps"]), (1 if cfg["cursor"] else 0), cfg["capture_mode"]
    gw, gh, gx, gy = geom
    if mode == "region":
        x, y, w, h = cfg["region_x"], cfg["region_y"], cfg["region_w"], cfg["region_h"]
    else:
        x, y, w, h = gx, gy, gw, gh
    w, h = max(2, w - w % 2), max(2, h - h % 2)
    tq = str(max(8, cfg["thread_queue"]))
    a, vf = [], []
    if PLAT == "win":
        method = cfg["win_capture"]
        if mode == "window":
            method = "gdigrab"
        elif method == "auto":
            method = "ddagrab" if "ddagrab" in caps.filters else "gdigrab"
        if method == "ddagrab":
            opts = f"ddagrab=output_idx={cfg['monitor_index']}:framerate={fps}:draw_mouse={cur}"
            if mode == "region":
                opts += f":video_size={w}x{h}:offset_x={x}:offset_y={y}"
            a += ["-f", "lavfi", "-i", opts]
            vf += ["hwdownload", "format=bgra"]
        else:
            a += ["-rtbufsize", f"{max(8, cfg['rtbuf_mb'])}M", "-f", "gdigrab", "-framerate", str(fps),
                  "-draw_mouse", str(cur)]
            if mode == "window":
                a += ["-i", "title=" + cfg["window_title"]]
            else:
                a += ["-offset_x", str(x), "-offset_y", str(y), "-video_size", f"{w}x{h}", "-i", "desktop"]
    elif PLAT == "linux":
        disp = os.environ.get("DISPLAY", ":0")
        a += ["-thread_queue_size", tq, "-f", "x11grab", "-framerate", str(fps), "-draw_mouse", str(cur),
              "-video_size", f"{w}x{h}", "-i", f"{disp}+{x},{y}"]
    else:
        a += ["-thread_queue_size", tq, "-f", "avfoundation", "-framerate", str(fps),
              "-capture_cursor", str(cur), "-i", f"{cfg['mac_screen_index']}:none"]
        if mode == "region":
            vf.append(f"crop={w}:{h}:{x}:{y}")
    return a, vf


def video_codec_args(cfg, enc, fps):
    fam, q, br = family(enc), cfg["quality"], max(100, cfg["bitrate"])
    use_q = cfg["rc_mode"] == "crf"
    idx = PRESETS.index(cfg["preset"]) if cfg["preset"] in PRESETS else 0
    a = ["-c:v", enc]
    rate = ["-b:v", f"{br}k", "-maxrate", f"{br}k", "-bufsize", f"{br * 2}k"]
    if fam in ("x264", "x265"):
        a += ["-preset", cfg["preset"]]
        a += ["-crf", str(q)] if use_q else rate
        if fam == "x265":
            a += ["-x265-params", "log-level=error"]
        if cfg["threads"] > 0:
            a += ["-threads", str(cfg["threads"])]
    elif fam == "nvenc":
        a += ["-preset", f"p{idx + 1}"]
        a += ["-rc", "vbr", "-cq", str(q), "-b:v", "0"] if use_q else rate
    elif fam == "qsv":
        a += ["-preset", ["veryfast", "veryfast", "veryfast", "faster", "fast", "medium", "slow"][idx]]
        a += ["-global_quality", str(q)] if use_q else ["-b:v", f"{br}k"]
    elif fam == "amf":
        a += ["-quality", ["speed", "speed", "speed", "balanced", "balanced", "balanced", "quality"][idx]]
        a += ["-rc", "cqp", "-qp_i", str(q), "-qp_p", str(q), "-qp_b", str(q)] if use_q else ["-b:v", f"{br}k"]
    elif fam == "vaapi":
        a += ["-qp", str(q)] if use_q else ["-b:v", f"{br}k"]
    elif fam == "videotoolbox":
        a += ["-realtime", "1"]
        a += ["-q:v", str(max(1, min(100, 100 - q * 2)))] if use_q else ["-b:v", f"{br}k"]
    a += ["-g", str(fps * max(1, cfg["gop_seconds"]))]
    if is_hevc(enc) and cfg["container"] in ("mp4", "mov"):
        a += ["-tag:v", "hvc1"]
    return a


def build_record_cmd(ff, cfg, caps, geom, out_arg):
    """Retourne (commande, encodeur utilisé)."""
    fps = max(1, cfg["fps"])
    enc = cfg["encoder"]
    if enc == "auto":
        enc = pick_auto(ff, caps, cfg)
    fam = family(enc)
    vin, vf = video_input(caps, cfg, geom)

    srcs = []
    for tag in ("system", "mic"):
        dev = cfg[f"audio_{tag}_dev"].strip()
        if cfg[f"audio_{tag}_on"] and dev:
            srcs.append((dev, max(0, cfg[f"audio_{tag}_vol"]) / 100.0))
    tq = str(max(8, cfg["thread_queue"]))
    ain = []
    for dev, _ in srcs:
        if PLAT == "win":
            ain += ["-thread_queue_size", tq, "-f", "dshow", "-i", "audio=" + dev]
        elif PLAT == "linux":
            ain += ["-thread_queue_size", tq, "-f", "pulse", "-i", dev]
        else:
            ain += ["-thread_queue_size", tq, "-f", "avfoundation", "-i", ":" + dev.split(":")[0].strip()]

    cmd = [ff, "-hide_banner", "-loglevel", cfg["log_level"], "-nostats", "-y"]
    if fam == "vaapi":
        cmd += ["-vaapi_device", cfg["vaapi_device"]]
    cmd += vin + ain

    if cfg["out_height"] > 0:
        vf.append(f"scale=-2:{cfg['out_height']}:flags=fast_bilinear")
    vf.append("format=" + ("yuv420p" if fam in ("x264", "x265") else "nv12"))
    if fam == "vaapi":
        vf.append("hwupload")

    n = len(srcs)
    if n == 0:
        cmd += ["-map", "0:v", "-an"]
    elif n == 1:
        cmd += ["-map", "0:v", "-map", "1:a"]
        if srcs[0][1] != 1.0:
            cmd += ["-af", f"volume={srcs[0][1]:.2f}"]
    elif cfg["audio_separate"]:
        cmd += ["-map", "0:v", "-map", "1:a", "-map", "2:a"]
        for i, (_, v) in enumerate(srcs):
            if v != 1.0:
                cmd += [f"-filter:a:{i}", f"volume={v:.2f}"]
    else:
        fc = (f"[1:a]volume={srcs[0][1]:.2f}[a1];[2:a]volume={srcs[1][1]:.2f}[a2];"
              f"[a1][a2]amix=inputs=2:duration=longest:dropout_transition=0,volume=2[aout]")
        cmd += ["-filter_complex", fc, "-map", "0:v", "-map", "[aout]"]

    cmd += ["-vf", ",".join(vf)] + video_codec_args(cfg, enc, fps)
    if n:
        cmd += ["-c:a", cfg["audio_codec"], "-ar", "48000", "-ac", "2"]
        if cfg["audio_codec"] != "flac":
            cmd += ["-b:a", f"{max(32, cfg['audio_bitrate'])}k"]

    ext, split = cfg["container"], cfg["split_minutes"]
    frag = "+frag_keyframe+empty_moov+default_base_moof"
    if cfg["extra_output_args"].strip():
        cmd += shlex.split(cfg["extra_output_args"], posix=(PLAT != "win"))
    if split > 0:
        seg = {"mkv": "matroska", "mp4": "mp4", "mov": "mov"}[ext]
        cmd += ["-f", "segment", "-segment_time", str(split * 60), "-reset_timestamps", "1",
                "-segment_format", seg]
        if cfg["mp4_fragmented"] and ext in ("mp4", "mov"):
            cmd += ["-segment_format_options", "movflags=" + frag]
    elif cfg["mp4_fragmented"] and ext in ("mp4", "mov"):
        cmd += ["-movflags", frag]
    cmd.append(out_arg)
    return cmd, enc


def fmt_size(n):
    return f"{n / 1048576:.1f} Mo" if n < 1 << 30 else f"{n / (1 << 30):.2f} Go"


# --------------------------------------------------------------------------- #
#  Mémoire du PC + télécommande réseau (serveur HTTP local)
# --------------------------------------------------------------------------- #
def ram_percent():
    """Pourcentage de RAM utilisée (-1 si inconnu)."""
    try:
        if PLAT == "win":
            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MS()
            m.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return float(m.dwMemoryLoad)
        if PLAT == "linux":
            info = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    k, v = line.split(":", 1)
                    info[k] = int(v.split()[0])
            return round(100 * (1 - info["MemAvailable"] / info["MemTotal"]), 1)
        total = int(run(["sysctl", "-n", "hw.memsize"], 3).stdout)
        out = run(["vm_stat"], 3).stdout
        page = int(re.search(r"page size of (\d+)", out).group(1))

        def pages(name):
            m = re.search(name + r":\s+(\d+)", out)
            return int(m.group(1)) if m else 0
        avail = (pages("Pages free") + pages("Pages inactive") + pages("Pages speculative")) * page
        return round(100 * (1 - avail / total), 1)
    except Exception:
        return -1.0


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


REMOTE_HTML = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<title>LeFilou Remote</title>
<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,sans-serif;background:#14141a;color:#eee;display:flex;flex-direction:column;align-items:center;min-height:100vh;padding:20px}
h1{font-size:18px;margin:6px 0 2px}
#conn{font-size:13px;color:#9a9;margin-bottom:12px}
#conn.bad{color:#f66}
#time{font-size:56px;font-variant-numeric:tabular-nums;margin:18px 0 4px}
#size{color:#999;margin-bottom:22px}
button{width:100%;max-width:420px;border:0;border-radius:16px;padding:22px;font-size:20px;font-weight:600;color:#fff;background:#e22832;margin:8px 0}
button.stop{background:#444}
button.sec{background:#2b2b36;font-size:16px;padding:16px}
button:disabled{opacity:.5}
.bar{width:100%;max-width:420px;height:10px;background:#2b2b36;border-radius:6px;overflow:hidden;margin:18px auto 0}
#ramfill{height:100%;width:0;background:#3c9;transition:width .4s}
#ramtxt{font-size:13px;color:#999;margin-top:6px}
#alert{display:none;background:#7a1620;border-radius:12px;padding:12px;margin-top:14px}
#login{display:none;width:100%;max-width:420px;text-align:center}
input{width:100%;padding:16px;font-size:22px;text-align:center;border-radius:12px;border:1px solid #333;background:#1f1f28;color:#fff;letter-spacing:6px;margin-bottom:8px}
#msg{min-height:20px;color:#9bd;margin-top:8px;font-size:14px;text-align:center}
</style></head><body>
<h1>&#9679; LeFilou Rec - t&eacute;l&eacute;commande</h1>
<div id="conn"></div>
<div id="login"><p>Entre le code PIN affich&eacute; sur le PC</p>
<input id="pin" type="tel" inputmode="numeric" autocomplete="off"><button id="ok">Se connecter</button></div>
<div id="main" style="display:none;width:100%;max-width:420px;text-align:center">
<div id="time">00:00:00</div><div id="size"></div>
<button id="rec">&#9679; D&eacute;marrer</button>
<button id="shot" class="sec">Capture d'&eacute;cran</button>
<div class="bar"><div id="ramfill"></div></div><div id="ramtxt"></div>
<div id="alert"></div></div>
<div id="msg"></div>
<script>
var $=function(i){return document.getElementById(i)},pin=localStorage.getItem("pin")||"",snap=null,fails=0;
function fmt(s){var h=Math.floor(s/3600),m=Math.floor(s/60)%60,x=s%60;return [h,m,x].map(function(v){return String(v).padStart(2,"0")}).join(":")}
function api(path,method){
  var ctl=new AbortController(),t=setTimeout(function(){ctl.abort()},4000);
  return fetch(path,{method:method||"GET",headers:{"X-Pin":pin},signal:ctl.signal,cache:"no-store"}).then(function(r){
    clearTimeout(t);return r.json().then(function(j){return {status:r.status,data:j}})});
}
function showLogin(){$("login").style.display="block";$("main").style.display="none"}
function poll(){
  api("/api/status").then(function(r){
    if(r.status===401||r.status===429){pin="";localStorage.removeItem("pin");showLogin();
      $("conn").textContent="";$("msg").textContent=r.data.error||"";return}
    snap=r.data;fails=0;
    $("login").style.display="none";$("main").style.display="block";
    $("conn").textContent="Connect\u00e9 au PC";$("conn").className="";
    $("time").textContent=fmt(snap.elapsed);
    $("size").textContent=snap.recording?(snap.size/1048576).toFixed(1)+" Mo - "+snap.encoder:snap.status;
    var b=$("rec");
    b.textContent=snap.stopping?"Finalisation\u2026":(snap.recording?"\u25a0 Arr\u00eater":"\u25cf D\u00e9marrer");
    b.className=snap.recording?"stop":"";b.disabled=snap.stopping;
    var ram=snap.ram;
    $("ramfill").style.width=Math.max(0,ram)+"%";
    $("ramfill").style.background=snap.ram_alert?"#e55":"#3c9";
    $("ramtxt").textContent="RAM du PC : "+(ram<0?"?":ram.toFixed(0)+" %");
    var a=$("alert");
    if(snap.ram_alert){a.style.display="block";a.textContent="M\u00e9moire du PC presque satur\u00e9e ("+ram.toFixed(0)+" %)";
      if(navigator.vibrate)navigator.vibrate(200)}else a.style.display="none";
  }).catch(function(){fails++;$("conn").textContent="Connexion perdue\u2026 ("+fails+")";$("conn").className="bad"});
}
function act(p){
  api(p,"POST").then(function(r){
    $("msg").textContent=r.data.ok?"OK":(r.data.error||"");
    setTimeout(function(){$("msg").textContent=""},2000);poll();
  }).catch(function(){$("msg").textContent="\u00c9chec de la commande"});
}
$("rec").onclick=function(){act(snap&&snap.recording?"/api/stop":"/api/start")};
$("shot").onclick=function(){act("/api/screenshot")};
$("ok").onclick=function(){pin=$("pin").value.trim();localStorage.setItem("pin",pin);poll()};
if(pin){poll()}else{showLogin()}
setInterval(function(){if(pin)poll()},2000);
</script></body></html>"""


class RemoteServer:
    """Mini serveur HTTP : page de télécommande + API protégée par PIN (réseau local)."""

    def __init__(self, app, port, pin):
        self.app, self.pin = app, pin
        self.fails = {}
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype="application/json"):
                data = body.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", ctype + "; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def _auth(self):
                ip = self.client_address[0]
                count, until = outer.fails.get(ip, (0, 0.0))
                if until > time.monotonic():
                    self._send(429, json.dumps({"error": "Trop d'essais, attends une minute."}))
                    return False
                if hmac.compare_digest(self.headers.get("X-Pin", "").encode(), outer.pin.encode()):
                    outer.fails.pop(ip, None)
                    return True
                count += 1
                outer.fails[ip] = (0, time.monotonic() + 60) if count >= 5 else (count, 0.0)
                self._send(401, json.dumps({"error": "PIN incorrect"}))
                return False

            def do_GET(self):
                if self.path in ("/", "/index.html"):
                    self._send(200, REMOTE_HTML, "text/html")
                elif self.path.startswith("/api/status"):
                    if self._auth():
                        outer.app.remote_seen(self.client_address[0])
                        self._send(200, json.dumps(outer.app.snap))
                else:
                    self._send(404, json.dumps({"error": "introuvable"}))

            def do_POST(self):
                cmds = {"/api/start": "remote_start", "/api/stop": "remote_stop", "/api/screenshot": "shot"}
                if self.path in cmds:
                    if self._auth():
                        outer.app.remote_seen(self.client_address[0])
                        outer.app.q.put((cmds[self.path], None))
                        self._send(200, json.dumps({"ok": True}))
                else:
                    self._send(404, json.dumps({"error": "introuvable"}))

        self.httpd = http.server.ThreadingHTTPServer(("0.0.0.0", port), Handler)

    def start(self):
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


# --------------------------------------------------------------------------- #
#  Raccourcis clavier (pynput)
# --------------------------------------------------------------------------- #
def hk_mod(kb, k):
    K = kb.Key
    if k in (K.ctrl, K.ctrl_l, K.ctrl_r):
        return "<ctrl>"
    if k in (K.alt, K.alt_l, K.alt_r, getattr(K, "alt_gr", None)):
        return "<alt>"
    if k in (K.shift, K.shift_l, K.shift_r):
        return "<shift>"
    if k in (K.cmd, K.cmd_l, K.cmd_r):
        return "<cmd>"
    return None


def hk_key(kb, k):
    if isinstance(k, kb.Key):
        return f"<{k.name}>"
    ch = getattr(k, "char", None)
    if ch and ch.isprintable() and ch.strip():
        return ch.lower()
    vk = getattr(k, "vk", None)
    if vk is not None:
        if 65 <= vk <= 90 or 97 <= vk <= 122:
            return chr(vk).lower()
        if 48 <= vk <= 57:
            return chr(vk)
        return f"<{vk}>"
    return str(k)


# --------------------------------------------------------------------------- #
#  Interface
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
#  Thème (sombre, léger : uniquement ttk)
# --------------------------------------------------------------------------- #
THEME = {"bg": "#14141a", "panel": "#1c1c24", "field": "#262631", "line": "#3a3a48", "fg": "#ececf1",
         "muted": "#8b8b99", "accent": "#e22832", "accent_h": "#ff3d47", "ok": "#35c58b"}


def apply_theme(root):
    t = THEME
    fams = set(tkfont.families(root))
    pref = {"win": ["Segoe UI"], "mac": ["Helvetica Neue", "Helvetica"],
            "linux": ["Ubuntu", "Noto Sans", "Cantarell", "DejaVu Sans"]}[PLAT]
    fam = next((f for f in pref if f in fams), None)
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        f = tkfont.nametofont(name)
        if fam:
            f.configure(family=fam)
        f.configure(size=10)
    base = tkfont.nametofont("TkDefaultFont")
    bold, title, timef, small = base.copy(), base.copy(), base.copy(), base.copy()
    bold.configure(weight="bold")
    title.configure(size=17, weight="bold")
    timef.configure(size=34, weight="bold")
    small.configure(size=9, weight="bold")
    root._fonts = (bold, title, timef, small)  # garde les références

    root.configure(bg=t["bg"])
    root.option_add("*TCombobox*Listbox.background", t["field"])
    root.option_add("*TCombobox*Listbox.foreground", t["fg"])
    root.option_add("*TCombobox*Listbox.selectBackground", t["accent"])
    root.option_add("*TCombobox*Listbox.selectForeground", "white")

    st = ttk.Style(root)
    st.theme_use("clam")
    st.configure(".", background=t["bg"], foreground=t["fg"], fieldbackground=t["field"],
                 bordercolor=t["line"], lightcolor=t["bg"], darkcolor=t["bg"], troughcolor=t["panel"],
                 focuscolor=t["bg"], selectbackground=t["accent"], selectforeground="white",
                 insertcolor=t["fg"])
    st.configure("TFrame", background=t["bg"])
    st.configure("Card.TFrame", background=t["panel"])
    st.configure("TLabel", background=t["bg"], foreground=t["fg"])
    st.configure("Muted.TLabel", foreground=t["muted"])
    st.configure("Title.TLabel", font=title)
    st.configure("Card.TLabel", background=t["panel"])
    st.configure("CardMuted.TLabel", background=t["panel"], foreground=t["muted"])
    st.configure("Time.TLabel", background=t["panel"], font=timef)
    st.configure("Section.TLabel", foreground=t["accent"], font=small)
    st.configure("TSeparator", background=t["line"])

    st.configure("TNotebook", background=t["bg"], borderwidth=0, tabmargins=(0, 0, 0, 0))
    st.configure("TNotebook.Tab", background=t["panel"], foreground=t["muted"], padding=(16, 9),
                 borderwidth=0, bordercolor=t["bg"], lightcolor=t["panel"], darkcolor=t["panel"])
    st.map("TNotebook.Tab",
           background=[("selected", t["bg"]), ("active", t["field"])],
           foreground=[("selected", t["fg"]), ("active", t["fg"])],
           lightcolor=[("selected", t["bg"])], darkcolor=[("selected", t["bg"])],
           expand=[("selected", (0, 0, 0, 0))])

    def button(style, bg, hover, fg, font=None, pad=(14, 8)):
        kw = dict(background=bg, foreground=fg, borderwidth=0, focusthickness=0, padding=pad,
                  relief="flat", lightcolor=bg, darkcolor=bg, bordercolor=bg)
        if font:
            kw["font"] = font
        st.configure(style, **kw)
        st.map(style, background=[("pressed", hover), ("active", hover)],
               lightcolor=[("pressed", hover), ("active", hover)],
               darkcolor=[("pressed", hover), ("active", hover)],
               bordercolor=[("pressed", hover), ("active", hover)])
    button("TButton", t["field"], t["line"], t["fg"])
    button("Accent.TButton", t["accent"], t["accent_h"], "white", bold, (18, 9))

    st.configure("TEntry", fieldbackground=t["field"], foreground=t["fg"], insertcolor=t["fg"],
                 bordercolor=t["line"], lightcolor=t["field"], darkcolor=t["field"], padding=(6, 5))
    st.map("TEntry", bordercolor=[("focus", t["accent"])], lightcolor=[("focus", t["field"])])
    st.configure("TCombobox", fieldbackground=t["field"], background=t["field"], foreground=t["fg"],
                 arrowcolor=t["fg"], bordercolor=t["line"], lightcolor=t["field"], darkcolor=t["field"],
                 padding=(6, 5), selectbackground=t["field"], selectforeground=t["fg"])
    st.map("TCombobox", fieldbackground=[("readonly", t["field"])], foreground=[("readonly", t["fg"])],
           selectbackground=[("readonly", t["field"])], selectforeground=[("readonly", t["fg"])],
           background=[("active", t["line"])], bordercolor=[("focus", t["accent"])])
    st.configure("TCheckbutton", background=t["bg"], foreground=t["fg"], indicatorbackground=t["field"],
                 indicatorforeground="white", upperbordercolor=t["line"], lowerbordercolor=t["line"])
    st.map("TCheckbutton", background=[("active", t["bg"])],
           indicatorbackground=[("selected", t["accent"]), ("!selected", t["field"])],
           indicatorforeground=[("selected", "white")])
    st.configure("TScrollbar", background=t["field"], troughcolor=t["bg"], bordercolor=t["bg"],
                 arrowcolor=t["muted"], lightcolor=t["field"], darkcolor=t["field"], relief="flat",
                 gripcount=0)
    st.map("TScrollbar", background=[("active", t["line"])])
    for name, color in (("RamOk", t["ok"]), ("RamBad", t["accent"])):
        st.configure(f"{name}.Horizontal.TProgressbar", background=color, troughcolor=t["field"],
                     bordercolor=t["field"], lightcolor=color, darkcolor=color, thickness=8)


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"LeFilou Rec {VERSION}")
        self.root.geometry("860x720")
        self.root.minsize(780, 620)
        apply_theme(self.root)
        self._logo = self._icon = None
        try:
            self._icon = tk.PhotoImage(data=ICON_B64)
            self.root.iconphoto(True, self._icon)
            self._logo = self._icon.subsample(4, 4)
        except tk.TclError:
            pass
        self._rec_state = self._rec_hover = False
        self.cfg = load_config()
        if not self.cfg["remote_pin"]:
            self.cfg["remote_pin"] = f"{secrets.randbelow(10 ** 6):06d}"
            save_config(self.cfg)
        self.vars, self.devboxes = {}, []
        self.q = queue.Queue()
        self.proc = self.logf = self.hk = self.cap_listener = self.cap_win = None
        self.recording = self.stopping = self.counting = False
        self.t0 = self.last_tick = 0.0
        self.remote, self.remote_url, self.remote_last = None, "", 0.0
        self.phone_connected = self.phone_lost = self.ram_alerted = False
        self.ram_samples = collections.deque(maxlen=20)
        self.last_size = 0
        self.snap = {"recording": False, "stopping": False, "elapsed": 0, "size": 0, "status": "Prêt.",
                     "encoder": "", "ram": -1.0, "ram_alert": False}
        self._bold = None
        self.caps = self.caps_ff = None
        self.out_prefix = self.out_ext = ""
        self.enc_used = ""
        self._build()
        self.refresh_devices()
        self.apply_hotkeys()
        self.apply_remote()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(250, self.pump)
        if self.cfg["dep_prompt"]:
            self.root.after(800, self.check_deps)

    # ---- construction de l'interface ------------------------------------- #
    def _build(self):
        t = THEME
        head = ttk.Frame(self.root, padding=(18, 14, 18, 2))
        head.pack(fill="x")
        if self._logo:
            ttk.Label(head, image=self._logo).pack(side="left")
        titles = ttk.Frame(head)
        titles.pack(side="left", padx=12)
        ttk.Label(titles, text="LeFilou Rec", style="Title.TLabel").pack(anchor="w")
        ttk.Label(titles, text="Enregistreur d'écran léger", style="Muted.TLabel").pack(anchor="w")

        nb = self.nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=14, pady=(8, 6))
        self.canvases, self.cur_canvas = {}, None

        main = ttk.Frame(nb, padding=(18, 14))
        nb.add(main, text="Enregistrer")
        card = ttk.Frame(main, style="Card.TFrame", padding=(20, 18))
        card.pack(fill="x")
        c = self.rec_canvas = tk.Canvas(card, width=128, height=128, bg=t["panel"], highlightthickness=0,
                                        bd=0, cursor="hand2")
        c.pack()
        c.bind("<Button-1>", lambda e: self.toggle())
        c.bind("<Enter>", lambda e: self.draw_rec(hover=True))
        c.bind("<Leave>", lambda e: self.draw_rec(hover=False))
        self.lbl_cta = ttk.Label(card, text="Cliquer pour démarrer", style="CardMuted.TLabel")
        self.lbl_cta.pack(pady=(4, 0))
        self.lbl_time = ttk.Label(card, text="00:00:00", style="Time.TLabel")
        self.lbl_time.pack(pady=(10, 0))
        self.lbl_size = ttk.Label(card, text="", style="CardMuted.TLabel")
        self.lbl_size.pack()
        self.lbl_status = ttk.Label(card, text="Prêt.", style="Card.TLabel", wraplength=680, justify="center")
        self.lbl_status.pack(pady=(10, 0))
        row = ttk.Frame(main)
        row.pack(pady=14)
        ttk.Button(row, text="Capture d'écran", command=self.screenshot).pack(side="left", padx=4)
        ttk.Button(row, text="Ouvrir le dossier", command=self.open_folder).pack(side="left", padx=4)
        ram = ttk.Frame(main)
        ram.pack(fill="x", pady=(2, 0))
        self.lbl_ram = ttk.Label(ram, text="RAM du PC", style="Muted.TLabel")
        self.lbl_ram.pack(anchor="w")
        self.ram_bar = ttk.Progressbar(ram, style="RamOk.Horizontal.TProgressbar", maximum=100,
                                       mode="determinate")
        self.ram_bar.pack(fill="x", pady=(4, 0))
        self.lbl_hint = ttk.Label(main, text="", style="Muted.TLabel")
        self.lbl_hint.pack(side="bottom", anchor="w", pady=(0, 2))

        for title, fields in SCHEMA:
            outer, tab = self._scroll_tab()
            nb.add(outer, text=title)
            tab.columnconfigure(2, weight=1)
            for r, (key, label, kind, hint) in enumerate(fields):
                self._field(tab, r, key, label, kind, hint)
            if title == "Performances":
                self._field(tab, len(fields), "", "Outils", "section", "")
                bar = ttk.Frame(tab)
                bar.grid(row=len(fields) + 1, column=0, columnspan=3, sticky="w", padx=4)
                tools = (("Détecter encodeurs / périphériques", self.detect_encoders),
                         ("Voir la commande FFmpeg", self.show_command),
                         ("Journal FFmpeg", self.show_log),
                         ("Dossier de config", lambda: self.open_folder(CONFIG_DIR)))
                for i, (text, cmd) in enumerate(tools):
                    ttk.Button(bar, text=text, command=cmd).grid(row=i // 2, column=i % 2, sticky="ew",
                                                                 padx=3, pady=3)
        nb.bind("<<NotebookTabChanged>>", lambda e: setattr(self, "cur_canvas", self.canvases.get(nb.select())))
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.root.bind_all(ev, self._wheel)

        bottom = ttk.Frame(self.root, padding=(14, 0, 14, 12))
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Sauvegarder les réglages", style="Accent.TButton",
                   command=self.save_settings).pack(side="left")
        ttk.Button(bottom, text="Importer…", command=self.import_cfg).pack(side="left", padx=6)
        ttk.Button(bottom, text="Exporter…", command=self.export_cfg).pack(side="left")
        ttk.Button(bottom, text="Valeurs par défaut", command=self.reset_cfg).pack(side="right")
        foot = ttk.Frame(self.root, padding=(16, 0, 16, 8))
        foot.pack(fill="x")
        self.lbl_remote = ttk.Label(foot, text="", style="Muted.TLabel")
        self.lbl_remote.pack(side="right")
        self.draw_rec(False)
        self.update_hint()

    def _scroll_tab(self):
        outer = ttk.Frame(self.nb)
        canvas = tk.Canvas(outer, bg=THEME["bg"], highlightthickness=0, bd=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas, padding=(14, 6, 14, 14))
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.canvases[str(outer)] = canvas
        return outer, inner

    def _wheel(self, e):
        if self.cur_canvas is not None:
            up = getattr(e, "num", 0) == 4 or getattr(e, "delta", 0) > 0
            self.cur_canvas.yview_scroll(-2 if up else 2, "units")

    def draw_rec(self, recording=None, hover=None):
        if recording is not None:
            self._rec_state = recording
        if hover is not None:
            self._rec_hover = hover
        t, c = THEME, self.rec_canvas
        c.delete("all")
        if self._rec_state:
            c.create_oval(12, 12, 116, 116, outline=t["accent"], width=4)
            c.create_rectangle(44, 44, 84, 84, fill=t["accent"], outline=t["accent"])
            self.lbl_cta.config(text="Cliquer pour arrêter")
        else:
            c.create_oval(12, 12, 116, 116, outline=t["accent_h"] if self._rec_hover else "#f0f0f0", width=4)
            c.create_oval(30, 30, 98, 98, fill=t["accent_h"] if self._rec_hover else t["accent"], outline="")
            self.lbl_cta.config(text="Cliquer pour démarrer")

    def _field(self, parent, row, key, label, kind, hint):
        if kind == "section":
            f = ttk.Frame(parent)
            ttk.Label(f, text=label.upper(), style="Section.TLabel").pack(anchor="w")
            ttk.Separator(f, orient="horizontal").pack(fill="x", pady=(3, 0))
            f.grid(row=row, column=0, columnspan=3, sticky="ew", padx=4, pady=(16 if row else 2, 6))
            return
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="nw", padx=(6, 12), pady=(9, 4))
        cell = ttk.Frame(parent)
        cell.grid(row=row, column=1, columnspan=2, sticky="w", pady=4)
        val = self.cfg[key]
        if kind == "bool":
            v = tk.BooleanVar(value=bool(val))
            w = ttk.Checkbutton(cell, variable=v)
        elif kind == "choice":
            v = tk.StringVar(value=choice_label(key, val))
            w = ttk.Combobox(cell, textvariable=v, state="readonly", width=34,
                             values=[lab for _, lab in CHOICES[key]])
        elif kind == "devchoice":
            v = tk.StringVar(value=str(val))
            w = ttk.Combobox(cell, textvariable=v, width=44)
            self.devboxes.append(w)
        elif kind in ("dir", "file"):
            v = tk.StringVar(value=str(val))
            w = ttk.Frame(cell)
            ttk.Entry(w, textvariable=v, width=40).pack(side="left", fill="x", expand=True)
            ttk.Button(w, text="…", width=3, command=lambda v=v, k=kind: self._browse(v, k)).pack(
                side="left", padx=(4, 0))
        elif kind == "hotkey":
            v = tk.StringVar(value=str(val))
            w = ttk.Frame(cell)
            ttk.Entry(w, textvariable=v, width=26).pack(side="left")
            ttk.Button(w, text="Définir…", command=lambda v=v: self.capture_hotkey(v)).pack(
                side="left", padx=(4, 0))
        else:
            v = tk.StringVar(value=str(val))
            w = ttk.Entry(cell, textvariable=v, width=10 if kind == "int" else 44)
        w.pack(anchor="w")
        if hint:
            ttk.Label(cell, text=hint, style="Muted.TLabel", wraplength=430, justify="left").pack(
                anchor="w", pady=(3, 0))
        self.vars[key] = v

    def _browse(self, var, kind):
        p = filedialog.askdirectory() if kind == "dir" else filedialog.askopenfilename()
        if p:
            var.set(p)

    # ---- configuration ---------------------------------------------------- #
    def collect(self):
        cfg = {}
        for key, default in DEFAULTS.items():
            kind, raw = KIND[key], self.vars[key].get()
            if kind == "bool":
                cfg[key] = bool(raw)
            elif kind == "choice":
                cfg[key] = choice_value(key, raw)
            elif isinstance(default, int):
                try:
                    cfg[key] = int(float(str(raw).replace(",", ".")))
                except ValueError:
                    cfg[key] = default
            else:
                cfg[key] = str(raw).strip()
        cfg["fps"] = max(1, cfg["fps"])
        for k in ("threads", "split_minutes", "countdown", "audio_system_vol", "audio_mic_vol"):
            cfg[k] = max(0, cfg[k])
        return cfg

    def apply_cfg(self, cfg):
        for key, var in self.vars.items():
            kind, val = KIND[key], cfg.get(key, DEFAULTS[key])
            if kind == "bool":
                var.set(bool(val))
            elif kind == "choice":
                var.set(choice_label(key, val))
            else:
                var.set(str(val))

    def save_settings(self):
        self.cfg = self.collect()
        save_config(self.cfg)
        self.apply_hotkeys()
        self.apply_remote()
        self.update_hint()
        self.set_status("Réglages sauvegardés.")

    def import_cfg(self):
        p = filedialog.askopenfilename(filetypes=[("Profil JSON", "*.json")])
        if p:
            self.apply_cfg(load_config(p))
            self.save_settings()

    def export_cfg(self):
        p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("Profil JSON", "*.json")])
        if p:
            save_config(self.collect(), p)

    def reset_cfg(self):
        if messagebox.askyesno("Valeurs par défaut", "Remettre tous les réglages par défaut ?"):
            self.apply_cfg(DEFAULTS)
            self.save_settings()

    def update_hint(self):
        c = self.cfg
        txt = ""
        if c["hotkeys_enabled"]:
            txt = f"Démarrer/arrêter : {c['hotkey_record']}    Capture : {c['hotkey_screenshot']}"
        self.lbl_hint.config(text=txt)

    # ---- périphériques & FFmpeg ------------------------------------------ #
    def ffmpeg(self):
        return find_ffmpeg(self.vars["ffmpeg_path"].get().strip())

    def refresh_devices(self):
        devs = list_audio_devices(self.ffmpeg())
        for b in self.devboxes:
            b["values"] = devs
        if devs and PLAT == "win":
            sysre = re.compile(r"stereo mix|mixage|virtual-audio|what u hear", re.I)
            if not self.vars["audio_system_dev"].get():
                for d in devs:
                    if sysre.search(d):
                        self.vars["audio_system_dev"].set(d)
                        break
            if not self.vars["audio_mic_dev"].get():
                for d in devs:
                    if not sysre.search(d):
                        self.vars["audio_mic_dev"].set(d)
                        break
        return devs

    def detect_encoders(self):
        ff = self.ffmpeg()
        if not ff:
            messagebox.showerror("FFmpeg", MISSING_FFMPEG[PLAT])
            return
        vaapi = self.vars["vaapi_device"].get()
        self.set_status("Détection des encodeurs en cours…")

        def work():
            caps = Caps(ff)
            lines = [f"FFmpeg : {ff}", f"libx264 : {'oui' if 'libx264' in caps.encoders else 'non'}",
                     f"libx265 : {'oui' if 'libx265' in caps.encoders else 'non'}"]
            if PLAT == "win":
                lines.append(f"ddagrab : {'oui' if 'ddagrab' in caps.filters else 'non (gdigrab sera utilisé)'}")
            lines.append("\nEncodeurs matériels (test réel) :")
            for enc in [e for e in ALL_HW if e in caps.encoders]:
                caps.hw_ok[enc] = probe(ff, enc, vaapi)
                lines.append(f"  {'OK ' if caps.hw_ok[enc] else 'KO '} {enc}")
            self.caps, self.caps_ff = caps, ff
            lines.append("\nPériphériques audio :")
            lines += ["  " + d for d in list_audio_devices(ff)]
            self.q.put(("text", ("Détection", "\n".join(lines))))

        threading.Thread(target=work, daemon=True).start()

    def prepare(self, cfg):
        ff = find_ffmpeg(cfg["ffmpeg_path"])
        if not ff:
            raise MissingFFmpeg(MISSING_FFMPEG[PLAT])
        if cfg["capture_mode"] == "window":
            if PLAT != "win":
                raise RuntimeError("Le mode fenêtre n'existe que sous Windows : utilise une région.")
            if not cfg["window_title"]:
                raise RuntimeError("Indique le titre exact de la fenêtre (onglet Vidéo).")
        if cfg["audio_codec"] == "flac" and cfg["container"] != "mkv":
            raise RuntimeError("FLAC n'est utilisable qu'avec le format MKV.")
        if self.caps is None or self.caps_ff != ff:
            self.set_status("Analyse de FFmpeg…")
            self.root.update_idletasks()
            self.caps, self.caps_ff = Caps(ff), ff
        if cfg["encoder"] == "auto":
            self.set_status("Choix de l'encodeur…")
            self.root.update_idletasks()
        geom = primary_geometry(self.root)
        out_arg, prefix, ext = self.make_output(cfg)
        cmd, enc = build_record_cmd(ff, cfg, self.caps, geom, out_arg)
        return cmd, enc, prefix, ext

    def make_output(self, cfg):
        os.makedirs(cfg["output_dir"], exist_ok=True)
        name = re.sub(r'[<>:"/\\|?*%]', "_", time.strftime(cfg["filename_pattern"])) or "Rec"
        ext, base = cfg["container"], os.path.join(cfg["output_dir"], name)
        if cfg["split_minutes"] > 0:
            return f"{base}_%03d.{ext}", base, ext
        path, n = base, 1
        while os.path.exists(f"{path}.{ext}"):
            n += 1
            path = f"{base}_{n}"
        return f"{path}.{ext}", path, ext

    def total_size(self):
        try:
            return sum(os.path.getsize(f) for f in glob.glob(glob.escape(self.out_prefix) + f"*.{self.out_ext}"))
        except OSError:
            return 0

    # ---- enregistrement ---------------------------------------------------- #
    def toggle(self):
        if self.stopping or self.counting:
            return
        if self.recording:
            self.stop()
            return
        n = self.collect()["countdown"]
        if n > 0:
            self.counting = True
            self._tick(n)
        else:
            self.start()

    def _tick(self, n):
        if n <= 0:
            self.counting = False
            self.start()
            return
        self.set_status(f"Démarrage dans {n} s…")
        self.root.after(1000, lambda: self._tick(n - 1))

    def start(self):
        cfg = self.cfg = self.collect()
        save_config(cfg)
        try:
            cmd, enc, self.out_prefix, self.out_ext = self.prepare(cfg)
        except MissingFFmpeg:
            self.set_status("Prêt.")
            self.offer_install(["ffmpeg"])
            return
        except RuntimeError as e:
            self.set_status("Prêt.")
            messagebox.showerror("Impossible de démarrer", str(e))
            return
        self.enc_used = enc
        try:
            self.logf = open(LOG_FILE, "w", encoding="utf-8")
            self.logf.write("CMD: " + " ".join(shlex.quote(c) for c in cmd) + "\n")
            self.logf.flush()
        except OSError:
            self.logf = None
        kw = dict(stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self.logf or subprocess.DEVNULL)
        prio = cfg["priority"]
        if PLAT == "win":
            kw["creationflags"] = NOWIN | {"normal": 0x20, "below": 0x4000, "low": 0x40}[prio]
        else:
            nice = {"normal": 0, "below": 5, "low": 15}[prio]
            if nice and shutil.which("nice"):
                cmd = ["nice", "-n", str(nice)] + cmd
        try:
            self.proc = subprocess.Popen(cmd, **kw)
        except OSError as e:
            messagebox.showerror("Impossible de lancer FFmpeg", str(e))
            self.set_status("Prêt.")
            return
        self.recording = True
        self.t0 = time.monotonic()
        self.draw_rec(True)
        self.set_status(f"Enregistrement en cours — encodeur : {enc}")
        self.beep(True)
        if cfg["minimize_on_start"]:
            self.root.iconify()

    def stop(self):
        if not self.proc or self.stopping:
            return
        self.stopping = True
        self.set_status("Finalisation du fichier…")
        p = self.proc

        def work():
            try:
                p.stdin.write(b"q")
                p.stdin.flush()
            except Exception:
                pass
            try:
                p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
            self.q.put(("stopped", p.returncode))

        threading.Thread(target=work, daemon=True).start()

    def _reset_ui(self):
        self.proc, self.recording, self.stopping = None, False, False
        if self.logf:
            try:
                self.logf.close()
            except OSError:
                pass
            self.logf = None
        self.draw_rec(False)
        self.lbl_time.config(text="00:00:00")

    def log_tail(self, n=12):
        try:
            with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
                return "".join(f.readlines()[-n:])
        except OSError:
            return ""

    def on_stopped(self):
        size = self.last_size = self.total_size()
        self._reset_ui()
        if self.cfg["minimize_on_start"]:
            self.root.deiconify()
        self.beep(False)
        if size == 0:
            self.set_status("Échec de l'enregistrement.")
            messagebox.showerror("Enregistrement vide", "Aucun fichier n'a été produit.\n\n" + self.log_tail())
            return
        self.lbl_size.config(text=fmt_size(size))
        self.set_status(f"Terminé : {self.out_prefix}*.{self.out_ext}")
        if self.cfg["open_folder_after"]:
            self.open_folder()

    def on_crash(self):
        rc = self.proc.returncode
        if rc == 0 and self.total_size() > 0:
            self.on_stopped()
            return
        tail = self.log_tail()
        self._reset_ui()
        if self.cfg["minimize_on_start"]:
            self.root.deiconify()
        self.set_status("FFmpeg s'est arrêté de façon inattendue.")
        messagebox.showerror("FFmpeg s'est arrêté", f"Code de sortie {rc}.\n\n{tail}")

    # ---- captures d'écran -------------------------------------------------- #
    def screenshot(self):
        cfg = self.collect()
        ff = find_ffmpeg(cfg["ffmpeg_path"])
        if not ff:
            messagebox.showerror("FFmpeg", MISSING_FFMPEG[PLAT])
            return
        if self.caps is None or self.caps_ff != ff:
            self.caps, self.caps_ff = Caps(ff), ff
        vin, vf = video_input(self.caps, cfg, primary_geometry(self.root))
        folder = cfg["screenshot_dir"] or cfg["output_dir"]
        os.makedirs(folder, exist_ok=True)
        ext = cfg["screenshot_format"]
        base = os.path.join(folder, time.strftime("Capture_%Y-%m-%d_%H-%M-%S"))
        path, n = f"{base}.{ext}", 1
        while os.path.exists(path):
            n += 1
            path = f"{base}_{n}.{ext}"
        cmd = [ff, "-hide_banner", "-loglevel", "error", "-y"] + vin
        if vf:
            cmd += ["-vf", ",".join(vf)]
        cmd += ["-frames:v", "1"] + (["-q:v", "2"] if ext == "jpg" else []) + [path]

        def work():
            r = run(cmd, 20)
            ok = bool(r and r.returncode == 0 and os.path.exists(path))
            self.q.put(("msg", f"Capture enregistrée : {path}" if ok else
                        "Échec de la capture d'écran :\n" + (r.stderr[-300:] if r else "")))

        threading.Thread(target=work, daemon=True).start()

    # ---- raccourcis -------------------------------------------------------- #
    def apply_hotkeys(self):
        if self.hk:
            try:
                self.hk.stop()
            except Exception:
                pass
            self.hk = None
        if not self.cfg["hotkeys_enabled"]:
            return
        try:
            from pynput import keyboard
        except Exception:
            self.set_status("Raccourcis indisponibles (pynput absent ou pas d'affichage X11).")
            return
        try:
            m = {}
            if self.cfg["hotkey_record"]:
                m[self.cfg["hotkey_record"]] = lambda: self.q.put(("toggle", None))
            if self.cfg["hotkey_screenshot"]:
                m[self.cfg["hotkey_screenshot"]] = lambda: self.q.put(("shot", None))
            self.hk = keyboard.GlobalHotKeys(m)
            self.hk.daemon = True
            self.hk.start()
        except Exception as e:
            messagebox.showwarning("Raccourcis", f"Raccourcis invalides ou indisponibles :\n{e}")

    def capture_hotkey(self, var):
        try:
            from pynput import keyboard
        except Exception:
            messagebox.showwarning("Raccourcis", "pynput n'est pas disponible sur ce système.")
            return
        if self.cap_win:
            return
        win = self.cap_win = tk.Toplevel(self.root, bg=THEME["bg"])
        win.title("Nouveau raccourci")
        ttk.Label(win, text="Appuie sur la combinaison voulue…\n(Échap pour annuler)", padding=24).pack()
        mods = set()
        order = ["<ctrl>", "<alt>", "<shift>", "<cmd>"]

        def on_press(k):
            m = hk_mod(keyboard, k)
            if m:
                mods.add(m)
                return None
            if k == keyboard.Key.esc:
                self.q.put(("hk_cancel", None))
                return False
            combo = "+".join(sorted(mods, key=order.index) + [hk_key(keyboard, k)])
            self.q.put(("hk", (var, combo)))
            return False

        def on_release(k):
            m = hk_mod(keyboard, k)
            if m:
                mods.discard(m)

        self.cap_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self.cap_listener.start()
        win.protocol("WM_DELETE_WINDOW", lambda: self.q.put(("hk_cancel", None)))

    def _close_capture(self):
        if self.cap_listener:
            try:
                self.cap_listener.stop()
            except Exception:
                pass
            self.cap_listener = None
        if self.cap_win:
            self.cap_win.destroy()
            self.cap_win = None

    # ---- télécommande & alertes mémoire ------------------------------------ #
    def apply_remote(self):
        self.ip = local_ip()
        if self.remote:
            try:
                self.remote.stop()
            except Exception:
                pass
            self.remote = None
        self.phone_connected = self.phone_lost = False
        self.remote_last = 0.0
        c = self.cfg
        if c["remote_enabled"]:
            if len(c["remote_pin"]) < 4:
                messagebox.showwarning("Télécommande", "Le code PIN doit faire au moins 4 caractères.")
            else:
                try:
                    self.remote = RemoteServer(self, c["remote_port"], c["remote_pin"])
                    self.remote.start()
                    self.remote_url = f"http://{local_ip()}:{c['remote_port']}"
                except (OSError, OverflowError) as e:
                    self.remote = None
                    messagebox.showwarning("Télécommande", f"Impossible d'ouvrir le port {c['remote_port']} : {e}")
        self.refresh_remote_label()

    def refresh_remote_label(self):
        ip = getattr(self, "ip", "") or local_ip()
        if not self.remote:
            txt = f"IP du PC : {ip}   ·   télécommande désactivée"
        else:
            state = "téléphone connecté" if self.phone_connected else "en attente du téléphone"
            txt = f"{self.remote_url}   ·   PIN {self.cfg['remote_pin']}   ·   {state}"
        self.lbl_remote.config(text=txt)

    def remote_seen(self, ip):  # appelé depuis le thread du serveur
        self.remote_last = time.monotonic()

    def tick(self, now):
        """Appelé une fois par seconde : minuteur, mémoire, état du téléphone."""
        ram = ram_percent()
        self.ram_samples.append(ram)
        warn = max(1, self.cfg["ram_warn"])
        if self.recording and not self.stopping:
            el = int(now - self.t0)
            self.lbl_time.config(text=f"{el // 3600:02d}:{el // 60 % 60:02d}:{el % 60:02d}")
            self.last_size = self.total_size()
            self.lbl_size.config(text=fmt_size(self.last_size))
        alert = ram >= warn
        if ram >= 0:
            self.ram_bar["value"] = ram
            self.ram_bar.configure(style=("RamBad" if alert else "RamOk") + ".Horizontal.TProgressbar")
            self.lbl_ram.config(text=f"RAM du PC : {ram:.0f} %")
        self.snap = {"recording": self.recording, "stopping": self.stopping,
                     "elapsed": int(now - self.t0) if self.recording else 0, "size": self.last_size,
                     "status": self.lbl_status.cget("text"), "encoder": self.enc_used,
                     "ram": ram, "ram_alert": alert}
        if self.remote:
            timeout = max(3, self.cfg["remote_timeout"])
            if self.remote_last and now - self.remote_last <= timeout:
                if self.phone_lost:
                    self.phone_lost = False
                    if self.cfg["remote_notify"]:
                        self.notify("Téléphone reconnecté", "La télécommande fonctionne de nouveau.", bad=False)
                self.phone_connected = True
            elif self.phone_connected:
                self.phone_connected = False
                self.phone_lost = True
                self.on_phone_lost()
            self.refresh_remote_label()
        if alert and (self.recording or self.remote) and not self.ram_alerted:
            self.ram_alerted = True
            if self.cfg["remote_notify"]:
                self.notify("Mémoire du PC presque saturée",
                            f"RAM à {ram:.0f} %. L'enregistrement ou la télécommande risquent de saccader.")
        elif ram < warn - 5:
            self.ram_alerted = False

    def on_phone_lost(self):
        if not self.cfg["remote_notify"]:
            return
        peak = max([r for r in self.ram_samples if r >= 0] + [0.0])
        extra = " L'enregistrement continue sur le PC." if self.recording else ""
        if peak >= self.cfg["ram_warn"]:
            msg = (f"Le téléphone s'est déconnecté, probablement par manque de mémoire : "
                   f"la RAM du PC a atteint {peak:.0f} %.{extra}")
        else:
            msg = (f"Le téléphone s'est déconnecté. La RAM du PC est normale ({peak:.0f} % au plus) : "
                   f"vérifie le Wi-Fi ou la mise en veille du téléphone.{extra}")
        self.notify("Téléphone déconnecté", msg)

    def notify(self, title, text, bad=True):
        self.beep(not bad)
        if PLAT == "linux" and shutil.which("notify-send"):
            threading.Thread(target=run, args=(["notify-send", "-a", "LeFilou Rec", title, text], 5),
                             daemon=True).start()
        try:
            if self._bold is None:
                self._bold = tkfont.nametofont("TkDefaultFont").copy()
                self._bold.configure(weight="bold")
            bg = "#7a1620" if bad else "#1d5c3a"
            w = tk.Toplevel(self.root)
            w.overrideredirect(True)
            try:
                w.attributes("-topmost", True)
            except tk.TclError:
                pass
            f = tk.Frame(w, bg=bg, padx=16, pady=12)
            f.pack()
            tk.Label(f, text=title, bg=bg, fg="white", font=self._bold).pack(anchor="w")
            tk.Label(f, text=text, bg=bg, fg="white", wraplength=360, justify="left").pack(anchor="w")
            w.update_idletasks()
            x = w.winfo_screenwidth() - w.winfo_reqwidth() - 24
            y = w.winfo_screenheight() - w.winfo_reqheight() - 70
            w.geometry(f"+{x}+{y}")
            for widget in (w, f):
                widget.bind("<Button-1>", lambda e, w=w: w.destroy())
            w.after(12000, lambda w=w: w.winfo_exists() and w.destroy())
        except tk.TclError:
            pass

    # ---- composants manquants --------------------------------------------- #
    def check_deps(self):
        missing = []
        if not self.ffmpeg():
            missing.append("ffmpeg")
        if PLAT == "linux":
            missing += [c for c in ("pactl", "xrandr") if not shutil.which(c)]
        if missing:
            self.offer_install(missing)

    def offer_install(self, missing):
        label = ", ".join(DEP_LABELS.get(m, m) for m in missing)
        cmd = install_command(missing)
        if not cmd:
            messagebox.showinfo("Composants manquants", f"Il manque : {label}.\n\n{MISSING_FFMPEG[PLAT]}")
            return
        pwd = {"linux": "Une fenêtre te demandera ton mot de passe.",
               "win": "Windows peut te demander une confirmation.", "mac": ""}[PLAT]
        if not messagebox.askyesno("Composants manquants", f"Il manque : {label}.\n\nL'installer maintenant ? {pwd}"):
            return
        self.set_status("Installation en cours… valide avec ton mot de passe si on te le demande.")

        def work():
            r = run(cmd, 1200)
            out = ((r.stderr or r.stdout) if r else "")[-400:]
            self.q.put(("installed", (bool(r and r.returncode == 0), r.returncode if r else -1, out)))

        threading.Thread(target=work, daemon=True).start()

    # ---- divers ------------------------------------------------------------ #
    def set_status(self, text):
        self.lbl_status.config(text=text)

    def beep(self, start):
        if not self.cfg["beep"]:
            return
        if PLAT == "win":
            import winsound
            seq = (880, 1175) if start else (1175, 660)
            threading.Thread(target=lambda: [winsound.Beep(f, 110) for f in seq], daemon=True).start()
        else:
            self.root.bell()

    def open_folder(self, path=None):
        path = path or self.collect()["output_dir"]
        os.makedirs(path, exist_ok=True)
        try:
            if PLAT == "win":
                os.startfile(path)
            else:
                subprocess.Popen(["open" if PLAT == "mac" else "xdg-open", path])
        except OSError as e:
            messagebox.showerror("Dossier", str(e))

    def show_text(self, title, text):
        w = tk.Toplevel(self.root)
        w.title(title)
        w.geometry("760x380")
        w.configure(bg=THEME["bg"])
        t = tk.Text(w, wrap="word", bg=THEME["field"], fg=THEME["fg"], insertbackground=THEME["fg"],
                    relief="flat", padx=10, pady=10)
        t.insert("1.0", text)
        t.pack(fill="both", expand=True)
        ttk.Button(w, text="Copier", command=lambda: (self.root.clipboard_clear(),
                                                      self.root.clipboard_append(text))).pack(pady=4)

    def show_command(self):
        try:
            cmd, enc, _, _ = self.prepare(self.collect())
        except RuntimeError as e:
            messagebox.showerror("Commande", str(e))
            return
        self.set_status("Prêt.")
        self.show_text(f"Commande FFmpeg (encodeur : {enc})", " ".join(shlex.quote(c) for c in cmd))

    def show_log(self):
        self.show_text("Journal FFmpeg", self.log_tail(200) or "(vide)")

    def pump(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == "toggle":
                    self.toggle()
                elif kind == "shot":
                    self.screenshot()
                elif kind == "remote_start":
                    if not (self.recording or self.stopping or self.counting):
                        self.toggle()
                elif kind == "remote_stop":
                    if self.recording:
                        self.stop()
                elif kind == "stopped":
                    self.on_stopped()
                elif kind == "msg":
                    self.set_status(data)
                elif kind == "installed":
                    ok, rc, tail = data
                    self.caps = None
                    if ok:
                        self.refresh_devices()
                        self.set_status("Installation terminée : tu peux enregistrer.")
                    elif rc in (126, 127):
                        self.set_status("Installation annulée (mot de passe refusé ou fenêtre fermée).")
                    else:
                        self.set_status("L'installation a échoué.")
                        messagebox.showerror("Installation", f"Code {rc}.\n\n{tail}")
                elif kind == "text":
                    self.set_status("Prêt.")
                    self.refresh_devices()
                    self.show_text(*data)
                elif kind == "hk":
                    var, combo = data
                    var.set(combo)
                    self._close_capture()
                elif kind == "hk_cancel":
                    self._close_capture()
        except queue.Empty:
            pass
        if self.proc and not self.stopping and self.proc.poll() is not None:
            self.on_crash()
        now = time.monotonic()
        if now - self.last_tick >= 1:
            self.last_tick = now
            self.tick(now)
        self.root.after(250, self.pump)

    def on_close(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.write(b"q")
                self.proc.stdin.flush()
                self.proc.wait(timeout=10)
            except Exception:
                self.proc.kill()
        try:
            self.cfg = self.collect()
            save_config(self.cfg)
        except Exception:
            pass
        if self.hk:
            try:
                self.hk.stop()
            except Exception:
                pass
        if self.remote:
            try:
                self.remote.stop()
            except Exception:
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    try:
        App().run()
    except Exception:
        import traceback
        tb = traceback.format_exc()
        try:
            with open(os.path.join(CONFIG_DIR, "crash.log"), "w", encoding="utf-8") as f:
                f.write(tb)
        except OSError:
            pass
        try:
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror("LeFilou Rec - erreur au lancement",
                                 tb[-1500:] + f"\n\nJournal : {CONFIG_DIR}")
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
