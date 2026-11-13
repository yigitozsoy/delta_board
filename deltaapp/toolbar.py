"""Yüzen araç çubuğu: araçlar, renkler, kalınlık, geri al / yinele (+ isteğe bağlı ek düğmeler).
Konumu değiştirilebilir: alt / üst (yatay) ya da sol / sağ (dikey). Boş yerinden tutup bir kenara sürükle,
sağ tıkla ya da Seçenekler'den seç."""
from PyQt6.QtCore import Qt, QRectF, QPointF, QPoint, QSize, QObject, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QPainterPath
from PyQt6.QtWidgets import QWidget, QBoxLayout, QAbstractButton, QMenu, QColorDialog

from . import icons
from . import items as I
from .config import prefs
from .i18n import t
from .theme import theme, qcolor, color as tcolor
from .tools import state, COLORS, SIZES, SHAPES, ICON, tool_key
from .widgets import IconButton

POSITIONS = ("bottom", "top", "left", "right")


class _Bus(QObject):
    position_changed = pyqtSignal()   # tüm araç çubukları (ana pencere + ekrana çiz) yeniden yerleşsin


bus = _Bus()


def set_position(pos):
    if pos in POSITIONS and pos != prefs.get("toolbar_pos", "bottom"):
        prefs.set("toolbar_pos", pos)
        bus.position_changed.emit()


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
        if self.width() >= self.height():   # dikey çubukta yatay çizgi
            y = self.height() // 2
            p.drawLine(9, y, self.width() - 9, y)
        else:
            x = self.width() // 2
            p.drawLine(x, 9, x, self.height() - 9)


