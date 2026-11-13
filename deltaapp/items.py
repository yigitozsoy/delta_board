"""Tuval nesneleri: kalem / fosforlu / şekil çizgileri, yazı, görsel ve lazer izi.
Hepsi sözlüğe çevrilip (not dosyası, kopyala-yapıştır) geri okunabilir."""
import base64
import math
import time

from PyQt6.QtCore import Qt, QPointF, QRectF, QByteArray, QBuffer, QIODevice
from PyQt6.QtGui import (QPainterPath, QPen, QColor, QPainterPathStroker, QFont, QPixmap, QImage, QTextCursor,
                         QBrush)
from PyQt6.QtWidgets import (QGraphicsPathItem, QGraphicsTextItem, QGraphicsPixmapItem, QGraphicsItem,
                             QGraphicsScene, QStyle)

from .theme import color as theme_color

SEL_COLOR = QColor("#3ea6ff")
Z_BASE = {"image": -3_000_000, "hl": -2_000_000}
FLAGS = QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable


def ink(name) -> QColor:
    """Renk adı: "auto" = tema metin rengi (koyu temada beyaz, açıkta siyah)."""
    if not name or name == "auto":
        return QColor(theme_color("text"))
    return QColor(name)


class DeltaScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSceneRect(-200000, -200000, 400000, 400000)
        self.zseq = 0

    def next_z(self, kind):
        self.zseq += 1
        return Z_BASE.get(kind, 0) + self.zseq

    def content_items(self):
        return [it for it in self.items() if isinstance(it, (StrokeItem, TextItem, ImageItem))]

    def restyle(self):
        for it in self.content_items():
            it.apply_style()


def _strip_state(opt):
    sel = bool(opt.state & QStyle.StateFlag.State_Selected)
    opt.state = opt.state & ~QStyle.StateFlag.State_Selected & ~QStyle.StateFlag.State_HasFocus
    return sel


def _draw_sel(p, rect, dashed=True):
    pen = QPen(SEL_COLOR, 1.4)
    pen.setCosmetic(True)
    if dashed:
        pen.setStyle(Qt.PenStyle.DashLine)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(rect)


def simplify(pts, eps):
    """Ramer–Douglas–Peucker: çizgiyi bozmadan gereksiz noktaları atar."""
    n = len(pts)
    if n < 3:
        return list(pts)
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay, bx, by = pts[a].x(), pts[a].y(), pts[b].x(), pts[b].y()
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy)
        best, bi = -1.0, -1
        for i in range(a + 1, b):
            px, py = pts[i].x(), pts[i].y()
            d = math.hypot(px - ax, py - ay) if L < 1e-9 else abs(dy * px - dx * py + bx * ay - by * ax) / L
            if d > best:
                best, bi = d, i
        if best > eps:
            keep[bi] = True
            stack.append((a, bi))
            stack.append((bi, b))
    return [p for p, k in zip(pts, keep) if k]


def smooth_path(pts):
    path = QPainterPath()
    if not pts:
        return path
    path.moveTo(pts[0])
    if len(pts) == 1:
        path.lineTo(pts[0] + QPointF(0.01, 0.0))  # tek tık = nokta
        return path
    if len(pts) == 2:
        path.lineTo(pts[1])
        return path
    for i in range(1, len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        path.quadTo(a, QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2))
    path.lineTo(pts[-1])
    return path


