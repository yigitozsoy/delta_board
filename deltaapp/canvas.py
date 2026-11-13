"""Çizim tuvali: sonsuz alan, araçlar, gelişmiş fare kontrolleri, geri al / yinele.

Fare:
  sol sürükle ........ seçili araçla çiz          sağ basılı sürükle ... sil (dokunduğu çizgiyi siler)
  sağ kısa tık ....... hızlı menü                 orta sürükle / Boşluk+sol ... kaydır
  tekerlek ........... yakınlaştır (imlecin olduğu yere)    Alt+tekerlek ... kalınlık
  Shift+sol .......... düz çizgi (şekillerde kare/daire, 45°)   Ctrl+sol ... seç / taşı
  çift tık ........... oraya yazı yaz             orta çift tık ... hepsini sığdır
  yan tuşlar (geri/ileri) ... geri al / yinele
"""
import json
import math
import os
import time

from PyQt6.QtCore import Qt, QPointF, QRectF, QSizeF, QTimer, pyqtSignal, QMimeData, QByteArray
from PyQt6.QtGui import (QPainter, QColor, QPen, QPainterPath, QPainterPathStroker, QCursor, QPixmap, QImage,
                         QGuiApplication, QImageReader, QUndoCommand, QPolygonF)
from PyQt6.QtWidgets import QGraphicsView, QMenu, QApplication, QFileDialog

from . import items as I
from . import icons
from .config import prefs
from .i18n import t
from .theme import theme, qcolor, color as tcolor
from .tools import state, SHAPES, COLORS, ICON, KEY

MIME_ITEMS = "application/x-delta-items"
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".ico", ".tif", ".tiff", ".jfif", ".avif", ".heic")
LEFT, RIGHT, MIDDLE = Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton


# ---------------------------------------------------------------- geri al komutları

class AddCmd(QUndoCommand):
    """Nesneler sahneye zaten eklenmiş olarak gelir (ilk redo atlanır)."""

    def __init__(self, scene, items, text=""):
        super().__init__(text)
        self.scene, self.items, self._skip = scene, list(items), True

    def redo(self):
        if self._skip:
            self._skip = False
            return
        for it in self.items:
            if it.scene() is None:
                self.scene.addItem(it)

    def undo(self):
        for it in self.items:
            if it.scene() is self.scene:
                self.scene.removeItem(it)


class RemoveCmd(QUndoCommand):
    """Nesneler sahneden zaten çıkarılmış olarak gelir."""

    def __init__(self, scene, items, text=""):
        super().__init__(text)
        self.scene, self.items, self._skip = scene, list(items), True

    def redo(self):
        if self._skip:
            self._skip = False
            return
        for it in self.items:
            if it.scene() is self.scene:
                self.scene.removeItem(it)

    def undo(self):
        for it in self.items:
            if it.scene() is None:
                self.scene.addItem(it)


class TransformCmd(QUndoCommand):
    def __init__(self, changes):
        super().__init__("move")
        self.changes = changes  # [(item, (pos, scale), (pos, scale))]

    def redo(self):
        for it, _, (pos, sc) in self.changes:
            it.setPos(pos)
            it.setScale(sc)

    def undo(self):
        for it, (pos, sc), _ in self.changes:
            it.setPos(pos)
            it.setScale(sc)


class TextCmd(QUndoCommand):
    def __init__(self, item, before, after):
        super().__init__("text")
        self.item, self.before, self.after = item, before, after

    def redo(self):
        self.item.setPlainText(self.after)

    def undo(self):
        self.item.setPlainText(self.before)


class StyleCmd(QUndoCommand):
    def __init__(self, items, new_color):
        super().__init__("color")
        self.items = list(items)
        self.old = [it.color_name for it in self.items]
        self.new = new_color

    def redo(self):
        for it in self.items:
            it.color_name = self.new
            it.apply_style()

    def undo(self):
        for it, c in zip(self.items, self.old):
            it.color_name = c
            it.apply_style()


# ---------------------------------------------------------------- yardımcılar

def render_scene(scene, items=None, scale=2.0, bg=None, max_side=8000, margin=24, fit=None):
    """Nesneleri görüntüye çizer. fit=(g, y) verilirse o kutuya sığacak ölçek seçilir."""
    content = scene.content_items()
    items = content if items is None else list(items)
    if not items:
        return None
    rect = QRectF()
    for it in items:
        rect = rect.united(it.sceneBoundingRect())
    rect.adjust(-margin, -margin, margin, margin)
    if fit:
        scale = min(fit[0] / rect.width(), fit[1] / rect.height())
    scale = min(scale, max_side / max(rect.width(), rect.height(), 1))
    w, h = max(1, int(rect.width() * scale)), max(1, int(rect.height() * scale))
    keep = set(items)
    hidden = [it for it in content if it not in keep and it.isVisible()]
    for it in hidden:
        it.setVisible(False)
    sel = scene.selectedItems()
    for it in sel:
        it.setSelected(False)
    lasers = [it for it in scene.items() if isinstance(it, I.LaserItem)]
    for it in lasers:
        it.setVisible(False)
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(bg if bg is not None else qcolor("bg"))
    p = QPainter(img)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform |
                     QPainter.RenderHint.TextAntialiasing)
    scene.render(p, QRectF(0, 0, w, h), rect)
    p.end()
    for it in hidden + lasers:
        it.setVisible(True)
    for it in sel:
        it.setSelected(True)
    return img


