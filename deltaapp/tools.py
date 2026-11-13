"""Ortak araç durumu: seçili araç, renk, kalınlık.
Ana pencere ve "ekrana çiz" katmanı aynı durumu paylaşır (birinde kalemi seçince diğerinde de seçili)."""
from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtGui import QKeySequence

from .config import prefs

TOOLS = ("select", "pen", "hl", "laser", "eraser", "line", "arrow", "rect", "ellipse", "text")
SHAPES = ("line", "arrow", "rect", "ellipse")
DRAW_TOOLS = ("pen", "hl") + SHAPES
# İlki "auto": koyu temada beyaz, açık temada siyah (tema değişince çizimler de döner)
COLORS = ["auto", "#ff453a", "#ff9f0a", "#ffd60a", "#30d158", "#3ea6ff", "#ff4fa3"]
SIZES = (2.0, 4.0, 8.0)
ICON = {"select": "select", "pen": "pen", "hl": "highlighter", "laser": "laser", "eraser": "eraser",
        "line": "line", "arrow": "arrow", "rect": "rect", "ellipse": "ellipse", "text": "text"}
# Varsayılan araç tuşları rakamlarda (harfler boşta: tahtada harfe basınca imlecin yerine hemen yazı başlar).
# Seçenekler > Tahta kısayolları'ndan değiştirilebilir (prefs "tool_keys").
KEY = {"pen": "1", "hl": "2", "arrow": "3", "line": "4", "rect": "5", "ellipse": "6", "text": "7",
       "laser": "8", "eraser": "9", "select": "0"}
TOOL_ORDER = ("pen", "hl", "arrow", "line", "rect", "ellipse", "text", "laser", "eraser", "select")


def tool_keys():
    """Geçerli araç → tuş eşlemesi (kullanıcının değiştirdikleri + varsayılanlar)."""
    keys = dict(KEY)
    user = prefs.get("tool_keys", {}) or {}
    if isinstance(user, dict):
        for tool, k in user.items():
            if tool in keys:
                keys[tool] = str(k or "")
    return keys


def tool_key(tool):
    return tool_keys().get(tool, "")


def key_name(e):
    """Tuş olayının adı: rakamlar düzenden bağımsız ("1"), diğerleri Qt adıyla ("Q", "F3", "Ö")."""
    vk = e.nativeVirtualKey()
    if 0x30 <= vk <= 0x39:
        return str(vk - 0x30)
    if 0x60 <= vk <= 0x69:
        return str(vk - 0x60)
    k = e.key()
    if vk == 0 and Qt.Key.Key_0 <= k <= Qt.Key.Key_9:
        return str(k - Qt.Key.Key_0)
    if k in (0, Qt.Key.Key_unknown, Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
        return ""
    txt = e.text()
    if txt and txt.isprintable() and not txt.isspace() and len(txt) == 1:
        return txt.upper() if txt.isalpha() else txt
    return QKeySequence(k).toString()


def tool_for_key(name):
    if not name:
        return None
    for tool, k in tool_keys().items():
        if k and k == name:
            return tool
    return None


def set_tool_key(tool, name):
    """Tuşu araca ata; aynı tuş başka araçtaysa oradan kaldırılır."""
    keys = tool_keys()
    for other, k in keys.items():
        if other != tool and name and k == name:
            keys[other] = ""
    keys[tool] = name
    prefs.set("tool_keys", keys)
    state.keys_changed.emit()


def reset_tool_keys():
    prefs.set("tool_keys", {})
    state.keys_changed.emit()


class ToolState(QObject):
    changed = pyqtSignal()
    keys_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        t = prefs.get("tool", "pen")
        self.tool = t if t in TOOLS else "pen"
        self.color = str(prefs.get("color", "auto") or "auto")
        try:
            self.width = float(prefs.get("width", 4.0))
        except (TypeError, ValueError):
            self.width = 4.0
        ls = prefs.get("last_shape", "arrow")
        self.last_shape = ls if ls in SHAPES else "arrow"
        self.custom_color = str(prefs.get("custom_color", "#b0b0b0"))

    def set_tool(self, t):
        if t not in TOOLS:
            return
        self.tool = t
        if t in SHAPES:
            self.last_shape = t
            prefs.set("last_shape", t)
        prefs.set("tool", t)
        self.changed.emit()

    def set_color(self, c):
        self.color = c
        if c not in COLORS:
            self.custom_color = c
            prefs.set("custom_color", c)
        prefs.set("color", c)
        # Renk seçmek, silgi/seçim/lazer açıksa kaleme döndürür (Paint'teki gibi)
        if self.tool in ("eraser", "select", "laser"):
            self.tool = "pen"
            prefs.set("tool", "pen")
        self.changed.emit()

    def set_width(self, w):
        w = max(1.0, min(60.0, float(w)))
        if abs(w - self.width) < 1e-6:
            return
        self.width = w
        prefs.set("width", w)
        self.changed.emit()

    def nudge(self, d):
        w = self.width
        step = 1 if w < 6 else 2 if w < 16 else 4
        self.set_width(w + d * step)

    def width_for(self, tool):
        return self.width * 4 + 6 if tool == "hl" else self.width

    def text_px(self):
        return round(12 + self.width * 3.5)


state = ToolState()