class StrokeItem(QGraphicsPathItem):
    """Serbest çizgi (pen / hl) ya da iki noktalı şekil (line / arrow / rect / ellipse)."""

    def __init__(self, kind, color="auto", width=4.0, pts=None):
        super().__init__()
        self.kind = kind
        self.color_name = color
        self.width = float(width)
        self.pts = list(pts or [])
        self.setFlags(FLAGS)
        self.apply_style()
        self.rebuild(smooth=True)

    def apply_style(self):
        c = ink(self.color_name)
        if self.kind == "hl":
            c.setAlpha(105)
        pen = QPen(c, self.width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        self.setPen(pen)

    # --- canlı çizim
    def add_point(self, p):
        self.pts.append(p)
        path = self.path()
        if path.elementCount() == 0:
            path.moveTo(p)
        else:
            path.lineTo(p)
        self.setPath(path)

    def set_points(self, pts):
        self.pts = list(pts)
        self.rebuild()

    def finish(self, zoom=1.0):
        if self.kind in ("pen", "hl") and len(self.pts) > 2:
            self.pts = simplify(self.pts, 0.35 / max(zoom, 0.05))
        self.rebuild(smooth=True)

    def rebuild(self, smooth=True):
        pts = self.pts
        path = QPainterPath()
        if self.kind in ("pen", "hl"):
            path = smooth_path(pts)
        elif len(pts) >= 2:
            a, b = pts[0], pts[-1]
            if self.kind == "line":
                path.moveTo(a)
                path.lineTo(b)
            elif self.kind == "arrow":
                path.moveTo(a)
                path.lineTo(b)
                dx, dy = b.x() - a.x(), b.y() - a.y()
                if math.hypot(dx, dy) > 1:
                    ang = math.atan2(dy, dx)
                    h = max(12.0, self.width * 3.4)
                    l_, r_ = ang + math.pi - 0.45, ang + math.pi + 0.45
                    path.moveTo(QPointF(b.x() + h * math.cos(l_), b.y() + h * math.sin(l_)))
                    path.lineTo(b)
                    path.lineTo(QPointF(b.x() + h * math.cos(r_), b.y() + h * math.sin(r_)))
            elif self.kind == "rect":
                path.addRoundedRect(QRectF(a, b).normalized(), 2, 2)
            elif self.kind == "ellipse":
                path.addEllipse(QRectF(a, b).normalized())
        elif pts:
            path.moveTo(pts[0])
            path.lineTo(pts[0] + QPointF(0.01, 0))
        self.setPath(path)

    def shape(self):
        st = QPainterPathStroker()
        st.setWidth(max(self.width, 6.0))
        st.setCapStyle(Qt.PenCapStyle.RoundCap)
        st.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return st.createStroke(self.path())

    def paint(self, p, opt, w=None):
        sel = _strip_state(opt)
        super().paint(p, opt, w)
        if sel:
            _draw_sel(p, self.boundingRect())


class TextItem(QGraphicsTextItem):
    kind = "text"

    def __init__(self, text="", color="auto", size=26):
        super().__init__()
        self.color_name = color
        self.size = float(size)
        f = QFont("Segoe UI Variable Text")
        f.setPixelSize(max(6, int(round(self.size))))
        f.setWeight(QFont.Weight.Medium)
        self.setFont(f)
        self.document().setDocumentMargin(4)
        self.setPlainText(text)
        self.setFlags(FLAGS)
        self.on_finished = None   # fn(item, önceki, sonraki, yeni_mi)
        self._before = None
        self.is_new = False
        self.apply_style()

    def apply_style(self):
        self.setDefaultTextColor(ink(self.color_name))

    def editing(self):
        return bool(self.textInteractionFlags() & Qt.TextInteractionFlag.TextEditorInteraction)

    def start_edit(self, select_all=False):
        if not self.editing():
            self._before = self.toPlainText()
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        c = self.textCursor()
        c.movePosition(QTextCursor.MoveOperation.End)
        if select_all:
            c.select(QTextCursor.SelectionType.Document)
        self.setTextCursor(c)

    def finish_edit(self):
        if not self.editing():
            return
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        c = self.textCursor()
        c.clearSelection()
        self.setTextCursor(c)
        txt = self.toPlainText().rstrip()
        self.setPlainText(txt)  # yapıştırılan zengin metni düz metne çevirir (renk temadan gelsin)
        before, new = self._before, self.is_new
        self._before, self.is_new = None, False
        if self.on_finished:
            self.on_finished(self, before or "", txt, new)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        if e.reason() != Qt.FocusReason.PopupFocusReason:
            self.finish_edit()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape or (e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                                            and e.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.clearFocus()
            return
        super().keyPressEvent(e)

    def paint(self, p, opt, w=None):
        sel = _strip_state(opt)
        super().paint(p, opt, w)
        if self.editing():
            _draw_sel(p, self.boundingRect(), dashed=True)
        elif sel:
            _draw_sel(p, self.boundingRect())


class ImageItem(QGraphicsPixmapItem):
    """Görsel. Seçiliyken köşe tutamaçlarından orantılı büyütülüp küçültülür (Board.mousePressEvent)."""
    kind = "image"
    HANDLE = 12  # ekran pikseli

    def __init__(self, png: bytes, scale=1.0):
        super().__init__()
        self.png = png
        pm = QPixmap()
        pm.loadFromData(png)
        pm.setDevicePixelRatio(1.0)
        self.setPixmap(pm)
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.setShapeMode(QGraphicsPixmapItem.ShapeMode.BoundingRectShape)
        self.setFlags(FLAGS)
        self.setScale(scale)
        self.color_name = None

    @classmethod
    def from_qimage(cls, img: QImage, scale=1.0):
        return cls(image_png_bytes(img), scale)

    def apply_style(self):
        pass

    def paint(self, p, opt, w=None):
        sel = _strip_state(opt)
        super().paint(p, opt, w)
        if sel:
            r = self.boundingRect()
            _draw_sel(p, r, dashed=False)
            # dört köşe tutamacı (boyutlandırmayı Board yapar, her araçta çalışır)
            s = p.worldTransform().m11() or 1.0
            hs = self.HANDLE / s
            p.setBrush(QBrush(QColor("#ffffff")))
            pen = QPen(SEL_COLOR, 1.6)
            pen.setCosmetic(True)
            p.setPen(pen)
            # kareler görselin içinde kalır (sınır dışına çizmek iz bırakır)
            for x in (r.left(), r.right() - hs):
                for y in (r.top(), r.bottom() - hs):
                    p.drawRect(QRectF(x, y, hs, hs))


class LaserItem(QGraphicsItem):
    """Lazer işaretçi: arkasında ~0.8 sn'de kaybolan kırmızı iz bırakır. Kaydedilmez, geri alınmaz."""
    kind = "laser"
    LIFE = 0.8

    def __init__(self):
        super().__init__()
        self.pts = []  # (QPointF, zaman)
        self._rect = QRectF()
        self.active = True
        self.setZValue(9e12)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def add(self, p):
        self.prepareGeometryChange()
        self.pts.append((p, time.monotonic()))
        self._calc()

    def _calc(self):
        if not self.pts:
            self._rect = QRectF()
            return
        xs = [q.x() for q, _ in self.pts]
        ys = [q.y() for q, _ in self.pts]
        m = 80
        self._rect = QRectF(min(xs) - m, min(ys) - m, max(xs) - min(xs) + 2 * m, max(ys) - min(ys) + 2 * m)

    def tick(self, now):
        cut = now - self.LIFE
        if self.pts and self.pts[0][1] < cut:
            self.prepareGeometryChange()
            keep = [x for x in self.pts if x[1] >= cut]
            # Fare basılı ve hareketsizken son nokta (imleç ucu) kalsın
            if not keep and self.active:
                keep = [self.pts[-1]]
            self.pts = keep
            self._calc()
        self.update()
        return bool(self.pts) or self.active

    def boundingRect(self):
        return self._rect

    def paint(self, p, opt, w=None):
        n = len(self.pts)
        if not n:
            return
        now = time.monotonic()
        p.setRenderHint(p.RenderHint.Antialiasing)
        scale = p.worldTransform().m11() or 1.0
        for width, alpha in ((14, 55), (5, 255)):
            for i in range(1, n):
                (a, _), (b, tb) = self.pts[i - 1], self.pts[i]
                k = max(0.0, min(1.0, 1 - (now - tb) / self.LIFE))
                if k <= 0:
                    continue
                pen = QPen(QColor(255, 45, 45, int(alpha * k)), width * (0.55 + 0.45 * k))
                pen.setCosmetic(True)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawLine(a, b)
        if self.active:
            tip = self.pts[-1][0]
            r = 6 / scale
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 45, 45, 70))
            p.drawEllipse(tip, r * 2.2, r * 2.2)
            p.setBrush(QColor(255, 60, 60))
            p.drawEllipse(tip, r, r)


