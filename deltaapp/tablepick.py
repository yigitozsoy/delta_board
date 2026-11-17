"""Tablo ekleme seçicisi: üstte kenarlı / kenarsız seçimi, altta fareyle boyut seçilen ızgara (Word'deki gibi).
Menüye QWidgetAction olarak konur; boyut seçilince picked(satır, sütun, kenarlı) yayar."""
from PyQt6.QtCore import Qt, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QColor
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel

from .config import prefs
from .i18n import t
from .theme import qcolor


class _Grid(QWidget):
    hovered = pyqtSignal(int, int)
    clicked = pyqtSignal(int, int)
    N_COLS, N_ROWS, CELL, GAP = 10, 8, 17, 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.border = True
        self.hr = self.hc = 0
        step = self.CELL + self.GAP
        self.setFixedSize(self.N_COLS * step - self.GAP + 2, self.N_ROWS * step - self.GAP + 2)

    def _cell(self, pos):
        step = self.CELL + self.GAP
        c = min(self.N_COLS, max(1, int(pos.x() // step) + 1))
        r = min(self.N_ROWS, max(1, int(pos.y() // step) + 1))
        return r, c

    def mouseMoveEvent(self, e):
        r, c = self._cell(e.position())
        if (r, c) != (self.hr, self.hc):
            self.hr, self.hc = r, c
            self.hovered.emit(r, c)
            self.update()

    def leaveEvent(self, e):
        self.hr = self.hc = 0
        self.hovered.emit(0, 0)
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            r, c = self._cell(e.position())
            self.clicked.emit(r, c)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        step = self.CELL + self.GAP
        on = QColor(qcolor("text"))
        on.setAlpha(150)
        off = qcolor("divider")
        rad = 1.5
        if self.hr and self.hc and self.border:      # kenarlı: seçilen alanın dış çerçevesi
            p.setPen(QPen(qcolor("text"), 1.6))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(0.5, 0.5, self.hc * step - self.GAP + 1, self.hr * step - self.GAP + 1))
        for r in range(self.N_ROWS):
            for c in range(self.N_COLS):
                rect = QRectF(1 + c * step, 1 + r * step, self.CELL, self.CELL)
                hit = r < self.hr and c < self.hc
                p.setPen(QPen(on if hit else off, 1.2))
                p.setBrush(on if hit else Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(rect, rad, rad)
        p.end()


class TablePicker(QWidget):
    picked = pyqtSignal(int, int, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.b_square = QPushButton(t("tbl_border"))
        self.b_round = QPushButton(t("tbl_borderless"))
        for b in (self.b_square, self.b_round):
            b.setObjectName("Chip")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.grid = _Grid(self)
        lay.addWidget(self.grid)
        self.label = QLabel(t("tbl_pick"))
        self.label.setObjectName("Muted")
        lay.addWidget(self.label)
        self.b_square.clicked.connect(lambda: self.set_border(True))
        self.b_round.clicked.connect(lambda: self.set_border(False))
        self.grid.hovered.connect(self._hover)
        self.grid.clicked.connect(lambda r, c: self.picked.emit(r, c, self.grid.border))
        self.set_border(bool(prefs.get("table_border", True)), save=False)

    def set_border(self, on, save=True):
        self.grid.border = on
        self.b_square.setChecked(on)
        self.b_round.setChecked(not on)
        self.grid.update()
        if save:
            prefs.set("table_border", on)

    def _hover(self, r, c):
        self.label.setText(t("tbl_size", r=r, c=c) if r and c else t("tbl_pick"))
