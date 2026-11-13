"""Alttaki yüzen araç çubuğu: araçlar, renkler, kalınlık, geri al / yinele (+ isteğe bağlı ek düğmeler)."""
from PyQt6.QtCore import Qt, QRectF, QPointF, QPoint, QSize
from PyQt6.QtGui import QPainter, QColor, QPen, QPainterPath
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QAbstractButton, QMenu, QColorDialog

from . import icons
from . import items as I
from .i18n import t
from .theme import theme, qcolor, color as tcolor
from .tools import state, COLORS, SIZES, SHAPES, ICON, KEY
from .widgets import IconButton


class Swatch(QAbstractButton):
    def __init__(self, col, parent=None):
        super().__init__(parent)
        self.col = col
        self.setFixedSize(28, 36)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        if self.isChecked():
            pen = QPen(qcolor("text"), 2)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, 12, 12)
        elif self.underMouse():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qcolor("hover"))
            p.drawEllipse(c, 13, 13)
        p.setPen(QPen(qcolor("divider"), 1))
        p.setBrush(I.ink(self.col))
        p.drawEllipse(c, 8.5, 8.5)


class SizeDot(QAbstractButton):
    def __init__(self, w, parent=None):
        super().__init__(parent)
        self.w = w
        self.setFixedSize(28, 36)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        if self.isChecked() or self.underMouse():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qcolor("surface_hover" if self.isChecked() else "hover"))
            p.drawEllipse(c, 13, 13)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qcolor("text"))
        r = {2.0: 2.0, 4.0: 3.6, 8.0: 6.0}.get(self.w, 3)
        p.drawEllipse(c, r, r)


class Sep(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(13, 36)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setPen(QPen(qcolor("divider"), 1))
        p.drawLine(6, 9, 6, 27)


class ToolBar(QWidget):
    """board_fn(): işlemlerin uygulanacağı tuvali döndürür."""

    def __init__(self, parent, board_fn, extras=None):
        super().__init__(parent)
        self.board_fn = board_fn
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(2)
        self.tool_btns = {}
        for tool in ("select", "pen", "hl", "laser", "eraser"):
            b = self._tool_btn(tool)
            lay.addWidget(b)
        self.shape_btn = IconButton(ICON[state.last_shape], t("shapes") + " (L, A, R, O)", 36, 20,
                                    checkable=True, obj="ToolBtn")
        self.shape_btn.clicked.connect(self._shape_menu)
        lay.addWidget(self.shape_btn)
        lay.addWidget(self._tool_btn("text"))
        b = IconButton("image", t("insert_image") + " (I) · Ctrl+V", 36, 20, obj="ToolBtn")
        b.clicked.connect(lambda: self.board_fn().insert_image_dialog())
        lay.addWidget(b)
        lay.addWidget(Sep())
        self.swatches = []
        for i, c in enumerate(COLORS):
            s = Swatch(c)
            s.setToolTip(t("color_n", n=i + 1) if c != "auto" else t("color_auto"))
            s.clicked.connect(lambda _=False, col=c: self.board_fn().apply_color(col))
            self.swatches.append(s)
            lay.addWidget(s)
        self.custom = Swatch(state.custom_color)
        self.custom.setToolTip(t("color_custom"))
        self.custom.clicked.connect(self._pick_color)
        lay.addWidget(self.custom)
        lay.addWidget(Sep())
        self.sizes = []
        for w in SIZES:
            d = SizeDot(w)
            d.setToolTip(t("size_tip"))
            d.clicked.connect(lambda _=False, ww=w: state.set_width(ww))
            self.sizes.append(d)
            lay.addWidget(d)
        lay.addWidget(Sep())
        self.btn_undo = IconButton("undo", t("undo") + " (Ctrl+Z)", 36, 20, obj="ToolBtn")
        self.btn_undo.clicked.connect(lambda: self.board_fn().undo())
        self.btn_redo = IconButton("redo", t("redo") + " (Ctrl+Y)", 36, 20, obj="ToolBtn")
        self.btn_redo.clicked.connect(lambda: self.board_fn().redo())
        lay.addWidget(self.btn_undo)
        lay.addWidget(self.btn_redo)
        self.extra_btns = {}
        if extras:
            lay.addWidget(Sep())
            for key, icon, tip, fn, checkable in extras:
                b = IconButton(icon, tip, 36, 20, checkable=checkable, obj="ToolBtn")
                b.clicked.connect(fn)
                self.extra_btns[key] = b
                lay.addWidget(b)
        state.changed.connect(self.sync)
        theme.changed.connect(lambda _: self.update())
        self.sync()
        self.adjustSize()

    def _tool_btn(self, tool):
        b = IconButton(ICON[tool], f"{t('tool_' + tool)} ({KEY[tool]})", 36, 20, checkable=True, obj="ToolBtn")
        b.clicked.connect(lambda _=False, x=tool: state.set_tool(x))
        self.tool_btns[tool] = b
        return b

    def _shape_menu(self):
        self.sync()
        m = QMenu(self)
        col = tcolor("text")
        for tool in SHAPES:
            a = m.addAction(icons.icon(ICON[tool], col, 18), f"{t('tool_' + tool)}\t{KEY[tool]}")
            a.triggered.connect(lambda _=False, x=tool: state.set_tool(x))
        m.addSeparator()
        m.addAction(t("shift_hint")).setEnabled(False)
        g = self.shape_btn.mapToGlobal(self.shape_btn.rect().topLeft())
        m.exec(QPoint(g.x(), g.y() - m.sizeHint().height() - 6))

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(state.custom_color), self.window(), t("color_custom"))
        if c.isValid():
            self.custom.col = c.name()
            self.board_fn().apply_color(c.name())

    def sync(self):
        for tool, b in self.tool_btns.items():
            b.setChecked(state.tool == tool)
        self.shape_btn.set_icon_name(ICON[state.last_shape])
        self.shape_btn.setChecked(state.tool in SHAPES)
        for s in self.swatches:
            s.setChecked(s.col == state.color)
        self.custom.col = state.custom_color
        self.custom.setChecked(state.color not in COLORS)
        for d in self.sizes:
            d.setChecked(abs(d.w - state.width) < 1e-6)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, r.height() / 2, r.height() / 2)
        p.fillPath(path, qcolor("dock"))
        p.setPen(QPen(qcolor("divider"), 1))
        p.drawPath(path)

    def sizeHint(self):
        return self.layout().sizeHint() if self.layout() else QSize(600, 48)