def read_image_file(path):
    r = QImageReader(path)
    r.setAutoTransform(True)
    img = r.read()
    if img.isNull():
        try:  # Qt'nin açamadığı biçimler için Pillow
            from PIL import Image
            with Image.open(path) as im:
                im = im.convert("RGBA")
                data = im.tobytes("raw", "RGBA")
                img = QImage(data, im.width, im.height, im.width * 4, QImage.Format.Format_RGBA8888).copy()
        except Exception:
            return QImage()
    return img


_cursor_cache = {}


def ring_cursor(diam, col: QColor, fill=False, alpha=255):
    d = int(max(5, min(110, round(diam))))
    key = (d, col.name(), fill, alpha)
    if key in _cursor_cache:
        return _cursor_cache[key]
    app = QGuiApplication.instance()
    dpr = app.devicePixelRatio() if app else 1.0
    size = d + 6
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = size / 2
    r = d / 2
    if fill:
        fc = QColor(col)
        fc.setAlpha(alpha)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fc)
        p.drawEllipse(QPointF(c, c), r, r)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(0, 0, 0, 150), 1.0))
    p.drawEllipse(QPointF(c, c), r + 1.2, r + 1.2)
    p.setPen(QPen(QColor(255, 255, 255, 220) if not fill else col.lighter(130), 1.2))
    p.drawEllipse(QPointF(c, c), r, r)
    p.end()
    cur = QCursor(pm, int(c), int(c))
    _cursor_cache[key] = cur
    return cur


def constrain(kind, a, b):
    dx, dy = b.x() - a.x(), b.y() - a.y()
    if kind in ("rect", "ellipse"):
        s = max(abs(dx), abs(dy))
        return QPointF(a.x() + math.copysign(s, dx or 1), a.y() + math.copysign(s, dy or 1))
    ang = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
    L = math.hypot(dx, dy)
    return QPointF(a.x() + L * math.cos(ang), a.y() + L * math.sin(ang))


# ---------------------------------------------------------------- tuval

