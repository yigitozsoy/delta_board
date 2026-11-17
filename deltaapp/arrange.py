"""Yerleştirme hesapları: hizala, eşit dağıt, yan yana / alt alta / ızgara / çember dizme.
Girdi: birimlerin (tek nesne ya da grup) sahne kutuları. Çıktı: her birimin kayacağı miktar (QPointF).
Saf geometri: Qt sahnesine dokunmaz, ayrı test edilebilir."""
import math

from PyQt6.QtCore import QPointF, QRectF

ALIGN = ("left", "hcenter", "right", "top", "vcenter", "bottom")
LAYOUTS = ("row", "column", "grid", "circle")


def bounds(rects):
    r = QRectF()
    for x in rects:
        r = r.united(x)
    return r


def auto_gap(rects):
    """Varsayılan boşluk: ortanca nesne boyunun ~%8'i (en az 12)."""
    if not rects:
        return 12.0
    sizes = sorted(max(r.width(), r.height()) for r in rects)
    return max(12.0, sizes[len(sizes) // 2] * 0.08)


def align(rects, mode):
    b = bounds(rects)
    out = []
    for r in rects:
        dx = dy = 0.0
        if mode == "left":
            dx = b.left() - r.left()
        elif mode == "hcenter":
            dx = b.center().x() - r.center().x()
        elif mode == "right":
            dx = b.right() - r.right()
        elif mode == "top":
            dy = b.top() - r.top()
        elif mode == "vcenter":
            dy = b.center().y() - r.center().y()
        elif mode == "bottom":
            dy = b.bottom() - r.bottom()
        out.append(QPointF(dx, dy))
    return out


def distribute(rects, axis):
    """Uçtakiler yerinde kalır, aradaki boşluklar eşitlenir (axis: "h" ya da "v")."""
    n = len(rects)
    out = [QPointF(0, 0) for _ in rects]
    if n < 3:
        return out
    h = axis == "h"
    order = sorted(range(n), key=lambda i: rects[i].center().x() if h else rects[i].center().y())
    first, last = rects[order[0]], rects[order[-1]]
    span = (last.right() - first.left()) if h else (last.bottom() - first.top())
    total = sum(rects[i].width() if h else rects[i].height() for i in order)
    gap = (span - total) / (n - 1)
    cur = first.left() if h else first.top()
    for i in order:
        r = rects[i]
        if h:
            out[i] = QPointF(cur - r.left(), 0)
            cur += r.width() + gap
        else:
            out[i] = QPointF(0, cur - r.top())
            cur += r.height() + gap
    return out


def _move_to(r, x, y):
    return QPointF(x - r.left(), y - r.top())


def row(rects, gap=None):
    """Yan yana, eşit boşlukla; dikeyde ortalanır. Soldaki birimden başlar, sıra korunur."""
    gap = auto_gap(rects) if gap is None else gap
    order = sorted(range(len(rects)), key=lambda i: rects[i].center().x())
    b = bounds(rects)
    cy = b.center().y()
    x = b.left()
    out = [QPointF(0, 0) for _ in rects]
    for i in order:
        r = rects[i]
        out[i] = _move_to(r, x, cy - r.height() / 2)
        x += r.width() + gap
    return out


def column(rects, gap=None):
    gap = auto_gap(rects) if gap is None else gap
    order = sorted(range(len(rects)), key=lambda i: rects[i].center().y())
    b = bounds(rects)
    cx = b.center().x()
    y = b.top()
    out = [QPointF(0, 0) for _ in rects]
    for i in order:
        r = rects[i]
        out[i] = _move_to(r, cx - r.width() / 2, y)
        y += r.height() + gap
    return out


def grid_shape(n):
    cols = max(1, math.ceil(math.sqrt(n)))
    return cols, max(1, math.ceil(n / cols))


def grid(rects, gap=None, cols=None):
    """Izgara: 10 nesne → 4 sütun × 3 satır. Hücre en büyük nesne boyunda, nesne hücrede ortalanır.
    Okuma sırası (yukarıdan aşağı, soldan sağa) korunur."""
    n = len(rects)
    out = [QPointF(0, 0) for _ in rects]
    if not n:
        return out
    gap = auto_gap(rects) if gap is None else gap
    cols = cols or grid_shape(n)[0]
    cw = max(r.width() for r in rects)
    ch = max(r.height() for r in rects)
    band = max(ch * 0.5, 1.0)
    order = sorted(range(n), key=lambda i: (round(rects[i].center().y() / band), rects[i].center().x()))
    b = bounds(rects)
    for k, i in enumerate(order):
        r = rects[i]
        c, rr = k % cols, k // cols
        x = b.left() + c * (cw + gap) + (cw - r.width()) / 2
        y = b.top() + rr * (ch + gap) + (ch - r.height()) / 2
        out[i] = _move_to(r, x, y)
    return out


def circle_radius(rects, gap=None):
    n = len(rects)
    gap = auto_gap(rects) if gap is None else gap
    d = max(max(r.width(), r.height()) for r in rects)
    if n < 2:
        return 0.0
    # komşu iki nesnenin merkezleri arası ≥ çap + boşluk olacak yarıçap
    return max((d + gap) / (2 * math.sin(math.pi / n)), d * 0.75)


def circle(rects, gap=None):
    """Çember: seçimin ortası merkez, ilk nesne tepede, saat yönünde eşit açılarla.
    Nesnelerin merkezin etrafındaki mevcut açı sırası korunur."""
    n = len(rects)
    out = [QPointF(0, 0) for _ in rects]
    if n < 2:
        return out
    c = bounds(rects).center()
    R = circle_radius(rects, gap)

    def ang(i):
        p = rects[i].center() - c
        a = math.atan2(p.y(), p.x()) + math.pi / 2     # tepeden başla
        return a % (2 * math.pi)
    order = sorted(range(n), key=ang)
    for k, i in enumerate(order):
        a = -math.pi / 2 + 2 * math.pi * k / n
        tgt = QPointF(c.x() + R * math.cos(a), c.y() + R * math.sin(a))
        out[i] = tgt - rects[i].center()
    return out


def layout(rects, kind, gap=None):
    return {"row": row, "column": column, "grid": grid, "circle": circle}[kind](rects, gap)


def snap_offsets(moving, targets, thr):
    """Akıllı kılavuz: taşınan kutunun kenar / ortası başka bir nesneninkine thr kadar yakınsa yapışma payı.
    Döner: (dx, dy, kılavuzlar) — kılavuz: ("v", x, y1, y2) ya da ("h", y, x1, x2)."""
    best_x = best_y = None
    mx = (moving.left(), moving.center().x(), moving.right())
    my = (moving.top(), moving.center().y(), moving.bottom())
    for t in targets:
        for a in mx:
            for bx in (t.left(), t.center().x(), t.right()):
                d = bx - a
                if abs(d) <= thr and (best_x is None or abs(d) < abs(best_x[0]) - 1e-9):
                    best_x = (d, bx, t)
        for a in my:
            for by in (t.top(), t.center().y(), t.bottom()):
                d = by - a
                if abs(d) <= thr and (best_y is None or abs(d) < abs(best_y[0]) - 1e-9):
                    best_y = (d, by, t)
    dx = best_x[0] if best_x else 0.0
    dy = best_y[0] if best_y else 0.0
    m = moving.translated(dx, dy)
    guides = []
    if best_x:
        t = best_x[2]
        guides.append(("v", best_x[1], min(m.top(), t.top()), max(m.bottom(), t.bottom())))
    if best_y:
        t = best_y[2]
        guides.append(("h", best_y[1], min(m.left(), t.left()), max(m.right(), t.right())))
    return dx, dy, guides
