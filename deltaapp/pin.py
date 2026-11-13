"""Ekrana iğnelenen alıntı: her zaman üstte duran küçük görsel pencere.
Sürükle: taşı · tekerlek: büyüt/küçült · Ctrl+tekerlek: saydamlık · çift tık / Esc: kapat · sağ tık: menü."""
import os
from datetime import datetime

from PyQt6.QtCore import Qt, QObject, pyqtSignal, QPoint, QPointF, QRect, QRectF, QSize, QTimer
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QAction
from PyQt6.QtWidgets import QWidget, QMenu, QApplication

from .config import snapshot_dir
from .i18n import t

MIN_SCALE, MAX_SCALE = 0.2, 5.0
CLOSE_R = 11  # sağ üstteki kapat düğmesinin yarıçapı


class PinWindow(QWidget):
    def __init__(self, mgr, pixmap, pos):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.Tool)
        self.mgr = mgr
        self.pix = pixmap
        self.base = pixmap.deviceIndependentSize()
        self.scale = 1.0
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setToolTip("")
        self._drag = None
        self._hover = False
        self._chip = ""
        self._chip_timer = QTimer(self, singleShot=True, interval=900)
        self._chip_timer.timeout.connect(self._hide_chip)
        self.setGeometry(QRect(pos, self._size()))

    def _size(self):
        return QSize(max(16, round(self.base.width() * self.scale)), max(16, round(self.base.height() * self.scale)))

    # --- çizim
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        p.drawPixmap(r, self.pix, QRectF(self.pix.rect()))
        # ince çerçeve: hem açık hem koyu görselde seçilsin diye iki tonlu
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 120), 1))
        p.drawRect(r.adjusted(0.5, 0.5, -0.5, -0.5))
        p.setPen(QPen(QColor(255, 255, 255, 150 if self._hover else 70), 1))
        p.drawRect(r.adjusted(1.5, 1.5, -1.5, -1.5))
        if self._hover and self.width() > 60 and self.height() > 40:
            c = self._close_center()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(28, 28, 28, 220))
            p.drawEllipse(c, CLOSE_R, CLOSE_R)
            p.setPen(QPen(QColor("#f1f1f1"), 1.6))
            d = 4.0
            p.drawLine(QPointF(c.x() - d, c.y() - d), QPointF(c.x() + d, c.y() + d))
            p.drawLine(QPointF(c.x() - d, c.y() + d), QPointF(c.x() + d, c.y() - d))
        if self._chip:
            f = QFont("Segoe UI Variable Text")
            f.setPixelSize(12)
            f.setWeight(QFont.Weight.DemiBold)
            p.setFont(f)
            tw = p.fontMetrics().horizontalAdvance(self._chip) + 16
            cr = QRectF(6, self.height() - 28, tw, 22)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(28, 28, 28, 230))
            p.drawRoundedRect(cr, 6, 6)
            p.setPen(QColor("#ffffff"))
            p.drawText(cr, Qt.AlignmentFlag.AlignCenter, self._chip)

    def _close_center(self):
        return QPointF(self.width() - CLOSE_R - 6, CLOSE_R + 6)

    def _on_close_btn(self, pos):
        if not (self.width() > 60 and self.height() > 40):
            return False
        c = self._close_center()
        return (QPointF(pos) - c).manhattanLength() <= CLOSE_R * 1.4

    def _show_chip(self, txt):
        self._chip = txt
        self._chip_timer.start()
        self.update()

    def _hide_chip(self):
        self._chip = ""
        self.update()

    # --- fare
    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self._on_close_btn(e.position()):
                self.close()
                return
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
        elif e.button() == Qt.MouseButton.MiddleButton:
            self.close()

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)
        else:
            on = self._on_close_btn(e.position()) and self._hover
            self.setCursor(Qt.CursorShape.PointingHandCursor if on else Qt.CursorShape.SizeAllCursor)

    def mouseReleaseEvent(self, e):
        self._drag = None

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.close()

    def wheelEvent(self, e):
        dy = e.angleDelta().y()
        if not dy:
            return
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            op = min(1.0, max(0.2, self.windowOpacity() + (0.1 if dy > 0 else -0.1)))
            self.setWindowOpacity(op)
            self._show_chip(f"{t('pin_opacity')} %{round(op * 100)}")
        else:
            self.set_scale(self.scale * (1.1 if dy > 0 else 1 / 1.1), e.position())

    def set_scale(self, s, anchor=None):
        s = min(MAX_SCALE, max(MIN_SCALE, s))
        if abs(s - self.scale) < 1e-6:
            return
        g = self.geometry()
        if anchor is None:
            anchor = QPointF(g.width() / 2, g.height() / 2)
        k = s / self.scale
        self.scale = s
        size = self._size()
        # imlecin altındaki nokta yerinde kalsın
        nx = g.x() + anchor.x() - anchor.x() * k
        ny = g.y() + anchor.y() - anchor.y() * k
        self.setGeometry(QRect(QPoint(round(nx), round(ny)), size))
        self._show_chip(f"%{round(s * 100)}")

    def keyPressEvent(self, e):
        k = e.key()
        ctrl = e.modifiers() & Qt.KeyboardModifier.ControlModifier
        if k in (Qt.Key.Key_Escape, Qt.Key.Key_Delete):
            self.close()
        elif ctrl and e.modifiers() & Qt.KeyboardModifier.ShiftModifier and k == Qt.Key.Key_C:
            self.ocr()
        elif ctrl and k == Qt.Key.Key_C:
            self.copy()
        elif ctrl and k == Qt.Key.Key_S:
            self.save()
        elif k in (Qt.Key.Key_0,):
            self.set_scale(1.0)
        elif k in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.set_scale(self.scale * 1.1)
        elif k == Qt.Key.Key_Minus:
            self.set_scale(self.scale / 1.1)
        elif k in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            step = 10 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
            dx = {Qt.Key.Key_Left: -step, Qt.Key.Key_Right: step}.get(k, 0)
            dy = {Qt.Key.Key_Up: -step, Qt.Key.Key_Down: step}.get(k, 0)
            self.move(self.pos() + QPoint(dx, dy))

    def contextMenuEvent(self, e):
        m = QMenu(self)
        items = [
            (t("copy") + "\tCtrl+C", self.copy),
            (t("save") + "\tCtrl+S", self.save),
            (t("cap_to_delta"), self.send),
            (t("ocr") + "\tCtrl+Shift+C", self.ocr),
            None,
            (t("pin_reset") + "\t0", lambda: self.set_scale(1.0)),
        ]
        for it in items:
            if it is None:
                m.addSeparator()
                continue
            a = QAction(it[0], m)
            a.triggered.connect(it[1])
            m.addAction(a)
        a_op = QAction(t("pin_half"), m)
        a_op.setCheckable(True)
        a_op.setChecked(self.windowOpacity() < 0.99)
        a_op.toggled.connect(lambda on: self.setWindowOpacity(0.55 if on else 1.0))
        m.addAction(a_op)
        m.addSeparator()
        a = QAction(t("close") + "\tEsc", m)
        a.triggered.connect(self.close)
        m.addAction(a)
        if len(self.mgr.pins) > 1:
            a = QAction(t("pin_close_all"), m)
            a.triggered.connect(self.mgr.close_all)
            m.addAction(a)
        m.exec(e.globalPos())

    # --- işler
    def plain(self):
        q = self.pix.copy()
        q.setDevicePixelRatio(1.0)
        return q

    def copy(self):
        QApplication.clipboard().setPixmap(self.plain())
        self._show_chip("✓ " + t("copied"))

    def ocr(self):
        from .ocr import read_text
        self._show_chip(t("ocr_busy"))

        def done(text):
            if text:
                QApplication.clipboard().setText(text)
                self._show_chip("✓ " + t("ocr_done", n=text.count("\n") + 1))
            else:
                self._show_chip(t("ocr_empty"))
        read_text(self.plain().toImage(), done, lambda _m: self._show_chip(t("ocr_failed")))

    def save(self):
        path = os.path.join(snapshot_dir(), "delta " + datetime.now().strftime("%Y-%m-%d %H.%M.%S") + ".png")
        self.plain().save(path, "PNG")
        self.mgr.saved.emit(path)

    def send(self):
        self.mgr.to_delta.emit(self.pix)

    def closeEvent(self, e):
        if self in self.mgr.pins:
            self.mgr.pins.remove(self)
        self.mgr.changed.emit()
        super().closeEvent(e)


class PinManager(QObject):
    to_delta = pyqtSignal(object)
    saved = pyqtSignal(str)
    changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.pins = []

    def add(self, pixmap, pos):
        w = PinWindow(self, pixmap, pos)
        self.pins.append(w)
        w.show()
        w.raise_()
        w.activateWindow()
        self.changed.emit()
        return w

    def close_all(self):
        for w in list(self.pins):
            w.close()
