"""Uygulama yolları ve kalıcı tercihler (%LOCALAPPDATA%\\delta\\preferences.json)."""
import json
import os
import sys
import threading

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "delta")
NOTES_DIR = os.path.join(DATA_DIR, "notes")
TRASH_DIR = os.path.join(DATA_DIR, "trash")
PREFS_FILE = os.path.join(DATA_DIR, "preferences.json")

for _d in (DATA_DIR, NOTES_DIR, TRASH_DIR):
    os.makedirs(_d, exist_ok=True)


def asset(name: str) -> str:
    return os.path.join(ASSETS_DIR, name)


DEFAULTS = {
    "language": "tr",
    "theme": "amoled",
    "accent": "gray",
    "grid": "dots",                 # dots | lines | none
    "wheel": "zoom",                # zoom | scroll  (fare tekerleği)
    "sidebar_visible": True,
    "pinned": False,
    "close_to_tray": True,
    "autostart": False,
    "tray_hint_shown": False,
    "capture_autocopy": True,
    "capture_target": "new",        # new | current  (alıntı delta'ya hangi nota gider)
    "hotkey_capture": "Win+Shift+X",       # Win+Shift+A Windows 11 tarafından kullanılıyor
    "hotkey_annotate": "Win+Shift+D",
    "hotkey_note": "Win+Shift+N",
    "hotkey_record": "Win+Shift+E",        # Win+Shift+R Windows 11 Ekran Alıntısı Aracı'nın
    "record_mic": "",               # "" = sessiz, yoksa DirectShow mikrofon adı
    "record_fps": 30,
    "snapshot_dir": "",
    "video_dir": "",
    "window_geometry": None,
    "last_note": None,
    # araç durumu
    "tool": "pen",
    "color": "auto",
    "width": 4.0,
    "last_shape": "arrow",
    "custom_color": "#b0b0b0",
}


class Prefs:
    def __init__(self, path=PREFS_FILE):
        self.path = path
        self.data = {}
        self._lock = threading.Lock()
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self.data.update(loaded)
        except (OSError, ValueError):
            pass

    def get(self, key, default=None):
        if key in self.data:
            return self.data[key]
        return DEFAULTS.get(key, default)

    def set(self, key, value):
        if self.data.get(key) == value and key in self.data:
            return
        self.data[key] = value
        self.save()

    def save(self):
        with self._lock:
            tmp = self.path + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=1)
                os.replace(tmp, self.path)
            except OSError:
                pass


def video_dir() -> str:
    """Ekran videolarının kaydedildiği klasör (varsayılan Videolar\\delta)."""
    d = prefs.get("video_dir") or ""
    if not d:
        try:
            from PyQt6.QtCore import QStandardPaths
            vids = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MoviesLocation)
        except Exception:
            vids = ""
        d = os.path.join(vids or os.path.expanduser("~"), "delta")
    os.makedirs(d, exist_ok=True)
    return d


def snapshot_dir() -> str:
    """Ekran alıntılarının / PNG dışa aktarımlarının kaydedildiği klasör."""
    d = prefs.get("snapshot_dir") or ""
    if not d:
        try:
            from PyQt6.QtCore import QStandardPaths
            pics = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
        except Exception:
            pics = ""
        d = os.path.join(pics or os.path.expanduser("~"), "delta")
    os.makedirs(d, exist_ok=True)
    return d


prefs = Prefs()
