"""Ortak araç durumu: seçili araç, renk, kalınlık.
Ana pencere ve "ekrana çiz" katmanı aynı durumu paylaşır (birinde kalemi seçince diğerinde de seçili)."""
from PyQt6.QtCore import QObject, pyqtSignal

from .config import prefs

TOOLS = ("select", "pen", "hl", "laser", "eraser", "line", "arrow", "rect", "ellipse", "text")
SHAPES = ("line", "arrow", "rect", "ellipse")
DRAW_TOOLS = ("pen", "hl") + SHAPES
# İlki "auto": koyu temada beyaz, açık temada siyah (tema değişince çizimler de döner)
COLORS = ["auto", "#ff453a", "#ff9f0a", "#ffd60a", "#30d158", "#3ea6ff", "#ff4fa3"]
SIZES = (2.0, 4.0, 8.0)
ICON = {"select": "select", "pen": "pen", "hl": "highlighter", "laser": "laser", "eraser": "eraser",
        "line": "line", "arrow": "arrow", "rect": "rect", "ellipse": "ellipse", "text": "text"}
KEY = {"select": "V", "pen": "P", "hl": "H", "laser": "K", "eraser": "E", "line": "L", "arrow": "A",
       "rect": "R", "ellipse": "O", "text": "T"}


class ToolState(QObject):
    changed = pyqtSignal()

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
