"""Çizim tuvali: sonsuz alan, araçlar, gelişmiş fare kontrolleri, geri al / yinele.

Fare:
  sol sürükle ........ seçili araçla çiz          sağ basılı sürükle ... sil (dokunduğu çizgiyi siler)
  sağ kısa tık ....... hızlı menü                 orta sürükle / Boşluk+sol ... kaydır
  tekerlek ........... yakınlaştır (imlecin olduğu yere)    Alt+tekerlek ... kalınlık
  Shift+sol .......... düz çizgi (şekillerde kare/daire, 45°)   Ctrl+sol ... seç / taşı
  çift tık ........... oraya yazı yaz             orta çift tık ... hepsini sığdır
  yan tuşlar (geri/ileri) ... geri al / yinele
Seçimde: sürüklerken akıllı kılavuzlar (Alt basılıyken kapalı), ok tuşları kaydırır, üstte seçim çubuğu.
"""
import json
import math
import os
import time
import uuid

from PyQt6.QtCore import Qt, QPointF, QRectF, QSizeF, QTimer, pyqtSignal, QMimeData, QByteArray, QEvent
from PyQt6.QtGui import (QPainter, QColor, QPen, QPainterPath, QPainterPathStroker, QCursor, QPixmap, QImage,
                         QGuiApplication, QImageReader, QUndoCommand, QPolygonF)
from PyQt6.QtWidgets import (QGraphicsView, QMenu, QApplication, QFileDialog, QWidgetAction, QWidget, QHBoxLayout,
                             QSlider, QLabel)

from . import items as I
from . import icons
from . import arrange as A
from .config import prefs
from .i18n import t
from .theme import theme, qcolor, color as tcolor
from .tools import state, SHAPES, COLORS, COLOR_NAMES, DRAW_TOOLS, ICON, tool_key, tool_for_key, key_name

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
    def __init__(self, changes, text="move", merge_key=None):
        super().__init__(text)
        self.changes = changes  # [(item, (pos, scale), (pos, scale))]
        self.merge_key = merge_key   # ok tuşuyla art arda kaydırmalar tek geri al adımı olsun

    def id(self):
        return 7101 if self.merge_key else -1

    def mergeWith(self, other):
        if not isinstance(other, TransformCmd) or other.merge_key != self.merge_key:
            return False
        after = {id(it): a for it, _, a in other.changes}
        self.changes = [(it, b, after.get(id(it), a)) for it, b, a in self.changes]
        return True

    def redo(self):
        for it, _, (pos, sc) in self.changes:
            it.setPos(pos)
            it.setScale(sc)

    def undo(self):
        for it, (pos, sc), _ in self.changes:
            it.setPos(pos)
            it.setScale(sc)


class ZCmd(QUndoCommand):
    """Katman sırası: [(öğe, eski z, yeni z)]."""

    def __init__(self, changes, text="order"):
        super().__init__(text)
        self.changes = changes

    def redo(self):
        for it, _, z in self.changes:
            it.setZValue(z)

    def undo(self):
        for it, z, _ in self.changes:
            it.setZValue(z)


class AttrCmd(QUndoCommand):
    """Grup / kilit / gizli gibi özellikler: setter(öğe, değer)."""

    def __init__(self, items, setter, olds, news, text="attr"):
        super().__init__(text)
        self.items, self.setter, self.olds, self.news = list(items), setter, list(olds), list(news)

    def redo(self):
        for it, v in zip(self.items, self.news):
            self.setter(it, v)

    def undo(self):
        for it, v in zip(self.items, self.olds):
            self.setter(it, v)


class GeoCmd(QUndoCommand):
    """Döndür / çevir: [(öğe, önceki geo_state, sonraki geo_state)]."""

    def __init__(self, changes, text="rotate"):
        super().__init__(text)
        self.changes = changes

    def redo(self):
        for it, _, st in self.changes:
            I.set_geo_state(it, st)

    def undo(self):
        for it, st, _ in self.changes:
            I.set_geo_state(it, st)


class TableCmd(QUndoCommand):
    """Tablo içeriği / yapısı: önceki ve sonraki durum (TableItem.state)."""

    def __init__(self, it, before, after, text="table"):
        super().__init__(text)
        self.it, self.before, self.after = it, before, after

    def redo(self):
        self.it.set_state(self.after)

    def undo(self):
        self.it.set_state(self.before)


class CropCmd(QUndoCommand):
    """Kırpma: değişiklik önceden uygulanmış gelir (ilk redo atlanır)."""

    def __init__(self, it, before, after):
        super().__init__("crop")
        self.it, self.before, self.after, self._skip = it, before, after, True

    def redo(self):
        if self._skip:
            self._skip = False
            return
        I.set_crop_state(self.it, self.after)

    def undo(self):
        I.set_crop_state(self.it, self.before)


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