# ---------------------------------------------------------------- dönüştürme

def image_png_bytes(img: QImage) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def to_dict(it):
    pos = [round(it.pos().x(), 2), round(it.pos().y(), 2)]
    z = it.zValue()
    if isinstance(it, StrokeItem):
        return {"t": "stroke", "k": it.kind, "c": it.color_name, "w": it.width, "pos": pos, "z": z,
                "p": [round(v, 2) for q in it.pts for v in (q.x(), q.y())]}
    if isinstance(it, TextItem):
        return {"t": "text", "c": it.color_name, "s": it.size, "txt": it.toPlainText(), "pos": pos, "z": z}
    if isinstance(it, ImageItem):
        return {"t": "image", "sc": it.scale(), "pos": pos, "z": z, "png": base64.b64encode(it.png).decode("ascii")}
    return None


def from_dict(d):
    try:
        t = d.get("t")
        if t == "stroke":
            p = d.get("p") or []
            pts = [QPointF(p[i], p[i + 1]) for i in range(0, len(p) - 1, 2)]
            it = StrokeItem(d.get("k", "pen"), d.get("c", "auto"), d.get("w", 4), pts)
        elif t == "text":
            it = TextItem(d.get("txt", ""), d.get("c", "auto"), d.get("s", 26))
        elif t == "image":
            it = ImageItem(base64.b64decode(d.get("png", "")), float(d.get("sc", 1.0)))
            if it.pixmap().isNull():
                return None
        else:
            return None
        pos = d.get("pos") or [0, 0]
        it.setPos(QPointF(pos[0], pos[1]))
        it.setZValue(float(d.get("z", 0)))
        return it
    except Exception:
        return None
