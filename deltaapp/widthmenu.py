"""Kalınlık kaydırıcısı: araç düğmesine sağ tıkta ve tahtanın hızlı menüsünde açılır.
Kaydırırken kalem kalınlığı anında değişir; yanında çizginin önizlemesi görünür."""
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QPainter, QPen
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QSlider, QLabel, QWidgetAction

from . import icons
from . import items as I
from .i18n import t
from .theme import color as tcolor
from .tools import state, SIZES

STEP = 2          # kaydırıcı yarım piksel adımlarla
MIN_W, MAX_W = 0.5, 30.0


class _Preview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(58, 34)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = state.width_for(state.tool if state.tool in ("pen", "hl") else "pen")
        c = I.ink(state.color)
        if state.tool == "hl":
            c.setAlpha(105)
        p.setPen(QPen(c, min(w, 30), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        y = self.height() / 2
        p.drawLine(QPointF(8 + min(w, 30) / 2, y), QPointF(self.width() - 8 - min(w, 30) / 2, y))
        p.end()


class WidthBox(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(4)
        title = QLabel(t("width_title"))
        title.setObjectName("Muted")
        lay.addWidget(title)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(int(MIN_W * STEP), int(MAX_W * STEP))
        self.slider.setFixedWidth(160)
        self.slider.setValue(int(round(state.width * STEP)))
        self.label = QLabel()
        self.label.setFixedWidth(46)
        self.preview = _Preview(self)
        row.addWidget(self.slider)
        row.addWidget(self.label)
        row.addWidget(self.preview)
        lay.addLayout(row)
        self.slider.valueChanged.connect(self._changed)
        self._show()

    def _changed(self, v):
        state.set_width(v / STEP)
        self._show()

    def _show(self):
        w = state.width
        self.label.setText(f"{w:g} px")
        self.preview.update()


def build_width_menu(m, presets=True):
    """Menünün başına kalınlık kaydırıcısı + hazır kalınlıklar ekler."""
    box = WidthBox()
    wa = QWidgetAction(m)
    wa.setDefaultWidget(box)
    m.addAction(wa)
    for w in (SIZES if presets else ()):
        on = abs(state.width - w) < 1e-6
        a = m.addAction(icons.icon("check" if on else "blank", tcolor("text"), 18), f"{w:g} px")
        a.triggered.connect(lambda _=False, x=w: state.set_width(x))
    return box