class ToolBar(QWidget):
    """board_fn(): işlemlerin uygulanacağı tuvali döndürür."""
    placed = pyqtSignal()

    def __init__(self, parent, board_fn, extras=None):
        super().__init__(parent)
        self.board_fn = board_fn
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.vertical = False
        self._drag = None
        self.margin = 16
        lay = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(2)
        self.tool_btns = {}
        for tool in ("select", "pen", "hl", "laser", "eraser"):
            b = self._tool_btn(tool)
            lay.addWidget(b)
        self.shape_btn = IconButton(ICON[state.last_shape], "", 36, 20, checkable=True, obj="ToolBtn")
        self.shape_btn.clicked.connect(self._shape_menu)
        lay.addWidget(self.shape_btn)
        lay.addWidget(self._tool_btn("text"))
        b = IconButton("image", t("insert_image") + " (Ctrl+I) · Ctrl+V", 36, 20, obj="ToolBtn")
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
        state.keys_changed.connect(self.update_tips)
        theme.changed.connect(lambda _: self.update())
        bus.position_changed.connect(self.place)
        self.update_tips()
        self.sync()
        self.adjustSize()

    def _tool_btn(self, tool):
        b = IconButton(ICON[tool], "", 36, 20, checkable=True, obj="ToolBtn")
        b.clicked.connect(lambda _=False, x=tool: state.set_tool(x))
        self.tool_btns[tool] = b
        return b

    def update_tips(self):
        for tool, b in self.tool_btns.items():
            k = tool_key(tool)
            b.setToolTip(t("tool_" + tool) + (f" ({k})" if k else ""))
        ks = [k for k in (tool_key(x) for x in SHAPES) if k]
        self.shape_btn.setToolTip(t("shapes") + (" (" + ", ".join(ks) + ")" if ks else ""))

    # ------------------------------------------------------------ konum / yön
    def set_vertical(self, v):
        if v == self.vertical:
            return
        self.vertical = v
        lay = self.layout()
        lay.setDirection(QBoxLayout.Direction.TopToBottom if v else QBoxLayout.Direction.LeftToRight)
        if v:
            lay.setContentsMargins(6, 10, 6, 10)
        else:
            lay.setContentsMargins(10, 6, 10, 6)
        for w in self.findChildren(QWidget):
            if isinstance(w, (Swatch, SizeDot, Sep)):
                a, b = w.width(), w.height()
                if (a < b) == v:      # yatayda dar-uzun, dikeyde geniş-kısa
                    w.setFixedSize(b, a)
        self.adjustSize()
        self.update()

    def place(self, margin=None):
        """Ebeveynin içinde tercih edilen kenara yerleşir."""
        if margin is not None:
            self.margin = margin
        par = self.parentWidget()
        if par is None:
            return
        pos = prefs.get("toolbar_pos", "bottom")
        if pos not in POSITIONS:
            pos = "bottom"
        self.set_vertical(pos in ("left", "right"))
        self.adjustSize()
        sh = self.sizeHint()
        m = self.margin
        if self.vertical:
            h = min(sh.height(), par.height() - 16)
            self.resize(sh.width(), h)
            x = m if pos == "left" else par.width() - sh.width() - m
            self.move(x, max(8, (par.height() - h) // 2))
        else:
            w = min(sh.width(), par.width() - 16)
            self.resize(w, sh.height())
            y = m if pos == "top" else par.height() - sh.height() - m
            self.move(max(8, (par.width() - w) // 2), y)
        self.raise_()
        self.placed.emit()

    def contextMenuEvent(self, e):
        m = QMenu(self)
        cur = prefs.get("toolbar_pos", "bottom")
        for pos in POSITIONS:
            a = m.addAction(t("tb_" + pos))
            a.setCheckable(True)
            a.setChecked(pos == cur)
            a.triggered.connect(lambda _=False, x=pos: set_position(x))
        m.addSeparator()
        m.addAction(t("tb_drag_hint")).setEnabled(False)
        m.exec(e.globalPos())

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            par = self.parentWidget()
            p = self.mapToParent(e.position().toPoint()) - self._drag
            if par is not None:
                p.setX(max(0, min(par.width() - self.width(), p.x())))
                p.setY(max(0, min(par.height() - self.height(), p.y())))
            self.move(p)
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._drag is not None and e.button() == Qt.MouseButton.LeftButton:
            self._drag = None
            self.unsetCursor()
            par = self.parentWidget()
            if par is not None:
                c = self.mapToParent(e.position().toPoint())
                d = {"left": c.x(), "right": par.width() - c.x(), "top": c.y(), "bottom": par.height() - c.y()}
                pos = min(d, key=d.get)
                if pos == prefs.get("toolbar_pos", "bottom"):
                    self.place()
                else:
                    set_position(pos)
            return
        super().mouseReleaseEvent(e)

    def _shape_menu(self):
        self.sync()
        m = QMenu(self)
        col = tcolor("text")
        for tool in SHAPES:
            a = m.addAction(icons.icon(ICON[tool], col, 18), f"{t('tool_' + tool)}\t{tool_key(tool)}")
            a.triggered.connect(lambda _=False, x=tool: state.set_tool(x))
        m.addSeparator()
        m.addAction(t("shift_hint")).setEnabled(False)
        r = self.shape_btn.rect()
        pos = prefs.get("toolbar_pos", "bottom")
        sh = m.sizeHint()
        if pos == "left":
            g = self.shape_btn.mapToGlobal(QPoint(r.right() + 8, r.top()))
        elif pos == "right":
            g = self.shape_btn.mapToGlobal(QPoint(r.left() - sh.width() - 8, r.top()))
        elif pos == "top":
            g = self.shape_btn.mapToGlobal(QPoint(r.left(), r.bottom() + 6))
        else:
            g = self.shape_btn.mapToGlobal(QPoint(r.left(), r.top() - sh.height() - 6))
        m.exec(g)

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
        rad = min(r.width(), r.height()) / 2
        path.addRoundedRect(r, rad, rad)
        p.fillPath(path, qcolor("dock"))
        p.setPen(QPen(qcolor("divider"), 1))
        p.drawPath(path)

    def sizeHint(self):
        return self.layout().sizeHint() if self.layout() else QSize(600, 48)
