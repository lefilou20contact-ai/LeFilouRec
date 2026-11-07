#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LeFilou Rec - enregistreur d'écran ultra léger et entièrement configurable.

Interface Tkinter (quelques dizaines de Mo de RAM) + FFmpeg pour la capture et
l'encodage (encodeurs matériels NVENC / QuickSync / AMF / VAAPI / VideoToolbox
ou x264 en secours). Aucun traitement vidéo n'est fait en Python.
"""
import glob
import json
import os
import queue
import re
import shlex
import shutil
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
    "ffmpeg_path": "", "extra_output_args": "",
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

# (clé, libellé, type, aide)
SCHEMA = [
    ("Vidéo", [
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
        ("audio_system_on", "Enregistrer le son du système", "bool", ""),
        ("audio_system_dev", "Périphérique son système", "devchoice",
         "Windows : « Mixage stéréo » ou virtual-audio-capturer. Linux : @DEFAULT_MONITOR@. macOS : BlackHole/Loopback."),
        ("audio_system_vol", "Volume son système (%)", "int", ""),
        ("audio_mic_on", "Enregistrer le micro", "bool", ""),
        ("audio_mic_dev", "Périphérique micro", "devchoice", ""),
        ("audio_mic_vol", "Volume micro (%)", "int", ""),
        ("audio_separate", "Pistes audio séparées", "bool", "Sinon les deux sources sont mélangées."),
        ("audio_codec", "Codec audio", "choice", ""),
        ("audio_bitrate", "Débit audio (kbps)", "int", ""),
    ]),
    ("Sortie", [
        ("output_dir", "Dossier d'enregistrement", "dir", ""),
        ("filename_pattern", "Nom du fichier", "str", "Codes date : %Y %m %d %H %M %S"),
        ("container", "Format", "choice", ""),
        ("mp4_fragmented", "MP4/MOV résistant aux crashs", "bool", "Fichier lisible même si l'enregistrement plante."),
        ("split_minutes", "Découper tous les (min)", "int", "0 = un seul fichier."),
        ("screenshot_dir", "Dossier des captures d'écran", "dir", "Vide = dossier d'enregistrement."),
        ("screenshot_format", "Format des captures", "choice", ""),
        ("open_folder_after", "Ouvrir le dossier à la fin", "bool", ""),
    ]),
    ("Raccourcis", [
        ("hotkeys_enabled", "Activer les raccourcis globaux", "bool", "Utilise pynput (X11 sous Linux)."),
        ("hotkey_record", "Démarrer / arrêter", "hotkey", ""),
        ("hotkey_screenshot", "Capture d'écran", "hotkey", ""),
        ("countdown", "Compte à rebours (s)", "int", "0 = démarrage immédiat."),
        ("minimize_on_start", "Réduire la fenêtre au démarrage", "bool", ""),
        ("beep", "Bip au démarrage / à l'arrêt", "bool", ""),
    ]),
    ("Performances", [
        ("priority", "Priorité de FFmpeg", "choice", "« Basse » peut perdre des images si le CPU est saturé."),
        ("threads", "Threads de l'encodeur CPU", "int", "0 = automatique. 2 est un bon compromis."),
        ("rtbuf_mb", "Tampon temps réel (Mo)", "int", "Capture Windows (gdigrab/dshow)."),
        ("thread_queue", "File d'attente d'entrée", "int", ""),
        ("log_level", "Niveau de log FFmpeg", "choice", ""),
        ("ffmpeg_path", "Chemin de FFmpeg", "file", "Vide = automatique."),
        ("extra_output_args", "Arguments FFmpeg supplémentaires", "str", "Ajoutés avant le fichier de sortie."),
    ]),
]
KIND = {k: kind for _, fields in SCHEMA for k, _, kind, _ in fields}

MISSING_FFMPEG = {
    "win": "ffmpeg.exe est introuvable. Il doit se trouver à côté de LeFilouRec.exe (inclus dans le zip), "
           "ou indique son chemin dans Performances > Chemin de FFmpeg.",
    "linux": "FFmpeg est introuvable. Installe-le :\n  sudo apt install ffmpeg\n(ou le paquet équivalent de ta distribution).",
    "mac": "FFmpeg est introuvable. Installe-le avec Homebrew :\n  brew install ffmpeg",
}


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
                              timeout=timeout, **kw)
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
class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"LeFilou Rec {VERSION}")
        self.root.geometry("800x660")
        self.root.minsize(720, 560)
        if PLAT == "linux":
            try:
                ttk.Style().theme_use("clam")
            except tk.TclError:
                pass
        self.cfg = load_config()
        self.vars, self.devboxes = {}, []
        self.q = queue.Queue()
        self.proc = self.logf = self.hk = self.cap_listener = self.cap_win = None
        self.recording = self.stopping = self.counting = False
        self.t0 = self.last_ui = 0.0
        self.caps = self.caps_ff = None
        self.out_prefix = self.out_ext = ""
        self.enc_used = ""
        self._build()
        self.refresh_devices()
        self.apply_hotkeys()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(250, self.pump)

    # ---- construction de l'interface ------------------------------------- #
    def _build(self):
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=8, pady=(8, 4))

        main = ttk.Frame(nb, padding=18)
        nb.add(main, text="Enregistrer")
        self.btn = ttk.Button(main, text="●  Démarrer l'enregistrement", command=self.toggle)
        self.btn.pack(fill="x", ipady=16)
        big = tkfont.nametofont("TkDefaultFont").copy()
        big.configure(size=30)
        self._big = big
        self.lbl_time = ttk.Label(main, text="00:00:00", font=big)
        self.lbl_time.pack(pady=(24, 4))
        self.lbl_size = ttk.Label(main, text="")
        self.lbl_size.pack()
        self.lbl_status = ttk.Label(main, text="Prêt.", wraplength=700, justify="center")
        self.lbl_status.pack(pady=14)
        row = ttk.Frame(main)
        row.pack(pady=6)
        ttk.Button(row, text="Capture d'écran", command=self.screenshot).pack(side="left", padx=4)
        ttk.Button(row, text="Ouvrir le dossier", command=self.open_folder).pack(side="left", padx=4)
        self.lbl_hint = ttk.Label(main, text="", foreground="#777")
        self.lbl_hint.pack(side="bottom", pady=4)

        for title, fields in SCHEMA:
            tab = ttk.Frame(nb, padding=8)
            tab.columnconfigure(2, weight=1)
            nb.add(tab, text=title)
            for r, (key, label, kind, hint) in enumerate(fields):
                self._field(tab, r, key, label, kind, hint)
            if title == "Performances":
                bar = ttk.Frame(tab)
                bar.grid(row=len(fields), column=0, columnspan=3, sticky="w", pady=12, padx=8)
                for text, cmd in (("Détecter encodeurs / périphériques", self.detect_encoders),
                                  ("Voir la commande FFmpeg", self.show_command),
                                  ("Journal FFmpeg", self.show_log),
                                  ("Dossier de config", lambda: self.open_folder(CONFIG_DIR))):
                    ttk.Button(bar, text=text, command=cmd).pack(side="left", padx=3)

        bottom = ttk.Frame(self.root)
        bottom.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(bottom, text="Sauvegarder les réglages", command=self.save_settings).pack(side="left")
        ttk.Button(bottom, text="Importer…", command=self.import_cfg).pack(side="left", padx=4)
        ttk.Button(bottom, text="Exporter…", command=self.export_cfg).pack(side="left")
        ttk.Button(bottom, text="Valeurs par défaut", command=self.reset_cfg).pack(side="right")
        self.update_hint()

    def _field(self, parent, row, key, label, kind, hint):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(8, 6), pady=3)
        val = self.cfg[key]
        if kind == "bool":
            v = tk.BooleanVar(value=bool(val))
            w = ttk.Checkbutton(parent, variable=v)
        elif kind == "choice":
            v = tk.StringVar(value=choice_label(key, val))
            w = ttk.Combobox(parent, textvariable=v, state="readonly", width=34,
                             values=[lab for _, lab in CHOICES[key]])
        elif kind == "devchoice":
            v = tk.StringVar(value=str(val))
            w = ttk.Combobox(parent, textvariable=v, width=48)
            self.devboxes.append(w)
        elif kind in ("dir", "file"):
            v = tk.StringVar(value=str(val))
            w = ttk.Frame(parent)
            ttk.Entry(w, textvariable=v, width=44).pack(side="left", fill="x", expand=True)
            ttk.Button(w, text="…", width=3, command=lambda v=v, k=kind: self._browse(v, k)).pack(
                side="left", padx=(4, 0))
        elif kind == "hotkey":
            v = tk.StringVar(value=str(val))
            w = ttk.Frame(parent)
            ttk.Entry(w, textvariable=v, width=30).pack(side="left")
            ttk.Button(w, text="Définir…", command=lambda v=v: self.capture_hotkey(v)).pack(
                side="left", padx=(4, 0))
        else:
            v = tk.StringVar(value=str(val))
            w = ttk.Entry(parent, textvariable=v, width=10 if kind == "int" else 48)
        w.grid(row=row, column=1, sticky="w", pady=3)
        if hint:
            ttk.Label(parent, text=hint, foreground="#777", wraplength=260, justify="left").grid(
                row=row, column=2, sticky="w", padx=8)
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
            raise RuntimeError(MISSING_FFMPEG[PLAT])
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
        self.btn.config(text="■  Arrêter l'enregistrement")
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
        self.btn.config(text="●  Démarrer l'enregistrement")
        self.lbl_time.config(text="00:00:00")

    def log_tail(self, n=12):
        try:
            with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
                return "".join(f.readlines()[-n:])
        except OSError:
            return ""

    def on_stopped(self):
        size = self.total_size()
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
        win = self.cap_win = tk.Toplevel(self.root)
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
        t = tk.Text(w, wrap="word")
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
                elif kind == "stopped":
                    self.on_stopped()
                elif kind == "msg":
                    self.set_status(data)
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
        if self.proc and not self.stopping:
            if self.proc.poll() is not None:
                self.on_crash()
            else:
                now = time.monotonic()
                if now - self.last_ui >= 1:
                    self.last_ui = now
                    el = int(now - self.t0)
                    self.lbl_time.config(text=f"{el // 3600:02d}:{el // 60 % 60:02d}:{el % 60:02d}")
                    self.lbl_size.config(text=fmt_size(self.total_size()))
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
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