def render_scene(scene, items=None, scale=2.0, bg=None, max_side=8000, margin=24, fit=None, rect=None):
    """Nesneleri görüntüye çizer. fit=(g, y) verilirse o kutuya sığacak ölçek seçilir.
    rect verilirse tam o sahne alanı çizilir (kenar boşluğu yok, taşan kısımlar kırpılır)."""
    content = scene.content_items()
    items = [it for it in content if it.isVisible()] if items is None else [it for it in items if it.isVisible()]
    if not items:
        return None
    if rect is None:
        rect = QRectF()
        for it in items:
            rect = rect.united(it.sceneBoundingRect())
        rect.adjust(-margin, -margin, margin, margin)
    else:
        rect = QRectF(rect)
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
    selection_changed = pyqtSignal()

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

        self._guides = []          # akıllı kılavuzlar: ("v", x, y1, y2) / ("h", y, x1, x2)
        self._rot = None           # döndürme: (öğe, merkez, başlangıç açısı, başlangıç rot, önceki durum)
        self._crop = None          # kırpma modu: {"it", "before", "rect" (özgün piksel), "drag"}
        self._drag_items = None    # seçimle sürüklenen nesneler (kılavuz için)
        self._expanding = False
        self._sel_scene = None

        from .widgets import Toast
        from .selbar import SelectionBar
        self.toast_label = Toast(self)
        self.selbar = SelectionBar(self)
        self.zoom_changed.connect(lambda _z: self._update_selbar())
        state.changed.connect(self._update_cursor)
        theme.changed.connect(lambda _: self.refresh_theme())
        self._update_cursor()

    # ============================================================ sayfa
    def detach(self):
        """Kapanırken: sahne sinyallerini bırak. Yoksa çıkışta sahneler silinirken gelen "seçim değişti"
        yarı silinmiş tahtaya ulaşır ve süreç çöker (seçili bir şey varken kapatınca)."""
        self.finish_text()
        for sig, slot in ((getattr(self._sel_scene, "selectionChanged", None), self._on_scene_selection),
                          (getattr(self.page.undo, "indexChanged", None) if self.page else None, self._on_undo_index)):
            if sig is not None:
                try:
                    sig.disconnect(slot)
                except (TypeError, RuntimeError):
                    pass
        self._sel_scene = None
        self.selbar.hide()

    def set_page(self, page):
        self.finish_text()
        self.end_crop(True)
        if self.page is not None:
            self.store_view()
            try:
                self.page.undo.indexChanged.disconnect(self._on_undo_index)
            except (TypeError, RuntimeError):
                pass
        self.page = page
        page.ensure_loaded()
        if self._sel_scene is not None:
            try:
                self._sel_scene.selectionChanged.disconnect(self._on_scene_selection)
            except (TypeError, RuntimeError):
                pass
        self.setScene(page.scene)
        self._sel_scene = page.scene
        page.scene.selectionChanged.connect(self._on_scene_selection)
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
        self._on_scene_selection()

    def store_view(self):
        if self.page is None or self.fixed:
            return
        c = self.mapToScene(self.viewport().rect().center())
        self.page.view = {"z": round(self.zoom(), 4), "cx": round(c.x(), 1), "cy": round(c.y(), 1)}

    def _on_undo_index(self, _i):
        self.content_changed.emit()
        self._update_selbar()

    # ============================================================ seçim: gruplar + seçim çubuğu
    def _on_scene_selection(self):
        sc = self.scene()
        if sc is None:
            return
        if not self._expanding:
            # gruptan biri seçilince grubun tamamı seçilsin (tek parça taşınsın)
            gids = {I.group_of(it) for it in sc.selectedItems() if I.group_of(it)}
            if gids:
                self._expanding = True
                try:
                    for it in sc.content_items():
                        if I.group_of(it) in gids and not it.isSelected() and it.isVisible() and not I.is_locked(it):
                            it.setSelected(True)
                finally:
                    self._expanding = False
        self.selection_changed.emit()
        self._update_selbar()

    def _sel_units(self):
        """Seçimdeki birimler: grup üyeleri tek birim. [(üyeler, sahne kutusu)]"""
        units, by_gid = [], {}
        for it in self.selected():
            if I.is_locked(it) or not it.isVisible():
                continue
            g = I.group_of(it)
            if g:
                if g not in by_gid:
                    by_gid[g] = []
                    units.append(by_gid[g])
                by_gid[g].append(it)
            else:
                units.append([it])
        return [(u, A.bounds([I.exact_rect(x) for x in u])) for u in units]

    def selection_info(self):
        sel = self.selected()
        gids = {I.group_of(it) for it in sel}
        grouped = any(gids)
        texts = [it for it in sel if isinstance(it, I.TextItem)]
        return {"units": len(self._sel_units()), "items": len(sel), "grouped": grouped,
                "can_group": len(sel) >= 2 and not (len(gids) == 1 and grouped),
                "images": len([it for it in sel if isinstance(it, I.ImageItem)]),
                "shapes": len([it for it in sel if isinstance(it, I.StrokeItem) and it.kind in I.FILLABLE]),
                "texts": len(texts),
                "tables": len([it for it in sel if isinstance(it, I.TableItem)]),
                "border": all(it.border for it in sel if isinstance(it, I.TableItem)),
                "bold": bool(texts) and all(it.bold for it in texts),
                "italic": bool(texts) and all(it.italic for it in texts),
                "underline": bool(texts) and all(it.underline for it in texts)}

    def _update_selbar(self):
        bar = getattr(self, "selbar", None)
        if bar is None:
            return
        sc = self.scene()
        sel = [it for it in self.selected() if it.isVisible()] if sc else []
        self.viewport().update()     # döndürme tutamacı (drawForeground) yeni yerinde çizilsin
        if not sel or self._drag_items is not None or self._mode in ("imgresize", "rotate") \
                or self.editing_text() is not None or self._crop is not None:
            bar.hide()
            return
        r = A.bounds([I.exact_rect(it) for it in sel])
        vr = QRectF(self.mapFromScene(r).boundingRect())
        if not QRectF(self.viewport().rect()).intersects(vr):
            bar.hide()
            return
        bar.refresh(self.selection_info())
        bar.place(vr)

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        self._update_selbar()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update_selbar()

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
        if isinstance(fi, (I.TextItem, I.CellEditor)) and fi.editing():
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
        if isinstance(ft, I.CellEditor) and b == LEFT:
            tb = ft.table
            rc = tb.cell_at(tb.mapFromScene(sp))
            if rc is not None and rc != tb.edit:
                tb.start_edit(*rc)
                return
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
        if self._crop is not None:
            if b == LEFT:
                self._crop_press(pos, sp)
            return
        if b != LEFT:
            return
        rh = self._rot_handle()
        if rh is not None and self._near(pos, rh[1]):
            it, hp, c = rh
            a0 = math.degrees(math.atan2(sp.y() - c.y(), sp.x() - c.x()))
            self._rot = (it, c, a0, I.geom(it)[0], I.geo_state(it))
            self._mode, self._mode_btn = "rotate", b
            self.selbar.hide()
            return
        tc = self._table_col_at(sp)
        if tc is not None:
            tb, c = tc
            self._tc = (tb, c, tb.state(), tb.mapFromScene(sp).x(), tb.colw[c])
            self._mode, self._mode_btn = "tablecol", b
            self.selbar.hide()
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
            if under is not None and under.isSelected() and not I.is_locked(under):
                self._drag_items = [it for it in self.scene().selectedItems() if not I.is_locked(it)]
                self.selbar.hide()
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
            self.viewport().update()
            return
        if m == "rotate":
            self._rotate_to(sp, e.modifiers())
            return
        if m == "tablecol":
            tb, c, _, x0, w0 = self._tc
            tb.set_col_width(c, w0 + tb.mapFromScene(sp).x() - x0)
            return
        if self._crop is not None:
            self._crop_move(pos, sp, e.buttons())
            return
        if m == "select" and self._drag_items:
            super().mouseMoveEvent(e)
            self._snap_drag(e.modifiers())
            return
        if not m and e.buttons() == Qt.MouseButton.NoButton:
            h = self._image_handle_at(pos)
            rh = self._rot_handle()
            if rh is not None and self._near(pos, rh[1]):
                self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
                self._rs_cursor = True
            elif self._table_col_at(sp) is not None:
                self.viewport().setCursor(Qt.CursorShape.SplitHCursor)
                self._rs_cursor = True
            elif h is not None:
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
        if self._crop is not None and m is None:
            self._crop["drag"] = None
            return
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
        elif m == "tablecol":
            tb, _, before, _, _ = self._tc
            self._tc = None
            after = tb.state()
            if after != before:
                self.push(TableCmd(tb, before, after, "tablecol"))
            self._rs_cursor = False
            self._update_cursor()
        elif m == "rotate":
            it, _, _, _, before = self._rot
            self._rot = None
            after = I.geo_state(it)
            if after[2:5] != before[2:5]:
                self.push(GeoCmd([(it, before, after)]))
            self._update_cursor()
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
            if self._guides:
                self._guides = []
                self.viewport().update()
            self._drag_items = None
            if ch:
                self.push(TransformCmd(ch))
        elif m == "textclick":
            super().mouseReleaseEvent(e)
        self._cur = None
        self._press_view = None
        self._update_selbar()

    # ------------------------------------------------------------ akıllı kılavuzlar
    SNAP_PX = 7

    def _snap_drag(self, mods):
        items = [it for it in (self._drag_items or []) if it.scene() is self.scene()]
        if not items:
            return
        if mods & Qt.KeyboardModifier.AltModifier:
            if self._guides:
                self._guides = []
                self.viewport().update()
            return
        moving = A.bounds([I.exact_rect(it) for it in items])
        view = self.mapToScene(self.viewport().rect()).boundingRect()
        drag = set(items)
        targets = [I.exact_rect(it) for it in self.scene().content_items()
                   if it not in drag and it.isVisible() and I.exact_rect(it).intersects(view)][:400]
        dx, dy, guides = A.snap_offsets(moving, targets, self.SNAP_PX / max(self.zoom(), 1e-6))
        if dx or dy:
            for it in items:
                it.setPos(it.pos() + QPointF(dx, dy))
        if guides or self._guides:
            self._guides = guides
            self.viewport().update()

    def drawForeground(self, p, rect):
        z = max(self.zoom(), 1e-6)
        if self._guides:
            pen = QPen(I.SEL_COLOR, 1.2)
            pen.setCosmetic(True)
            p.setPen(pen)
            for kind, v, a, b in self._guides:
                if kind == "v":
                    p.drawLine(QPointF(v, a), QPointF(v, b))
                else:
                    p.drawLine(QPointF(a, v), QPointF(b, v))
        if self._crop is not None:
            self._draw_crop(p, z)
            return
        rh = self._rot_handle() if self._mode in (None, "rotate") else None
        if rh is not None:
            it, hp, c = rh
            lc = I.local_center(it)
            br = I.body_rect(it)
            top = it.mapToScene(QPointF(lc.x(), br.top()))
            pen = QPen(I.SEL_COLOR, 1.4)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.drawLine(top, hp)
            p.setBrush(QColor("#ffffff"))
            r = 6.5 / z
            p.drawEllipse(hp, r, r)
            # küçük dönüş oku
            pen2 = QPen(QColor("#3a3a3a"), 1.3)
            pen2.setCosmetic(True)
            p.setPen(pen2)
            p.setBrush(Qt.BrushStyle.NoBrush)
            rr = 3.2 / z
            p.drawArc(QRectF(hp.x() - rr, hp.y() - rr, 2 * rr, 2 * rr), 30 * 16, 270 * 16)

    def _draw_crop(self, p, z):
        c = self._crop
        it = c["it"]
        full = it.mapToScene(QRectF(it.full_rect()))
        inner = it.mapToScene(c["rect"])
        path = QPainterPath()
        path.addPolygon(full)
        hole = QPainterPath()
        hole.addPolygon(inner)
        p.fillPath(path.subtracted(hole), QColor(0, 0, 0, 150))
        pen = QPen(QColor("#ffffff"), 1.6)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolygon(inner)
        # üçte bir kılavuzları
        pen3 = QPen(QColor(255, 255, 255, 110), 1)
        pen3.setCosmetic(True)
        p.setPen(pen3)
        r = c["rect"]
        for k in (1, 2):
            x = r.left() + r.width() * k / 3
            y = r.top() + r.height() * k / 3
            p.drawLine(it.mapToScene(QPointF(x, r.top())), it.mapToScene(QPointF(x, r.bottom())))
            p.drawLine(it.mapToScene(QPointF(r.left(), y)), it.mapToScene(QPointF(r.right(), y)))
        p.setPen(QPen(I.SEL_COLOR, 1.4 / z))
        p.setBrush(QColor("#ffffff"))
        hs = 5 / z
        for lp in self._crop_points().values():
            q = it.mapToScene(lp)
            p.drawRect(QRectF(q.x() - hs, q.y() - hs, 2 * hs, 2 * hs))

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
        tb = self.table_at(sp)
        if tb is not None and not I.is_locked(tb):
            self._undo_last_dot()
            rc = tb.cell_at(tb.mapFromScene(sp))
            if rc is not None:
                self.edit_cell(tb, *rc)
            return
        if state.tool == "select":
            under = self.scene().itemAt(sp, self.transform())
            if isinstance(under, I.ImageItem) and not I.is_locked(under):
                self.start_crop(under)        # seç aracında görsele çift tık: kırp
                return
            if under is not None:
                return
        # İlk tıklamanın bıraktığı noktayı geri al, sonra oraya yazı aç
        self._undo_last_dot()
        self.new_text(sp)

    def _undo_last_dot(self):
        if self._last_dot and time.monotonic() - self._last_dot[1] < 0.6 and self.page.undo.canUndo():
            cmd = self.page.undo.command(self.page.undo.index() - 1)
            if isinstance(cmd, AddCmd) and self._last_dot[0] in cmd.items:
                self.page.undo.undo()
        self._last_dot = None

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
            if isinstance(it, (I.StrokeItem, I.TextItem)) and it.scene() is sc and it.isVisible() \
                    and not I.is_locked(it):
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
    def event(self, e):
        # Tab'ı sahne odak zincirine kaptırmadan tablo hücreleri arasında gezdir
        if e.type() == QEvent.Type.KeyPress and e.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            ed = self.editing_text()
            if isinstance(ed, I.CellEditor):
                back = e.key() == Qt.Key.Key_Backtab or bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                ed.table.move_edit(-1 if back else 1)
                return True
        return super().event(e)

    def keyPressEvent(self, e):
        if self.editing_text():
            super().keyPressEvent(e)
            return
        if self._crop is not None:
            if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.end_crop(True)
            elif e.key() == Qt.Key.Key_Escape:
                self.end_crop(False)
            return
        k = e.key()
        mods = e.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        K = Qt.Key
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)
        if ctrl and alt and e.text() and e.text().isprintable() and not e.text().isspace():
            self.scene().clearSelection()   # AltGr ile yazılan @ € { } gibi işaretler de yazı başlatır
            self.new_text(self._cursor_scene(), e.text())
            return
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
            elif k in (K.Key_I, 0x131):    # Türkçe klavyede ı
                self.insert_image_dialog()
            elif k == K.Key_R and not self.transparent:
                self.cycle_grid()
            elif k == K.Key_G:
                self.ungroup_selection() if shift else self.group_selection()
            elif k == K.Key_L:
                self.lock_selection()
            elif k == K.Key_PageUp:
                self.reorder("front" if shift else "forward")
            elif k == K.Key_PageDown:
                self.reorder("back" if shift else "backward")
            elif k in (K.Key_Up, K.Key_Down):
                state.nudge(1 if k == K.Key_Up else -1)
                self.toast(t("size_toast", n=f"{state.width:g}"), 700)
            else:
                e.ignore()
            return
        if mods & Qt.KeyboardModifier.AltModifier:
            e.ignore()
            return
        if k in (K.Key_Left, K.Key_Right, K.Key_Up, K.Key_Down) and self.selected():
            st = (10 if shift else 1) * max(1.0, 1 / max(self.zoom(), 1e-6))
            d = {K.Key_Left: (-st, 0), K.Key_Right: (st, 0), K.Key_Up: (0, -st), K.Key_Down: (0, st)}[k]
            self.nudge(*d)
            return
        # araç tuşları (varsayılan 1-9 / 0, Seçenekler'den değişir); Shift+1-7 renkler (sanal tuş kodu: düzenden bağımsız)
        vk = e.nativeVirtualKey()
        digit = None
        if 0x30 <= vk <= 0x39:
            digit = vk - 0x30
        elif 0x60 <= vk <= 0x69:          # sayı tuş takımı
            digit = vk - 0x60
        elif vk == 0 and K.Key_0 <= k <= K.Key_9:   # sanal tuş kodu olmayan (yapay) olaylar
            digit = k - K.Key_0
        if digit is not None and shift:
            if 1 <= digit <= len(COLORS):
                self.apply_color(COLORS[digit - 1])
            return
        tool = tool_for_key(key_name(e))
        if tool is not None:
            if not e.isAutoRepeat():
                state.set_tool(tool)
            return
        if digit is not None:
            return    # atanmamış rakam: yazı başlatmasın
        if k == K.Key_Home:
            self.fit_all()
            return
        if k in (K.Key_Delete, K.Key_Backspace):
            self.delete_selection()
            return
        if k in (K.Key_Return, K.Key_Enter):
            sel = [it for it in self.scene().selectedItems() if isinstance(it, I.TextItem)]
            tbs = [it for it in self.selected() if isinstance(it, I.TableItem) and not I.is_locked(it)]
            if len(sel) == 1:
                self.edit_text(sel[0])
            elif len(tbs) == 1 and len(self.selected()) == 1:
                self.edit_cell(tbs[0], 0, 0)
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
        # hızlı yazı: herhangi bir harfe / işarete basınca imlecin olduğu yerde yazı kutusu açılır
        ch = e.text()
        if ch and ch.isprintable() and not ch.isspace():
            self.scene().clearSelection()
            self.new_text(self._cursor_scene(), ch)
            return
        super().keyPressEvent(e)

    def cycle_grid(self):
        order = ["dots", "lines", "none"]
        cur = prefs.get("grid", "dots")
        prefs.set("grid", order[(order.index(cur) + 1) % 3] if cur in order else "dots")
        self.resetCachedContent()
        self.viewport().update()

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
        return [it for it in sc.selectedItems() if isinstance(it, I.CONTENT)] if sc else []

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

    # ------------------------------------------------------------ hizala / dağıt / diz
    def _move_units(self, units, deltas, text):
        ch = []
        for (members, _r), d in zip(units, deltas):
            if abs(d.x()) < 1e-6 and abs(d.y()) < 1e-6:
                continue
            for it in members:
                ch.append((it, (it.pos(), it.scale()), (it.pos() + d, it.scale())))
        if not ch:
            return False
        for it, _, (pos, _sc) in ch:
            it.setPos(pos)
        self.push(TransformCmd(ch, text))
        self._update_selbar()
        return True

    def align(self, mode):
        units = self._sel_units()
        if len(units) < 2:
            return
        self._move_units(units, A.align([r for _, r in units], mode), "align")

    def distribute(self, axis):
        units = self._sel_units()
        if len(units) < 3:
            return
        self._move_units(units, A.distribute([r for _, r in units], axis), "distribute")

    def arrange(self, kind):
        units = self._sel_units()
        if len(units) < 2:
            return
        if self._move_units(units, A.layout([r for _, r in units], kind), "arrange"):
            self.toast(t("arranged", n=len(units)))

    def same_size(self):
        """Seçili görselleri ortalama yüksekliğe getirir (en-boy oranı korunur, sol üst köşe yerinde kalır)."""
        imgs = [it for it in self.selected() if isinstance(it, I.ImageItem) and not I.is_locked(it)]
        if len(imgs) < 2:
            return
        hs = [it.pixmap().height() * it.scale() for it in imgs]
        target = sum(hs) / len(hs)
        ch = []
        for it in imgs:
            sc = target / max(1, it.pixmap().height())
            ch.append((it, (it.pos(), it.scale()), (it.pos(), sc)))
            it.setScale(sc)
        self.push(TransformCmd(ch, "size"))
        self._update_selbar()

    def nudge(self, dx, dy):
        items = [it for it in self.selected() if not I.is_locked(it)]
        if not items:
            return
        d = QPointF(dx, dy)
        ch = [(it, (it.pos(), it.scale()), (it.pos() + d, it.scale())) for it in items]
        for it in items:
            it.setPos(it.pos() + d)
        self.push(TransformCmd(ch, "nudge", merge_key=("nudge", frozenset(id(it) for it in items))))
        self._update_selbar()

    # ------------------------------------------------------------ grup / kilit / gizle
    def group_selection(self):
        sel = [it for it in self.selected() if not I.is_locked(it)]
        if len(sel) < 2:
            return
        gid = uuid.uuid4().hex[:10]
        self.push(AttrCmd(sel, I.set_group, [I.group_of(it) for it in sel], [gid] * len(sel), "group"))
        self.toast(t("grouped"))
        self._update_selbar()

    def ungroup_selection(self):
        sel = [it for it in self.selected() if I.group_of(it)]
        if not sel:
            return
        self.push(AttrCmd(sel, I.set_group, [I.group_of(it) for it in sel], [None] * len(sel), "ungroup"))
        self.toast(t("ungrouped"))
        self._update_selbar()

    def _with_group(self, items):
        gids = {I.group_of(it) for it in items if I.group_of(it)}
        out = list(items)
        if gids and self.scene():
            out += [it for it in self.scene().content_items() if I.group_of(it) in gids and it not in out]
        return out

    def set_locked(self, items, on):
        items = [it for it in self._with_group(items) if I.is_locked(it) != on]
        if not items:
            return
        self.push(AttrCmd(items, I.set_locked, [not on] * len(items), [on] * len(items), "lock"))
        self.toast(t("locked_toast") if on else t("unlocked_toast"), 1800)
        self._update_selbar()

    def lock_selection(self):
        self.set_locked(self.selected(), True)

    def set_hidden(self, items, on):
        items = [it for it in self._with_group(items) if it.isVisible() == on]
        if not items:
            return
        self.push(AttrCmd(items, I.set_hidden, [not on] * len(items), [on] * len(items), "hide"))
        self._update_selbar()

    # ------------------------------------------------------------ döndür / çevir
    ROT_GAP = 26     # döndürme tutamacının nesneden uzaklığı (ekran pikseli)

    def _near(self, pos, scene_pt, px=11):
        v = QPointF(self.mapFromScene(scene_pt))
        return math.hypot(v.x() - pos.x(), v.y() - pos.y()) <= px

    def _rot_handle(self):
        """Tek nesne seçiliyken döndürme tutamacı: (öğe, tutamaç noktası, merkez) — sahne koordinatı."""
        if self._crop is not None or self._drag_items is not None or self.editing_text() is not None:
            return None
        sel = [it for it in self.selected() if it.isVisible() and not I.is_locked(it)]
        if len(sel) != 1:
            return None
        it = sel[0]
        lc = I.local_center(it)
        br = I.body_rect(it)
        c = it.mapToScene(lc)
        top = it.mapToScene(QPointF(lc.x(), br.top()))
        v = top - c
        n = math.hypot(v.x(), v.y())
        if n < 1e-6:
            return None
        k = self.ROT_GAP / max(self.zoom(), 1e-6) / n
        return it, top + v * k, c

    def _rotate_to(self, sp, mods):
        it, c, a0, r0, _ = self._rot
        a = math.degrees(math.atan2(sp.y() - c.y(), sp.x() - c.x()))
        rot = (r0 + a - a0) % 360
        if mods & Qt.KeyboardModifier.ShiftModifier:
            rot = round(rot / 15) * 15
        else:
            near = round(rot / 90) * 90          # dik açılara yapış
            if abs(rot - near) < 4:
                rot = near
        _, fh, fv = I.geom(it)
        I.set_geom(it, rot, fh, fv)
        self.toast(f"{round(rot) % 360}°", 600)
        self.viewport().update()

    def _geo_change(self, fn, text):
        items = [it for it in self.selected() if not I.is_locked(it)]
        if not items:
            return
        ch = []
        for it in items:
            before = I.geo_state(it)
            fn(it)
            ch.append((it, before, I.geo_state(it)))
        self.push(GeoCmd(ch, text))
        self._update_selbar()

    def rotate_selection(self, deg):
        self._geo_change(lambda it: I.set_geom(it, I.geom(it)[0] + deg, *I.geom(it)[1:]), "rotate")

    def flip_selection(self, axis):
        def f(it):
            rot, fh, fv = I.geom(it)
            I.set_geom(it, rot, fh ^ (axis == "h"), fv ^ (axis == "v"))
        self._geo_change(f, "flip")

    def reset_rotation(self):
        self._geo_change(lambda it: I.set_geom(it, 0.0, False, False), "rotate")

    # ------------------------------------------------------------ kırpma
    def start_crop(self, it=None):
        if it is None:
            imgs = [x for x in self.selected() if isinstance(x, I.ImageItem)]
            it = imgs[0] if len(imgs) == 1 else None
        if it is None or I.is_locked(it) or self._crop is not None:
            return
        before = I.crop_state(it)
        rect = QRectF(it.crop_rect())
        I.set_crop_keep(it, it.full_rect())     # kırparken görüntünün tamamı görünsün
        self._crop = {"it": it, "before": before, "rect": rect, "drag": None}
        self.scene().clearSelection()
        self.selbar.hide()
        self.toast(t("crop_hint"), 2600)
        self.viewport().update()
        self.setFocus()

    def end_crop(self, apply=True):
        c = self._crop
        if c is None:
            return
        self._crop = None
        it = c["it"]
        r = c["rect"].toAlignedRect().intersected(it.full_rect())
        if apply and not r.isEmpty() and r != c["before"][0]:
            I.set_crop_keep(it, r)
            self.push(CropCmd(it, c["before"], I.crop_state(it)))
        else:
            I.set_crop_state(it, c["before"])
        if it.scene() is not None:
            it.setSelected(True)
        self.viewport().update()
        self._update_selbar()

    def _crop_points(self):
        """Kırpma çerçevesinin 8 tutamacı: {ad: yerel nokta}."""
        r = self._crop["rect"]
        cx, cy = r.center().x(), r.center().y()
        return {"tl": r.topLeft(), "t": QPointF(cx, r.top()), "tr": r.topRight(), "r": QPointF(r.right(), cy),
                "br": r.bottomRight(), "b": QPointF(cx, r.bottom()), "bl": r.bottomLeft(), "l": QPointF(r.left(), cy)}

    def _crop_press(self, pos, sp):
        c = self._crop
        it = c["it"]
        for k, lp in self._crop_points().items():
            if self._near(pos, it.mapToScene(lp)):
                c["drag"] = (k, None)
                return
        lp = it.mapFromScene(sp)
        if c["rect"].contains(lp):
            c["drag"] = ("move", (lp, QRectF(c["rect"])))
            return
        self.end_crop(True)          # dışarı tıklayınca uygula

    def _crop_move(self, pos, sp, buttons):
        c = self._crop
        if not (buttons & LEFT) or c.get("drag") is None:
            return
        it = c["it"]
        full = QRectF(it.full_rect())
        lp = it.mapFromScene(sp)
        k, data = c["drag"]
        r = QRectF(c["rect"])
        mn = 8.0
        if k == "move":
            start, r0 = data
            r = r0.translated(lp - start)
            dx = max(full.left() - r.left(), 0) + min(full.right() - r.right(), 0)
            dy = max(full.top() - r.top(), 0) + min(full.bottom() - r.bottom(), 0)
            r.translate(dx, dy)
        else:
            x = max(full.left(), min(lp.x(), full.right()))
            y = max(full.top(), min(lp.y(), full.bottom()))
            if "l" in k:
                r.setLeft(min(x, r.right() - mn))
            if "r" in k:
                r.setRight(max(x, r.left() + mn))
            if k.startswith("t"):
                r.setTop(min(y, r.bottom() - mn))
            if k.startswith("b"):
                r.setBottom(max(y, r.top() + mn))
        c["rect"] = r
        self.viewport().update()

    # ------------------------------------------------------------ saydamlık / dolgu / yazı biçimi
    def set_opacity_items(self, items, v, olds=None):
        items = list(items)
        olds = olds if olds is not None else [it.opacity() for it in items]
        news = [v] * len(items)
        if [round(o, 3) for o in olds] == [round(n, 3) for n in news]:
            return
        self.push(AttrCmd(items, I.set_opacity, olds, news, "opacity"))

    def fill_selection(self, col):
        items = [it for it in self.selected() if isinstance(it, I.StrokeItem) and it.kind in I.FILLABLE]
        if items:
            self.push(AttrCmd(items, I.set_fill, [it.fill for it in items], [col] * len(items), "fill"))

    def _texts(self):
        return [it for it in self.selected() if isinstance(it, I.TextItem)]

    def text_style_change(self, fn):
        items = self._texts()
        if not items:
            return
        olds = [I.text_style(it) for it in items]
        news = [fn(st) for st in olds]
        self.push(AttrCmd(items, I.set_text_style, olds, news, "textstyle"))
        self._update_selbar()

    def toggle_text(self, attr):
        idx = {"bold": 1, "italic": 2, "underline": 3}[attr]
        on = not all(I.text_style(it)[idx] for it in self._texts())

        def fn(st):
            st = list(st)
            st[idx] = on
            return tuple(st)
        self.text_style_change(fn)

    def text_size(self, factor):
        def clamp(v):
            return max(8.0, min(400.0, round(v * factor, 1)))
        tbs = [it for it in self.selected() if isinstance(it, I.TableItem)]
        if tbs:
            self.push(AttrCmd(tbs, I.set_table_size, [it.size for it in tbs], [clamp(it.size) for it in tbs],
                              "textstyle"))
        if self._texts():
            self.text_style_change(lambda st: (clamp(st[0]),) + tuple(st[1:]))
        self._update_selbar()

    # ------------------------------------------------------------ tablo
    def table_at(self, sp):
        for it in self.scene().items(sp):
            if isinstance(it, I.CellEditor):
                return it.table
            if isinstance(it, I.TableItem) and it.isVisible():
                return it
        return None

    def _table_col_at(self, sp):
        """Seç aracında tablonun sütun çizgisi imlecin altındaysa (tablo, sütun)."""
        if state.tool != "select" or self.scene() is None or self.editing_text() is not None:
            return None
        tol = 5 / max(self.zoom(), 1e-6)
        for it in self.scene().items(QRectF(sp.x() - tol, sp.y() - tol, 2 * tol, 2 * tol)):
            if isinstance(it, I.TableItem) and it.isVisible() and not I.is_locked(it):
                c = it.col_border_at(it.mapFromScene(sp), tol / max(it.scale(), 1e-6))
                if c is not None:
                    return it, c
        return None

    def insert_table(self, rows, cols, border=True, at=None):
        self.finish_text()
        size = max(12, round(state.text_px() * 0.72))
        it = I.TableItem(rows, cols, state.color, size, border, True)
        c = at if at is not None else self.mapToScene(self.viewport().rect().center())
        it.setPos(c - QPointF(it.table_rect().width() / 2, it.table_rect().height() / 2))
        it.setZValue(self.scene().next_z("table"))
        self.scene().addItem(it)
        self.push(AddCmd(self.scene(), [it], "table"))
        self.scene().clearSelection()
        it.setSelected(True)
        self.content_changed.emit()
        self.edit_cell(it, 0, 0)
        return it

    def edit_cell(self, tb, r, c):
        tb.on_changed = self._table_changed
        self.setFocus()
        tb.start_edit(r, c)

    def _table_changed(self, tb, before, after):
        self.push(TableCmd(tb, before, after, "tabletext"))
        self.content_changed.emit()
        self._update_selbar()
        if self.isVisible():
            QTimer.singleShot(0, self.setFocus)

    def table_op(self, tb, fn, text="table"):
        self.finish_text()
        before = tb.state()
        fn()
        after = tb.state()
        if after != before:
            self.push(TableCmd(tb, before, after, text))
            self.content_changed.emit()
        self._update_selbar()

    def set_table_border(self, tb, on):
        def f():
            tb.border = on
            tb.update()
        self.table_op(tb, f)

    def build_table_insert_menu(self, m, at=None):
        from .tablepick import TablePicker
        pk = TablePicker()
        wa = QWidgetAction(m)
        wa.setDefaultWidget(pk)
        m.addAction(wa)

        def done(r, c, border):
            m.close()
            top = m.parentWidget()
            while isinstance(top, QMenu):     # alt menüden seçildiyse ana menü de kapansın
                top.close()
                top = top.parentWidget()
            self.insert_table(r, c, border, at)
        pk.picked.connect(done)

    def build_table_menu(self, m, tb, cell=None):
        r, c = cell if cell is not None else (tb.rows - 1, tb.cols - 1)
        if cell is not None:
            m.addAction(self._ic("edit"), t("tbl_edit_cell") + "\t" + t("crop_dbl"), lambda: self.edit_cell(tb, r, c))
            m.addSeparator()
        m.addAction(self._ic("row_above"), t("tbl_row_above"), lambda: self.table_op(tb, lambda: tb.insert_row(r)))
        m.addAction(self._ic("row_below"), t("tbl_row_below"), lambda: self.table_op(tb, lambda: tb.insert_row(r + 1)))
        m.addAction(self._ic("col_left"), t("tbl_col_left"), lambda: self.table_op(tb, lambda: tb.insert_col(c)))
        m.addAction(self._ic("col_right"), t("tbl_col_right"), lambda: self.table_op(tb, lambda: tb.insert_col(c + 1)))
        m.addSeparator()
        a = m.addAction(self._ic("row_del"), t("tbl_row_del"), lambda: self.table_op(tb, lambda: tb.delete_row(r)))
        a.setEnabled(tb.rows > 1)
        a = m.addAction(self._ic("col_del"), t("tbl_col_del"), lambda: self.table_op(tb, lambda: tb.delete_col(c)))
        a.setEnabled(tb.cols > 1)
        m.addSeparator()

        def hdr():
            tb.header = not tb.header
            tb.relayout()
        # seçili olan tik simgesiyle gösterilir (menü işaret kutusu çizmiyor)
        for label, on, fn in ((t("tbl_header"), tb.header, lambda: self.table_op(tb, hdr)),
                              (t("tbl_border"), tb.border, lambda: self.set_table_border(tb, True)),
                              (t("tbl_borderless"), not tb.border, lambda: self.set_table_border(tb, False))):
            m.addAction(self._ic("check") if on else self._ic("blank"), label, fn)

    def _sel_table(self):
        sel = self.selected()
        return sel[0] if len(sel) == 1 and isinstance(sel[0], I.TableItem) else None

    def text_align(self, al):
        self.text_style_change(lambda st: tuple(st[:4]) + (al,))

    # ------------------------------------------------------------ katman sırası
    def layer_order(self):
        """Tüm nesneler, en arkadan en öne."""
        return sorted(self.scene().content_items(), key=lambda it: it.zValue()) if self.scene() else []

    def reorder(self, how, items=None):
        """how: front | forward | backward | back. Grup üyeleri birlikte hareket eder."""
        sc = self.scene()
        if sc is None:
            return
        sel = self._with_group(items if items is not None else self.selected())
        if not sel:
            return
        order = self.layer_order()
        chosen = set(sel)
        ch = []
        if how == "front":
            for it in sorted(sel, key=lambda i: i.zValue()):
                ch.append((it, it.zValue(), sc.front_z()))
        elif how == "back":
            low = order[0].zValue() if order else 0.0
            n = len(sel)
            for k, it in enumerate(sorted(sel, key=lambda i: i.zValue())):
                ch.append((it, it.zValue(), low - n + k))
        else:
            # bir adım: seçimle üst üste binen en yakın (seçili olmayan) nesneyle yer değiştir
            up = how == "forward"
            box = A.bounds([I.exact_rect(it) for it in sel])
            others = [it for it in order if it not in chosen]
            near = [it for it in others if I.exact_rect(it).intersects(box)] or others
            if up:
                top = max(it.zValue() for it in sel)
                cand = [it for it in near if it.zValue() > top]
                if not cand:
                    return
                tgt = min(cand, key=lambda i: i.zValue())
            else:
                bot = min(it.zValue() for it in sel)
                cand = [it for it in near if it.zValue() < bot]
                if not cand:
                    return
                tgt = max(cand, key=lambda i: i.zValue())
            # hedefle seçimin z değerleri yeniden dağıtılır (değer kümesi aynı kalır):
            # yukarı: hedef en alta iner, seçim üste çıkar; aşağı: hedef en üste çıkar
            zs = sorted([it.zValue() for it in sel] + [tgt.zValue()])
            seq = sorted(sel, key=lambda i: i.zValue())
            arranged = ([tgt] + seq) if up else (seq + [tgt])
            for it, z in zip(arranged, zs):
                if it.zValue() != z:
                    ch.append((it, it.zValue(), z))
        ch = [c for c in ch if c[1] != c[2]]
        if not ch:
            return
        for it, _, z in ch:
            it.setZValue(z)
        self.push(ZCmd(ch, how))
        self.content_changed.emit()

    def set_layer_order(self, items_back_to_front):
        """Katmanlar panelinden sürükleyerek: mevcut z değerleri yeni sıraya göre dağıtılır."""
        zs = sorted(it.zValue() for it in items_back_to_front)
        ch = [(it, it.zValue(), z) for it, z in zip(items_back_to_front, zs) if it.zValue() != z]
        if not ch:
            return
        for it, _, z in ch:
            it.setZValue(z)
        self.push(ZCmd(ch, "order"))
        self.content_changed.emit()

    # ------------------------------------------------------------ menüler (seçim çubuğu + sağ tık)
    def _ic(self, n):
        return icons.icon(n, tcolor("text"), 18)

    def build_align_menu(self, m):
        n = len(self._sel_units())
        for mode in A.ALIGN:
            a = m.addAction(self._ic("align_" + mode), t("al_" + mode), lambda _=False, x=mode: self.align(x))
            a.setEnabled(n >= 2)
            if mode == "right":
                m.addSeparator()
        m.addSeparator()
        for ax in ("h", "v"):
            a = m.addAction(self._ic("dist_" + ax), t("dist_" + ax), lambda _=False, x=ax: self.distribute(x))
            a.setEnabled(n >= 3)

    def build_arrange_menu(self, m):
        n = len(self._sel_units())
        for kind in A.LAYOUTS:
            a = m.addAction(self._ic("lay_" + kind), t("lay_" + kind), lambda _=False, x=kind: self.arrange(x))
            a.setEnabled(n >= 2)
        m.addSeparator()
        a = m.addAction(self._ic("same_size"), t("same_size"), self.same_size)
        a.setEnabled(len([it for it in self.selected() if isinstance(it, I.ImageItem)]) >= 2)

    def build_rotate_menu(self, m):
        m.addAction(self._ic("rotate_right"), t("rot_cw"), lambda: self.rotate_selection(90))
        m.addAction(self._ic("rotate_left"), t("rot_ccw"), lambda: self.rotate_selection(-90))
        m.addSeparator()
        m.addAction(self._ic("flip_h"), t("flip_h"), lambda: self.flip_selection("h"))
        m.addAction(self._ic("flip_v"), t("flip_v"), lambda: self.flip_selection("v"))
        a = m.addAction(self._ic("rot_reset"), t("rot_reset"), self.reset_rotation)
        a.setEnabled(any(any(I.geom(it)) for it in self.selected()))

    def build_opacity_menu(self, m):
        items = [it for it in self.selected() if not I.is_locked(it)]
        if not items:
            return
        olds = [it.opacity() for it in items]
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(10)
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(5, 100)
        sl.setFixedWidth(170)
        sl.setValue(int(round(min(olds) * 100)))
        lbl = QLabel(f"%{sl.value()}")
        lbl.setFixedWidth(42)

        def live(v):
            lbl.setText(f"%{v}")
            for it in items:
                I.set_opacity(it, v / 100)
        sl.valueChanged.connect(live)
        lay.addWidget(sl)
        lay.addWidget(lbl)
        wa = QWidgetAction(m)
        wa.setDefaultWidget(box)
        m.addAction(wa)
        m.aboutToHide.connect(lambda: self.set_opacity_items(items, sl.value() / 100, olds))

    def build_fill_menu(self, m):
        from PyQt6.QtGui import QIcon, QPixmap as _QP, QPainter as _QPa
        m.addAction(self._ic("fill_none"), t("fill_none"), lambda: self.fill_selection(None))
        m.addSeparator()
        for i, c in enumerate(COLORS):
            pm = _QP(18, 18)
            pm.fill(Qt.GlobalColor.transparent)
            pa = _QPa(pm)
            pa.setRenderHint(_QPa.RenderHint.Antialiasing)
            pa.setPen(QPen(QColor(tcolor("divider")), 1))
            pa.setBrush(I.ink(c))
            pa.drawEllipse(QRectF(2, 2, 14, 14))
            pa.end()
            m.addAction(QIcon(pm), t(COLOR_NAMES[i]), lambda _=False, x=c: self.fill_selection(x))

    def build_text_align_menu(self, m):
        for al in ("left", "center", "right"):
            m.addAction(self._ic("talign_" + al), t("talign_" + al), lambda _=False, x=al: self.text_align(x))

    def build_layer_menu(self, m, items=None):
        for how, key in (("front", "Ctrl+Shift+PgUp"), ("forward", "Ctrl+PgUp"), ("backward", "Ctrl+PgDown"),
                         ("back", "Ctrl+Shift+PgDown")):
            m.addAction(self._ic("z_" + how), t("z_" + how) + "\t" + key,
                        lambda _=False, x=how: self.reorder(x, items))

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

    def _image_copy_region(self, imgs):
        """Seçili görsel(ler)in tam sahne alanı, üstündeki çizimler ve görselin kendi çözünürlüğüne denk ölçek."""
        rect = QRectF()
        for it in imgs:
            rect = rect.united(it.mapRectToScene(QRectF(it.pixmap().rect())))
        items = [it for it in self.scene().content_items() if it.sceneBoundingRect().intersects(rect)]
        scale = max(1.0 / max(it.scale(), 1e-3) for it in imgs)
        return items, rect, max(1.0, min(scale, 4.0))

    def copy(self, only_image=False):
        sel = self.selected()
        items, rect, scale = sel or None, None, 2.0
        imgs = [it for it in sel if isinstance(it, I.ImageItem)]
        if not sel:
            all_imgs = [it for it in self.scene().content_items() if isinstance(it, I.ImageItem) and it.isVisible()]
            if len(all_imgs) == 1:
                imgs = all_imgs
        if imgs and (len(imgs) == len(sel) or not sel):
            # alıntı / görsel seçili: üstüne çizilenlerle birlikte, tam görsel sınırında kopyala
            items, rect, scale = self._image_copy_region(imgs)
        img = render_scene(self.scene(), items, scale=scale, rect=rect)
        if img is None:
            self.toast(t("nothing_to_copy"))
            return
        md = QMimeData()
        md.setImageData(img)
        if sel and not only_image:
            data = [I.to_dict(it) for it in (items or sel)]
            md.setData(MIME_ITEMS, QByteArray(json.dumps(data).encode("utf-8")))
        QApplication.clipboard().setMimeData(md)
        self.toast(t("copied_image_drawn") if rect is not None and len(items) > len(imgs)
                   else t("copied_image") if rect is not None
                   else t("copied_sel") if sel else t("copied_page"))

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

    def ocr_image(self, it):
        """Görseldeki yazıyı okuyup panoya kopyalar (Windows OCR)."""
        from .ocr import read_text
        self.toast(t("ocr_busy"), 1200)

        def done(text):
            if text:
                QApplication.clipboard().setText(text)
                self.toast(t("ocr_done", n=text.count("\n") + 1), 1800)
            else:
                self.toast(t("ocr_empty"), 1800)
        read_text(it.pixmap().toImage(), done, lambda _m: self.toast(t("ocr_failed"), 1800))

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
        rot, fh, fv = I.geom(it)
        if rot or fh or fv:
            # genel yol: karşı köşe sahnede sabit, ölçek = köşegen uzunluğu oranı
            r = QRectF(it.offset(), QSizeF(pw, ph))
            cs = {"tl": r.topLeft(), "tr": r.topRight(), "bl": r.bottomLeft(), "br": r.bottomRight()}
            opp = {"tl": "br", "tr": "bl", "bl": "tr", "br": "tl"}
            a_loc, d_loc = cs[opp[corner]], cs[corner]
            dl = math.hypot(d_loc.x() - a_loc.x(), d_loc.y() - a_loc.y())
            mn = 16 / max(self.zoom(), 1e-6) / max(pw, ph)
            sc = max(math.hypot(sp.x() - anchor.x(), sp.y() - anchor.y()) / max(dl, 1e-6), mn)
            it.setScale(sc)
            it.setPos(it.pos() + (anchor - it.mapToScene(a_loc)))
            return
        mn = 16 / max(self.zoom(), 1e-6) / max(pw, ph)
        s = max(abs(sp.x() - anchor.x()) / pw, abs(sp.y() - anchor.y()) / ph, mn)
        x = anchor.x() - pw * s if corner in ("tl", "bl") else anchor.x()
        y = anchor.y() - ph * s if corner in ("tl", "tr") else anchor.y()
        it.setScale(s)
        it.setPos(QPointF(x, y))

    def insert_image(self, img: QImage, center: QPointF, dpr=1.0, select=True, fit=False):
        """fit=True: görsel ekrandaki gerçek boyutunda kalır (görünüm ona yakınlaşır); False: görünüme sığdırılır."""
        if img.isNull():
            return None
        it = I.ImageItem.from_qimage(img)
        s = 1.0 / max(dpr, 0.1)
        vis = self.mapToScene(self.viewport().rect()).boundingRect()
        maxw, maxh = vis.width() * 0.75, vis.height() * 0.75
        w, h = img.width() * s, img.height() * s
        if not fit and (w > maxw or h > maxh):
            s *= min(maxw / w, maxh / h)
        it.setScale(s)
        it.setPos(center - QPointF(img.width() * s / 2, img.height() * s / 2))
        it.setZValue(self.scene().next_z("image"))
        self.scene().addItem(it)
        self.push(AddCmd(self.scene(), [it], "image"))
        self.scene().clearSelection()
        if select:      # eklenen görsel seçili gelsin: köşelerden hemen boyutlandırılabilsin
            it.setSelected(True)
        return it

    def fit_to(self, rect):
        """Görünümü verilen sahne alanına sığdırır (araç çubuğu payı bırakarak, en çok %100)."""
        if self.fixed or rect.isEmpty():
            return
        r = rect.adjusted(-40, -40, 40, 40)
        vp = self.viewport().rect()
        z = max(0.08, min(vp.width() / r.width(), (vp.height() - 90) / r.height(), 1.0))
        self.resetTransform()
        self.scale(z, z)
        self.centerOn(r.center() + QPointF(0, 30 / z))
        self.zoom_changed.emit(z)
        self._update_cursor()

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
        under = [it for it in sc.items(sp) if isinstance(it, I.CONTENT) and it.isVisible()]
        target = under[0] if under else None
        m = QMenu(self)
        col = tcolor("text")

        def ic(n):
            return icons.icon(n, col, 18)
        if state.tool in DRAW_TOOLS:
            from .widthmenu import build_width_menu
            build_width_menu(m, presets=False)
            m.addSeparator()
        if target is not None and I.is_locked(target):
            m.addAction(ic("lock_open"), t("sb_unlock"), lambda: self.set_locked([target], False))
            m.addSeparator()
            target = None
        sel_now = self.selected()
        if target is not None and target.isSelected() and len(sel_now) >= 2:
            self.build_align_menu(m.addMenu(ic("align_left"), t("sb_align")))
            self.build_arrange_menu(m.addMenu(ic("lay_grid"), t("sb_arrange")))
            info = self.selection_info()
            if info["can_group"]:
                m.addAction(ic("group"), t("sb_group"), self.group_selection)
            if info["grouped"]:
                m.addAction(ic("ungroup"), t("sb_ungroup"), self.ungroup_selection)
            self.build_layer_menu(m.addMenu(ic("layers"), t("sb_layer")))
            m.addAction(ic("lock"), t("sb_lock"), self.lock_selection)
            m.addAction(ic("delete"), t("sb_delete"), self.delete_selection)
            m.addSeparator()
            target = None
        if target is not None:
            if isinstance(target, I.TextItem):
                m.addAction(ic("edit"), t("edit_text"), lambda: self.edit_text(target))
            if isinstance(target, I.TableItem):
                self.build_table_menu(m.addMenu(ic("table"), t("table")), target,
                                      target.cell_at(target.mapFromScene(sp)))
            if isinstance(target, I.ImageItem):
                def copy_img():
                    QApplication.clipboard().setPixmap(target.pixmap())
                    self.toast(t("copied"))
                m.addAction(ic("copy"), t("copy_image"), copy_img)
                m.addAction(ic("text"), t("ocr"), lambda: self.ocr_image(target))

                def pick():
                    self.scene().clearSelection()
                    target.setSelected(True)
                    self.toast(t("img_resize_hint"), 2200)
                m.addAction(ic("resize"), t("img_resize"), pick)
                if not I.is_locked(target):
                    m.addAction(ic("crop"), t("crop") + "\t" + t("crop_dbl"), lambda: self.start_crop(target))
            self.build_layer_menu(m.addMenu(ic("layers"), t("sb_layer")), [target])
            m.addAction(ic("lock"), t("sb_lock"), lambda: self.set_locked([target], True))
            m.addAction(ic("delete"), t("delete_this"), lambda: self.delete_item(target))
            m.addSeparator()
        for tool in ("pen", "hl", "laser", "eraser", "text", "select"):
            a = m.addAction(ic(ICON[tool]), f"{t('tool_' + tool)}\t{tool_key(tool)}")
            a.triggered.connect(lambda _=False, x=tool: state.set_tool(x))
        sh = m.addMenu(ic("shapes"), t("shapes"))
        for tool in SHAPES:
            a = sh.addAction(ic(ICON[tool]), f"{t('tool_' + tool)}\t{tool_key(tool)}")
            a.triggered.connect(lambda _=False, x=tool: state.set_tool(x))
        m.addSeparator()
        m.addAction(ic("text"), t("write_here") + "\tEnter", lambda: self.new_text(sp))
        a = m.addAction(ic("copy"), t("paste") + "\tCtrl+V", self.paste)
        md = QApplication.clipboard().mimeData()
        a.setEnabled(bool(md and (md.hasImage() or md.hasText() or md.hasUrls() or md.hasFormat(MIME_ITEMS))))
        m.addAction(ic("image"), t("insert_image") + "\tI", self.insert_image_dialog)
        self.build_table_insert_menu(m.addMenu(ic("table"), t("insert_table")), sp)
        m.addSeparator()
        m.addAction(ic("copy"), t("copy_page_image") + "\tCtrl+C", lambda: self.copy(only_image=True))
        if not self.fixed:
            m.addAction(ic("fit"), t("fit_all") + "\tF", self.fit_all)
        a = m.addAction(ic("delete"), t("clear_all"), self.clear_all)
        a.setEnabled(not self.is_empty())
        m.exec(self.viewport().mapToGlobal(pos))