class Board(QGraphicsView):
    zoom_changed = pyqtSignal(float)
    content_changed = pyqtSignal()
    escape_pressed = pyqtSignal()

    def __init__(self, parent=None, transparent=False, fixed=False):
        super().__init__(parent)
        self.transparent = transparent   # ekrana çiz katmanı: arka plan görünmez
        self.fixed = fixed               # yakınlaştırma / kaydırma yok (ekran koordinatı)
        self.opaque_bg = False           # ekrana çizde "tahta" modu
        self.page = None
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform |
                            QPainter.RenderHint.TextAntialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setRubberBandSelectionMode(Qt.ItemSelectionMode.IntersectsItemShape)
        if transparent:
            self.setStyleSheet("QGraphicsView { background: transparent; border: none; }")
            self.viewport().setAutoFillBackground(False)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        else:
            self.setStyleSheet("QGraphicsView { border: none; }")
            self.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground)

        self._mode = None          # draw | shape | pan | erase | select | laser | textclick
        self._mode_btn = None
        self._cur = None
        self._start = None
        self._last_view = None
        self._last_scene = None
        self._press_view = None
        self._press_time = 0.0
        self._moved = False
        self._erased = []
        self._space = False
        self._snapshot = {}
        self._last_dot = None
        self._rs = None            # görsel boyutlandırma: (öğe, sabit köşe, eski konum, eski ölçek, köşe)
        self._rs_cursor = False
        self._mouse_view = None
        self._lasers = []
        self._laser_timer = QTimer(self)
        self._laser_timer.setInterval(16)
        self._laser_timer.timeout.connect(self._tick_laser)

        from .widgets import Toast
        self.toast_label = Toast(self)
        state.changed.connect(self._update_cursor)
        theme.changed.connect(lambda _: self.refresh_theme())
        self._update_cursor()

    # ============================================================ sayfa
    def set_page(self, page):
        self.finish_text()
        if self.page is not None:
            self.store_view()
            try:
                self.page.undo.indexChanged.disconnect(self._on_undo_index)
            except (TypeError, RuntimeError):
                pass
        self.page = page
        page.ensure_loaded()
        self.setScene(page.scene)
        page.undo.indexChanged.connect(self._on_undo_index)
        self.resetTransform()
        v = page.view or {}
        if not self.fixed:
            z = float(v.get("z", 1.0))
            self.scale(z, z)
            if "cx" in v:
                self.centerOn(QPointF(v["cx"], v["cy"]))
            else:
                self.centerOn(QPointF(0, 0))
        else:
            self.centerOn(QPointF(self.viewport().width() / 2, self.viewport().height() / 2))
        self.zoom_changed.emit(self.zoom())
        self.content_changed.emit()
        self._update_cursor()

    def store_view(self):
        if self.page is None or self.fixed:
            return
        c = self.mapToScene(self.viewport().rect().center())
        self.page.view = {"z": round(self.zoom(), 4), "cx": round(c.x(), 1), "cy": round(c.y(), 1)}

    def _on_undo_index(self, _i):
        self.content_changed.emit()

    def push(self, cmd):
        if self.page is not None:
            self.page.undo.push(cmd)

    def undo(self):
        self.finish_text()
        if self.page and self.page.undo.canUndo():
            self.page.undo.undo()
        else:
            self.toast(t("nothing_to_undo"))

    def redo(self):
        self.finish_text()
        if self.page and self.page.undo.canRedo():
            self.page.undo.redo()

    def is_empty(self):
        return not self.scene() or not self.scene().content_items()

    def active_tool(self):
        if self._mode == "select":
            return "select"
        return state.tool

    # ============================================================ görünüm
    def zoom(self):
        return self.transform().m11()

    def zoom_by(self, f, under_mouse=True):
        if self.fixed:
            return
        z = self.zoom()
        nz = max(0.08, min(10.0, z * f))
        f = nz / z
        if abs(f - 1) < 1e-4:
            return
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse if under_mouse
                                     else QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.scale(f, f)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.zoom_changed.emit(nz)
        self._update_cursor()

    def set_zoom(self, z):
        self.zoom_by(z / self.zoom(), under_mouse=False)

    def pan_px(self, dx, dy):
        if self.fixed:
            return
        h, v = self.horizontalScrollBar(), self.verticalScrollBar()
        h.setValue(h.value() - int(round(dx)))
        v.setValue(v.value() - int(round(dy)))

    def fit_all(self):
        if self.fixed or self.is_empty():
            self.set_zoom(1.0)
            return
        rect = QRectF()
        for it in self.scene().content_items():
            rect = rect.united(it.sceneBoundingRect())
        rect.adjust(-60, -60, 60, 60)
        vp = self.viewport().rect()
        z = min(vp.width() / rect.width(), (vp.height() - 80) / rect.height(), 2.0)
        self.resetTransform()
        z = max(0.08, z)
        self.scale(z, z)
        self.centerOn(rect.center() + QPointF(0, 30 / z))
        self.zoom_changed.emit(z)
        self._update_cursor()

    def refresh_theme(self):
        if self.scene():
            self.scene().restyle()
        self.resetCachedContent()
        self.viewport().update()
        self._update_cursor()

    def drawBackground(self, p, rect):
        if self.transparent and not self.opaque_bg:
            # Alfa=1 dolgu: saydam pencere fare olaylarını yine de yakalasın
            p.save()
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            p.fillRect(rect, QColor(0, 0, 0, 1))
            p.restore()
            return
        p.fillRect(rect, qcolor("bg"))
        grid = prefs.get("grid", "dots")
        if grid == "none":
            return
        z = self.zoom()
        step = 28.0
        while step * z < 14:
            step *= 2
        gc = qcolor("grid")
        x0 = math.floor(rect.left() / step) * step
        y0 = math.floor(rect.top() / step) * step
        if grid == "lines":
            gc.setAlpha(int(gc.alpha() * 0.55))
            pen = QPen(gc, 1)
            pen.setCosmetic(True)
            p.setPen(pen)
            x = x0
            while x <= rect.right():
                p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
                x += step
            y = y0
            while y <= rect.bottom():
                p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
                y += step
            return
        pen = QPen(gc, 2.2)
        pen.setCosmetic(True)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        pts = []
        x = x0
        while x <= rect.right():
            y = y0
            while y <= rect.bottom():
                pts.append(QPointF(x, y))
                y += step
            x += step
        if pts:
            p.drawPoints(QPolygonF(pts))

    # ============================================================ imleç
    def _update_cursor(self, *_):
        if self._mode == "pan" or self._space:
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor if self._mode == "pan"
                                      else Qt.CursorShape.OpenHandCursor)
            return
        if self._mode == "erase":
            self.viewport().setCursor(ring_cursor(20, QColor("#ffffff")))
            return
        tool = state.tool
        z = self.zoom()
        if tool in ("pen", "hl"):
            c = I.ink(state.color)
            self.viewport().setCursor(ring_cursor(state.width_for(tool) * z, c, fill=True,
                                                  alpha=105 if tool == "hl" else 255))
        elif tool == "eraser":
            self.viewport().setCursor(ring_cursor(20, QColor("#ffffff")))
        elif tool == "laser":
            self.viewport().setCursor(ring_cursor(8, QColor("#ff3030"), fill=True))
        elif tool == "text":
            self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        elif tool in SHAPES:
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)

    def toast(self, text, ms=1400):
        self.toast_label.show_text(text, ms)

    # ============================================================ yazı
    def editing_text(self):
        sc = self.scene()
        fi = sc.focusItem() if sc else None
        if isinstance(fi, I.TextItem) and fi.editing():
            return fi
        return None

    def finish_text(self):
        it = self.editing_text()
        if it is not None:
            it.clearFocus()

    def text_at(self, sp):
        sc = self.scene()
        for it in sc.items(sp):
            if isinstance(it, I.TextItem):
                return it
        return None

    def new_text(self, sp, text=""):
        it = I.TextItem(text, state.color, state.text_px())
        it.setZValue(self.scene().next_z("text"))
        h = it.boundingRect().height()
        it.setPos(sp - QPointF(6, h / 2))
        self.scene().addItem(it)
        it.is_new = True
        it.on_finished = self._text_finished
        it.start_edit()
        return it

    def edit_text(self, it):
        it.on_finished = self._text_finished
        it.start_edit()

    def _text_finished(self, it, before, after, is_new):
        sc = self.scene()
        if is_new:
            if after.strip():
                self.push(AddCmd(sc, [it], "text"))
            elif it.scene() is not None:
                it.scene().removeItem(it)
        else:
            if not after.strip():
                it.setPlainText(before)
                if it.scene() is not None:
                    it.scene().removeItem(it)
                self.push(RemoveCmd(sc, [it], "erase"))
            elif after != before:
                self.push(TextCmd(it, before, after))
        self.content_changed.emit()
        if self.isVisible():
            QTimer.singleShot(0, self.setFocus)

    def _cursor_scene(self):
        pos = self.viewport().mapFromGlobal(QCursor.pos())
        if not self.viewport().rect().contains(pos):
            pos = self.viewport().rect().center()
        return self.mapToScene(pos)

    # ============================================================ fare
    def mousePressEvent(self, e):
        b = e.button()
        pos = e.position().toPoint()
        sp = self.mapToScene(pos)
        if not self.editing_text():
            self.setFocus()
        if b == Qt.MouseButton.BackButton:
            self.undo()
            return
        if b == Qt.MouseButton.ForwardButton:
            self.redo()
            return
        if self._mode:
            return
        ft = self.editing_text()
        if ft is not None:
            if b == LEFT and ft.sceneBoundingRect().contains(sp):
                self._mode, self._mode_btn = "textclick", b
                super().mousePressEvent(e)
                return
            ft.clearFocus()
            if b == LEFT:
                return
        self._press_view, self._press_time, self._moved = pos, time.monotonic(), False
        self._last_view, self._last_scene = pos, sp
        if b == MIDDLE or (b == LEFT and self._space):
            if self.fixed:
                return
            self._mode, self._mode_btn = "pan", b
            self._update_cursor()
            return
        if b == RIGHT:
            self._start_erase(b, sp)
            return
        if b != LEFT:
            return
        h = self._image_handle_at(pos)
        if h is not None:
            it, corner, anchor = h
            self._rs = (it, anchor, it.pos(), it.scale(), corner)
            self._mode, self._mode_btn = "imgresize", b
            return
        tool = state.tool
        mods = e.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier and tool != "select":
            tool = "select"
        if tool in ("pen", "hl") and mods & Qt.KeyboardModifier.ShiftModifier:
            tool = "line"
        if tool != "select":
            # çizim araçlarında seçimin dışına basınca seçim (ve tutamaçlar) kalksın
            for it in self.scene().selectedItems():
                if not it.sceneBoundingRect().contains(sp):
                    it.setSelected(False)
        if tool == "select":
            self._mode, self._mode_btn = "select", b
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            super().mousePressEvent(e)
            under = self.scene().itemAt(sp, self.transform())
            items = set(self.scene().selectedItems())
            if under is not None:
                items.add(under)
            self._snapshot = {it: (it.pos(), it.scale()) for it in items}
            return
        if tool == "eraser":
            self._start_erase(b, sp)
            return
        if tool == "laser":
            it = I.LaserItem()
            self.scene().addItem(it)
            it.add(sp)
            self._lasers.append(it)
            self._cur = it
            self._mode, self._mode_btn = "laser", b
            self._laser_timer.start()
            return
        if tool == "text":
            it = self.text_at(sp)
            if it is not None:
                self.edit_text(it)
            else:
                self.new_text(sp)
            return
        if tool in ("pen", "hl"):
            it = I.StrokeItem(tool, state.color, state.width_for(tool), [sp])
            it.setZValue(self.scene().next_z(tool))
            self.scene().addItem(it)
            self._cur = it
            self._mode, self._mode_btn = "draw", b
            return
        if tool in SHAPES:
            it = I.StrokeItem(tool, state.color, state.width_for(tool), [sp, sp])
            it.setZValue(self.scene().next_z(tool))
            self.scene().addItem(it)
            self._cur, self._start = it, sp
            self._mode, self._mode_btn = "shape", b

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        self._mouse_view = pos
        sp = self.mapToScene(pos)
        m = self._mode
        if self._press_view is not None and (pos - self._press_view).manhattanLength() > 4:
            self._moved = True
        if m == "pan":
            d = pos - self._last_view
            self.pan_px(d.x(), d.y())
            self._last_view = pos
            return
        if m == "erase":
            self._erase_between(self._last_scene, sp)
            self._last_scene = sp
            return
        if m == "draw":
            if (pos - self._last_view).manhattanLength() >= 2:
                self._cur.add_point(sp)
                self._last_view = pos
            return
        if m == "shape":
            end = sp
            if e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                end = constrain(self._cur.kind, self._start, sp)
            self._cur.set_points([self._start, end])
            return
        if m == "laser":
            self._cur.add(sp)
            return
        if m == "imgresize":
            self._resize_to(sp)
            return
        if not m and e.buttons() == Qt.MouseButton.NoButton:
            h = self._image_handle_at(pos)
            if h is not None:
                self.viewport().setCursor(Qt.CursorShape.SizeFDiagCursor if h[1] in ("tl", "br")
                                          else Qt.CursorShape.SizeBDiagCursor)
                self._rs_cursor = True
            elif self._rs_cursor:
                self._rs_cursor = False
                self._update_cursor()
        if state.tool == "laser" and not m and e.buttons() == Qt.MouseButton.NoButton:
            pass
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        b = e.button()
        m = self._mode
        if m is None or b != self._mode_btn:
            if m is None:
                super().mouseReleaseEvent(e)
            return
        self._mode = None
        if m == "pan":
            self._update_cursor()
        elif m == "erase":
            if self._erased:
                self.push(RemoveCmd(self.scene(), self._erased, "erase"))
                self._erased = []
            elif b == RIGHT and not self._moved and time.monotonic() - self._press_time < 0.45:
                self._context_menu(e.position().toPoint())
            self._update_cursor()
        elif m == "draw":
            it = self._cur
            it.finish(self.zoom())
            self.push(AddCmd(self.scene(), [it], "draw"))
            self._last_dot = (it, time.monotonic()) if len(it.pts) <= 2 else None
        elif m == "shape":
            it = self._cur
            a, bb = it.pts[0], it.pts[-1]
            if math.hypot(a.x() - bb.x(), a.y() - bb.y()) * self.zoom() < 4:
                self.scene().removeItem(it)
            else:
                self.push(AddCmd(self.scene(), [it], "shape"))
        elif m == "laser":
            self._cur.active = False
        elif m == "imgresize":
            it, _, pos0, sc0, _ = self._rs
            self._rs = None
            if it.pos() != pos0 or abs(it.scale() - sc0) > 1e-9:
                self.push(TransformCmd([(it, (pos0, sc0), (it.pos(), it.scale()))]))
            self._rs_cursor = False
            self._update_cursor()
        elif m == "select":
            super().mouseReleaseEvent(e)
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            ch = []
            for it, (pos, sc) in self._snapshot.items():
                if it.scene() is not None and (it.pos() != pos or abs(it.scale() - sc) > 1e-9):
                    ch.append((it, (pos, sc), (it.pos(), it.scale())))
            self._snapshot = {}
            if ch:
                self.push(TransformCmd(ch))
        elif m == "textclick":
            super().mouseReleaseEvent(e)
        self._cur = None
        self._press_view = None

    def mouseDoubleClickEvent(self, e):
        b = e.button()
        if b == MIDDLE:
            self.fit_all()
            return
        if b != LEFT or self._mode:
            return
        sp = self.mapToScene(e.position().toPoint())
        it = self.text_at(sp)
        if it is not None:
            self.edit_text(it)
            return
        if state.tool == "select":
            under = self.scene().itemAt(sp, self.transform())
            if under is not None:
                return
        # İlk tıklamanın bıraktığı noktayı geri al, sonra oraya yazı aç
        if self._last_dot and time.monotonic() - self._last_dot[1] < 0.6 and self.page.undo.canUndo():
            cmd = self.page.undo.command(self.page.undo.index() - 1)
            if isinstance(cmd, AddCmd) and self._last_dot[0] in cmd.items:
                self.page.undo.undo()
        self._last_dot = None
        self.new_text(sp)

    def contextMenuEvent(self, e):
        e.accept()  # sağ tık silgi; menü kısa tıkta açılır

    def wheelEvent(self, e):
        mods = e.modifiers()
        ad, pd = e.angleDelta(), e.pixelDelta()
        if mods & Qt.KeyboardModifier.AltModifier:
            d = ad.x() or ad.y()
            if d:
                state.nudge(1 if d > 0 else -1)
                self.toast(t("size_toast", n=f"{state.width:g}"), 700)
            return
        if self.fixed:
            return
        if mods & Qt.KeyboardModifier.ControlModifier:
            self.zoom_by(1.0018 ** ad.y())
            return
        if not pd.isNull():  # dokunmatik yüzey: iki parmakla kaydır
            self.pan_px(pd.x(), pd.y())
            return
        if mods & Qt.KeyboardModifier.ShiftModifier:
            self.pan_px((ad.y() or ad.x()) * 0.8, 0)
            return
        if prefs.get("wheel", "zoom") == "zoom":
            self.zoom_by(1.0018 ** ad.y())
        else:
            self.pan_px(ad.x() * 0.8, ad.y() * 0.8)

    # ============================================================ silgi
    def _start_erase(self, b, sp):
        self._mode, self._mode_btn = "erase", b
        self._erased = []
        self._update_cursor()
        self._erase_between(sp, sp)

    def _erase_between(self, a, b):
        r = 10 / max(self.zoom(), 1e-6)
        path = QPainterPath(a)
        path.lineTo(b + QPointF(0.01, 0))
        st = QPainterPathStroker()
        st.setWidth(2 * r)
        st.setCapStyle(Qt.PenCapStyle.RoundCap)
        area = st.createStroke(path)
        sc = self.scene()
        for it in sc.items(area, Qt.ItemSelectionMode.IntersectsItemShape):
            if isinstance(it, (I.StrokeItem, I.TextItem)) and it.scene() is sc:
                sc.removeItem(it)
                self._erased.append(it)

    # ============================================================ lazer
    def _tick_laser(self):
        now = time.monotonic()
        alive = []
        for it in self._lasers:
            if it.scene() is not None and it.tick(now):
                alive.append(it)
            elif it.scene() is not None:
                it.scene().removeItem(it)
        self._lasers = alive
        if not alive:
            self._laser_timer.stop()

    # ============================================================ klavye
    def keyPressEvent(self, e):
        if self.editing_text():
            super().keyPressEvent(e)
            return
        k = e.key()
        mods = e.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        K = Qt.Key
        if ctrl:
            if k == K.Key_Z:
                self.redo() if shift else self.undo()
            elif k == K.Key_Y:
                self.redo()
            elif k == K.Key_C and not shift:
                self.copy()
            elif k == K.Key_X:
                self.cut()
            elif k == K.Key_V:
                self.paste()
            elif k == K.Key_D:
                self.duplicate()
            elif k == K.Key_A:
                self.select_all()
            elif k == K.Key_0:
                self.set_zoom(1.0)
            elif k in (K.Key_Plus, K.Key_Equal):
                self.zoom_by(1.25, False)
            elif k == K.Key_Minus:
                self.zoom_by(0.8, False)
            else:
                e.ignore()
            return
        if mods & Qt.KeyboardModifier.AltModifier:
            e.ignore()
            return
        tools = {K.Key_V: "select", K.Key_P: "pen", K.Key_B: "pen", K.Key_H: "hl", K.Key_K: "laser",
                 K.Key_E: "eraser", K.Key_L: "line", K.Key_A: "arrow", K.Key_R: "rect", K.Key_O: "ellipse",
                 K.Key_T: "text"}
        if k in tools and not e.isAutoRepeat():
            state.set_tool(tools[k])
            return
        if K.Key_1 <= k <= K.Key_7:
            self.apply_color(COLORS[k - K.Key_1])
            return
        if k in (K.Key_BracketLeft, K.Key_Comma, K.Key_Minus):
            state.nudge(-1)
            self.toast(t("size_toast", n=f"{state.width:g}"), 700)
            return
        if k in (K.Key_BracketRight, K.Key_Period, K.Key_Plus, K.Key_Asterisk):
            state.nudge(1)
            self.toast(t("size_toast", n=f"{state.width:g}"), 700)
            return
        if k == K.Key_I or k == 0x131:  # Türkçe klavyede ı
            self.insert_image_dialog()
            return
        if k == K.Key_F:
            self.fit_all()
            return
        if k == K.Key_G and not self.transparent:
            order = ["dots", "lines", "none"]
            cur = prefs.get("grid", "dots")
            prefs.set("grid", order[(order.index(cur) + 1) % 3] if cur in order else "dots")
            self.resetCachedContent()
            self.viewport().update()
            return
        if k in (K.Key_Delete, K.Key_Backspace):
            self.delete_selection()
            return
        if k in (K.Key_Return, K.Key_Enter):
            sel = [it for it in self.scene().selectedItems() if isinstance(it, I.TextItem)]
            if len(sel) == 1:
                self.edit_text(sel[0])
            else:
                self.new_text(self._cursor_scene())
            return
        if k == K.Key_Space:
            if not e.isAutoRepeat() and not self.fixed:
                self._space = True
                self._update_cursor()
            return
        if k == K.Key_Escape:
            if self.scene() and self.scene().selectedItems():
                self.scene().clearSelection()
            else:
                self.escape_pressed.emit()
            return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self._space = False
            self._update_cursor()
            return
        super().keyReleaseEvent(e)

    def focusOutEvent(self, e):
        self._space = False
        super().focusOutEvent(e)

    # ============================================================ düzenleme işlemleri
    def selected(self):
        sc = self.scene()
        return [it for it in sc.selectedItems() if isinstance(it, (I.StrokeItem, I.TextItem, I.ImageItem))] if sc else []

    def apply_color(self, c):
        sel = [it for it in self.selected() if not isinstance(it, I.ImageItem)]
        if sel:
            cmd = StyleCmd(sel, c)
            self.push(cmd)
            state.color = c  # aracı değiştirmeden rengi hatırla
            from .config import prefs as _p
            _p.set("color", c)
            state.changed.emit()
        else:
            state.set_color(c)

    def delete_selection(self):
        sel = self.selected()
        if not sel:
            return
        for it in sel:
            self.scene().removeItem(it)
        self.push(RemoveCmd(self.scene(), sel, "delete"))

    def delete_item(self, it):
        if it.scene() is not None:
            it.scene().removeItem(it)
            self.push(RemoveCmd(self.scene(), [it], "delete"))

    def clear_all(self):
        items = self.scene().content_items() if self.scene() else []
        if not items:
            return
        for it in items:
            self.scene().removeItem(it)
        self.push(RemoveCmd(self.scene(), items, "clear"))
        self.toast(t("cleared_undo"))

    def select_all(self):
        state.set_tool("select")
        for it in self.scene().content_items():
            it.setSelected(True)

    def copy(self, only_image=False):
        sel = self.selected()
        img = render_scene(self.scene(), sel or None)
        if img is None:
            self.toast(t("nothing_to_copy"))
            return
        md = QMimeData()
        md.setImageData(img)
        if sel and not only_image:
            data = [I.to_dict(it) for it in sel]
            md.setData(MIME_ITEMS, QByteArray(json.dumps(data).encode("utf-8")))
        QApplication.clipboard().setMimeData(md)
        self.toast(t("copied_sel") if sel else t("copied_page"))

    def cut(self):
        if self.selected():
            self.copy()
            self.delete_selection()

    def duplicate(self):
        sel = self.selected()
        if not sel:
            return
        self._add_dicts([I.to_dict(it) for it in sel], offset=QPointF(24, 24))

    def _add_dicts(self, dicts, offset=None, center=None):
        new = []
        for d in dicts:
            it = I.from_dict(d)
            if it is None:
                continue
            new.append(it)
        if not new:
            return []
        if center is not None:
            rect = QRectF()
            for it in new:
                rect = rect.united(it.sceneBoundingRect())
            offset = center - rect.center()
        sc = self.scene()
        sc.clearSelection()
        for it in sorted(new, key=lambda i: i.zValue()):
            it.setZValue(sc.next_z(getattr(it, "kind", "")))
            if offset is not None:
                it.setPos(it.pos() + offset)
            sc.addItem(it)
            it.setSelected(True)
        self.push(AddCmd(sc, new, "paste"))
        return new

    def paste(self):
        md = QApplication.clipboard().mimeData()
        if md is None:
            return
        at = self._cursor_scene()
        if md.hasFormat(MIME_ITEMS):
            try:
                dicts = json.loads(bytes(md.data(MIME_ITEMS)).decode("utf-8"))
                if self._add_dicts(dicts, center=at):
                    state.set_tool("select")
                    return
            except ValueError:
                pass
        if self.insert_from_mime(md, at):
            return
        if md.hasText() and md.text().strip():
            it = I.TextItem(md.text().strip(), state.color, state.text_px())
            it.setZValue(self.scene().next_z("text"))
            it.setPos(at)
            self.scene().addItem(it)
            self.push(AddCmd(self.scene(), [it], "paste"))
            return
        self.toast(t("clipboard_empty"))

    def insert_from_mime(self, md, at):
        if md.hasImage():
            img = md.imageData()
            if isinstance(img, QImage) and not img.isNull():
                self.insert_image(img, at)
                return True
            if isinstance(img, QPixmap) and not img.isNull():
                self.insert_image(img.toImage(), at)
                return True
        if md.hasUrls():
            paths = [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
            done = 0
            for i, pth in enumerate(paths):
                if pth.lower().endswith(IMAGE_EXT) and os.path.isfile(pth):
                    img = read_image_file(pth)
                    if not img.isNull():
                        self.insert_image(img, at + QPointF(30 * i, 30 * i) / max(self.zoom(), 0.1))
                        done += 1
            return done > 0
        return False

    # ------------------------------------------------------------ görsel boyutlandırma
    HANDLE_HIT = 14  # köşeye bu kadar ekran pikseli yakınsa tutamaç sayılır

    def _image_handle_at(self, pos):
        """Seçili bir görselin köşe tutamacı imlecin altındaysa (öğe, köşe, karşı köşe) döner.
        Hangi araç seçili olursa olsun çalışır."""
        sc = self.scene()
        if sc is None:
            return None
        opp = {"tl": "br", "tr": "bl", "bl": "tr", "br": "tl"}
        best = None
        for it in sc.selectedItems():
            if not isinstance(it, I.ImageItem) or not it.isVisible():
                continue
            r = QRectF(it.offset(), QSizeF(it.pixmap().width(), it.pixmap().height()))  # boundingRect'te +0.5 pay var
            cs = {"tl": r.topLeft(), "tr": r.topRight(), "bl": r.bottomLeft(), "br": r.bottomRight()}
            for k, c in cs.items():
                v = QPointF(self.mapFromScene(it.mapToScene(c)))
                d = max(abs(v.x() - pos.x()), abs(v.y() - pos.y()))
                if d <= self.HANDLE_HIT and (best is None or d < best[0]):
                    best = (d, it, k, it.mapToScene(cs[opp[k]]))
        return None if best is None else best[1:]

    def _resize_to(self, sp):
        it, anchor, _, _, corner = self._rs
        pw, ph = max(1, it.pixmap().width()), max(1, it.pixmap().height())
        mn = 16 / max(self.zoom(), 1e-6) / max(pw, ph)
        s = max(abs(sp.x() - anchor.x()) / pw, abs(sp.y() - anchor.y()) / ph, mn)
        x = anchor.x() - pw * s if corner in ("tl", "bl") else anchor.x()
        y = anchor.y() - ph * s if corner in ("tl", "tr") else anchor.y()
        it.setScale(s)
        it.setPos(QPointF(x, y))

    def insert_image(self, img: QImage, center: QPointF, dpr=1.0):
        if img.isNull():
            return None
        it = I.ImageItem.from_qimage(img)
        s = 1.0 / max(dpr, 0.1)
        vis = self.mapToScene(self.viewport().rect()).boundingRect()
        maxw, maxh = vis.width() * 0.75, vis.height() * 0.75
        w, h = img.width() * s, img.height() * s
        if w > maxw or h > maxh:
            s *= min(maxw / w, maxh / h)
        it.setScale(s)
        it.setPos(center - QPointF(img.width() * s / 2, img.height() * s / 2))
        it.setZValue(self.scene().next_z("image"))
        self.scene().addItem(it)
        self.push(AddCmd(self.scene(), [it], "image"))
        # eklenen görsel seçili gelsin: köşelerden hemen boyutlandırılabilsin
        self.scene().clearSelection()
        it.setSelected(True)
        return it

    def insert_image_dialog(self):
        flt = t("image_filter") + " (" + " ".join("*" + e for e in IMAGE_EXT) + ")"
        files, _ = QFileDialog.getOpenFileNames(self.window(), t("insert_image"), "", flt)
        at = self.mapToScene(self.viewport().rect().center())
        for i, f in enumerate(files):
            img = read_image_file(f)
            if not img.isNull():
                self.insert_image(img, at + QPointF(30 * i, 30 * i))

    # ============================================================ sürükle-bırak
    def _mime_ok(self, md):
        if md.hasImage():
            return True
        if md.hasUrls():
            return any(u.isLocalFile() and u.toLocalFile().lower().endswith(IMAGE_EXT) for u in md.urls())
        return False

    def dragEnterEvent(self, e):
        if self._mime_ok(e.mimeData()):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if self._mime_ok(e.mimeData()):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dropEvent(self, e):
        sp = self.mapToScene(e.position().toPoint())
        if self.insert_from_mime(e.mimeData(), sp):
            e.acceptProposedAction()
            self.window().activateWindow()
            self.setFocus()

    # ============================================================ hızlı menü
    def _context_menu(self, pos):
        sp = self.mapToScene(pos)
        sc = self.scene()
        under = [it for it in sc.items(sp) if isinstance(it, (I.StrokeItem, I.TextItem, I.ImageItem))]
        target = under[0] if under else None
        m = QMenu(self)
        col = tcolor("text")

        def ic(n):
            return icons.icon(n, col, 18)
        if target is not None:
            if isinstance(target, I.TextItem):
                m.addAction(ic("edit"), t("edit_text"), lambda: self.edit_text(target))
            if isinstance(target, I.ImageItem):
                def copy_img():
                    QApplication.clipboard().setPixmap(target.pixmap())
                    self.toast(t("copied"))
                m.addAction(ic("copy"), t("copy_image"), copy_img)

                def pick():
                    self.scene().clearSelection()
                    target.setSelected(True)
                    self.toast(t("img_resize_hint"), 2200)
                m.addAction(ic("resize"), t("img_resize"), pick)
            m.addAction(ic("delete"), t("delete_this"), lambda: self.delete_item(target))
            m.addSeparator()
        for tool in ("pen", "hl", "laser", "eraser", "text", "select"):
            a = m.addAction(ic(ICON[tool]), f"{t('tool_' + tool)}\t{KEY[tool]}")
            a.triggered.connect(lambda _=False, x=tool: state.set_tool(x))
        sh = m.addMenu(ic("shapes"), t("shapes"))
        for tool in SHAPES:
            a = sh.addAction(ic(ICON[tool]), f"{t('tool_' + tool)}\t{KEY[tool]}")
            a.triggered.connect(lambda _=False, x=tool: state.set_tool(x))
        m.addSeparator()
        m.addAction(ic("text"), t("write_here") + "\tEnter", lambda: self.new_text(sp))
        a = m.addAction(ic("copy"), t("paste") + "\tCtrl+V", self.paste)
        md = QApplication.clipboard().mimeData()
        a.setEnabled(bool(md and (md.hasImage() or md.hasText() or md.hasUrls() or md.hasFormat(MIME_ITEMS))))
        m.addAction(ic("image"), t("insert_image") + "\tI", self.insert_image_dialog)
        m.addSeparator()
        m.addAction(ic("copy"), t("copy_page_image") + "\tCtrl+C", lambda: self.copy(only_image=True))
        if not self.fixed:
            m.addAction(ic("fit"), t("fit_all") + "\tF", self.fit_all)
        a = m.addAction(ic("delete"), t("clear_all"), self.clear_all)
        a.setEnabled(not self.is_empty())
        m.exec(self.viewport().mapToGlobal(pos))
