"""Ekran alıntısı: ekran dondurulur, alan sürükleyerek seçilir.
Bırakınca panoya kopyalanır (varsayılan) ve altında küçük bir çubuk çıkar: delta'ya ekle / iğnele / kopyala / kaydet / video.
mode="record" ile aynı seçim ekranı video kaydı alanı seçmek için kullanılır."""
import os
from datetime import datetime

from PyQt6.QtCore import Qt, QObject, pyqtSignal, QRect, QPoint, QPointF, QTimer, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QGuiApplication, QCursor, QPainterPath, QFont
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QApplication, QLabel

from . import icons
from .config import prefs, snapshot_dir
from .i18n import t

BAR_QSS = """
QWidget#CapBar { background: transparent; }
QPushButton { background: transparent; color: #f1f1f1; border: none; border-radius: 15px;
              padding: 0px 12px; min-height: 32px; max-height: 32px; font-size: 13px; font-weight: 500; }
QPushButton:hover { background: rgba(255,255,255,0.12); }
QPushButton#CapMain { background: #f1f1f1; color: #0f0f0f; font-weight: 600; }
QPushButton#CapMain:hover { background: #d9d9d9; }
QLabel { color: #aaaaaa; font-size: 12px; padding: 0 6px; }
"""


class CapBar(QWidget):
    def __init__(self, overlay):
        super().__init__(overlay)
        self.setObjectName("CapBar")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(BAR_QSS)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)
        self.info = QLabel("")
        lay.addWidget(self.info)
        if overlay.ctrl.mode == "record":
            b = QPushButton(icons.icon("videocam", "#0f0f0f", 18), " " + t("rec_start"))
            b.setObjectName("CapMain")
            b.setToolTip(t("rec_start_tip"))
            b.clicked.connect(overlay.record)
            lay.addWidget(b)
        else:
            b = QPushButton(icons.icon("edit", "#0f0f0f", 18), " " + t("cap_to_delta"))
            b.setObjectName("CapMain")
            b.setToolTip(t("cap_to_delta_tip"))
            b.clicked.connect(overlay.send)
            lay.addWidget(b)
            for ic, txt, fn, tip in (("pin", t("pin"), overlay.pin, t("pin_snip_tip")),
                                     ("text", t("ocr"), overlay.ocr, t("ocr_tip")),
                                     ("copy", t("copy"), overlay.copy, ""), ("save", t("save"), overlay.save, ""),
                                     ("videocam", t("rec_video"), overlay.record, t("rec_video_tip"))):
                bb = QPushButton(icons.icon(ic, "#f1f1f1", 18), " " + txt)
                bb.setToolTip(tip)
                bb.clicked.connect(fn)
                lay.addWidget(bb)
        bc = QPushButton(icons.icon("close", "#f1f1f1", 18), "")
        bc.setToolTip(t("close") + " (Esc)")
        bc.clicked.connect(overlay.ctrl.cancel)
        lay.addWidget(bc)
        for w in self.findChildren(QPushButton):
            w.setCursor(Qt.CursorShape.PointingHandCursor)
            w.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path.addRoundedRect(r, r.height() / 2, r.height() / 2)
        p.fillPath(path, QColor(28, 28, 28, 240))
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.drawPath(path)


class CaptureOverlay(QWidget):
    def __init__(self, ctrl, screen, pixmap):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.Tool)
        self.ctrl = ctrl
        self.scr = screen
        self.pix = pixmap
        self.dpr = pixmap.width() / max(1, screen.geometry().width())
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.sel = QRect()
        self._start = None
        self._mouse = QPoint(-1, -1)
        self.bar = CapBar(self)
        self.bar.hide()
        self.setScreen(screen)
        self.setGeometry(screen.geometry())

    # --- çizim
    def paintEvent(self, e):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self.pix)
        dim = QColor(0, 0, 0, 120)
        if self.sel.isNull():
            p.fillRect(self.rect(), dim)
            if self._mouse.x() >= 0:
                pen = QPen(QColor(255, 255, 255, 90), 1, Qt.PenStyle.DashLine)
                p.setPen(pen)
                p.drawLine(0, self._mouse.y(), self.width(), self._mouse.y())
                p.drawLine(self._mouse.x(), 0, self._mouse.x(), self.height())
            self._hint(p)
            return
        s = self.sel
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        inner = QPainterPath()
        inner.addRect(QRectF(s))
        p.fillPath(path.subtracted(inner), dim)
        p.setPen(QPen(QColor("#ffffff"), 1.5))
        p.drawRect(QRectF(s).adjusted(0.5, 0.5, -0.5, -0.5))
        # köşe tutamaçları
        p.setBrush(QColor("#ffffff"))
        p.setPen(Qt.PenStyle.NoPen)
        for c in (s.topLeft(), s.topRight(), s.bottomLeft(), s.bottomRight()):
            p.drawEllipse(QPointF(c), 3.5, 3.5)
        txt = f"{round(s.width() * self.dpr)} × {round(s.height() * self.dpr)}"
        f = QFont("Segoe UI Variable Text")
        f.setPixelSize(12)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        tw = p.fontMetrics().horizontalAdvance(txt) + 16
        y = s.top() - 28 if s.top() > 32 else s.top() + 6
        r = QRectF(s.left(), y, tw, 22)
        p.setBrush(QColor(28, 28, 28, 230))
        p.drawRoundedRect(r, 6, 6)
        p.setPen(QColor("#ffffff"))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, txt)

    def _hint(self, p):
        under = self.rect().contains(self.mapFromGlobal(QCursor.pos()))
        if not under:
            return
        txt = t("rec_hint") if self.ctrl.mode == "record" else t("cap_hint")
        f = QFont("Segoe UI Variable Text")
        f.setPixelSize(14)
        f.setWeight(QFont.Weight.Medium)
        p.setFont(f)
        tw = p.fontMetrics().horizontalAdvance(txt) + 32
        r = QRectF((self.width() - tw) / 2, 28, tw, 38)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(28, 28, 28, 235))
        p.drawRoundedRect(r, 19, 19)
        p.setPen(QColor("#f1f1f1"))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, txt)

    # --- fare
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.ctrl.clear_others(self)
            self._start = e.position().toPoint()
            self.sel = QRect(self._start, self._start)
            self.bar.hide()
            self.update()
        elif e.button() == Qt.MouseButton.RightButton:
            if not self.sel.isNull():
                self.sel = QRect()
                self.bar.hide()
                self.update()
            else:
                self.ctrl.cancel()

    def mouseMoveEvent(self, e):
        self._mouse = e.position().toPoint()
        if self._start is not None:
            a, b = self._start, self._mouse
            self.sel = QRect(min(a.x(), b.x()), min(a.y(), b.y()), abs(b.x() - a.x()),
                             abs(b.y() - a.y())).intersected(self.rect())
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or self._start is None:
            return
        self._start = None
        if self.sel.width() < 5 or self.sel.height() < 5:
            self.sel = QRect(self.rect())  # tek tık: tüm ekran
        self.update()
        self._selected()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and not self.sel.isNull() and self.sel.contains(
                e.position().toPoint()):
            self.record() if self.ctrl.mode == "record" else self.send()

    def keyPressEvent(self, e):
        k = e.key()
        ctrl = e.modifiers() & Qt.KeyboardModifier.ControlModifier
        if k == Qt.Key.Key_Escape:
            self.ctrl.cancel()
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.sel.isNull():
                self.sel = QRect(self.rect())
            self.record() if self.ctrl.mode == "record" else self.send()
        elif ctrl and e.modifiers() & Qt.KeyboardModifier.ShiftModifier and k == Qt.Key.Key_C                 and not self.sel.isNull() and self.ctrl.mode != "record":
            self.ocr()
        elif ctrl and k == Qt.Key.Key_C and not self.sel.isNull():
            self.copy()
        elif ctrl and k == Qt.Key.Key_S and not self.sel.isNull():
            self.save()
        elif ((ctrl and k == Qt.Key.Key_T) or k == Qt.Key.Key_F3) and not self.sel.isNull()                 and self.ctrl.mode != "record":
            self.pin()

    # --- sonuç
    def cropped(self):
        s = self.sel
        r = QRect(round(s.x() * self.dpr), round(s.y() * self.dpr), round(s.width() * self.dpr),
                  round(s.height() * self.dpr))
        pm = self.pix.copy(r)
        pm.setDevicePixelRatio(self.dpr)
        return pm

    def _selected(self):
        if self.ctrl.mode == "record":
            mic = prefs.get("record_mic", "") or ""
            self.bar.info.setText("🎙 " + mic[:28] if mic else t("rec_silent"))
            self.bar.info.setToolTip(t("rec_mic_tip"))
        else:
            auto = bool(prefs.get("capture_autocopy", True))
            if auto:
                QApplication.clipboard().setPixmap(self._plain(self.cropped()))
            self.bar.info.setText("✓ " + t("copied") if auto else "")
            self.bar.info.setVisible(auto)
        self.bar.adjustSize()
        bw, bh = self.bar.width(), self.bar.height()
        s = self.sel
        x = min(max(8, s.right() - bw), self.width() - bw - 8)
        y = s.bottom() + 10
        if y + bh > self.height() - 8:
            y = s.top() - bh - 10
            if y < 8:
                y = s.bottom() - bh - 10
        self.bar.move(int(x), int(y))
        self.bar.show()
        self.bar.raise_()

    @staticmethod
    def _plain(pm):
        q = pm.copy()
        q.setDevicePixelRatio(1.0)
        return q

    def send(self):
        if self.sel.isNull():
            return
        pm = self.cropped()
        self.ctrl.finish("send", pm)

    def record(self):
        if self.sel.isNull():
            return
        self.ctrl.finish("record", (self.scr, QRect(self.sel), self.dpr))

    def pin(self):
        if self.sel.isNull():
            return
        self.ctrl.finish("pin", (self.cropped(), self.mapToGlobal(self.sel.topLeft())))

    def ocr(self):
        if self.sel.isNull():
            return
        self.ctrl.finish("ocr", self._plain(self.cropped()))

    def copy(self):
        QApplication.clipboard().setPixmap(self._plain(self.cropped()))
        self.ctrl.finish("copy", None)

    def save(self):
        pm = self._plain(self.cropped())
        path = os.path.join(snapshot_dir(), "delta " + datetime.now().strftime("%Y-%m-%d %H.%M.%S") + ".png")
        pm.save(path, "PNG")
        self.ctrl.finish("save", path)


class CaptureController(QObject):
    to_delta = pyqtSignal(object)      # QPixmap (devicePixelRatio ayarlı)
    saved = pyqtSignal(str)
    copied = pyqtSignal()
    record = pyqtSignal(object)        # (ekran, mantıksal seçim, dpr)
    pinned = pyqtSignal(object)        # (QPixmap, genel konum)
    ocr_req = pyqtSignal(object)       # QPixmap: yazısı okunacak
    finished = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.overlays = []
        self.mode = "snip"   # snip | record

    def active(self):
        return bool(self.overlays)

    def start(self, delay=0, mode="snip"):
        if self.overlays:
            return
        self.mode = mode
        QTimer.singleShot(delay, self._grab)

    def _grab(self):
        if self.overlays:
            return
        under = QGuiApplication.screenAt(QCursor.pos())
        for scr in QGuiApplication.screens():
            pm = scr.grabWindow(0)
            if pm.isNull():
                continue
            ov = CaptureOverlay(self, scr, pm)
            self.overlays.append(ov)
            ov.show()
            ov.raise_()
        for ov in self.overlays:
            if ov.scr is under:
                ov.activateWindow()
                ov.setFocus()
        if self.overlays and under is None:
            self.overlays[0].activateWindow()

    def clear_others(self, keep):
        for ov in self.overlays:
            if ov is not keep and not ov.sel.isNull():
                ov.sel = QRect()
                ov.bar.hide()
                ov.update()

    def _close_all(self):
        ovs, self.overlays = self.overlays, []
        for ov in ovs:
            ov.close()

    def cancel(self):
        self._close_all()
        self.finished.emit()

    def finish(self, what, data):
        self._close_all()
        if what == "send":
            self.to_delta.emit(data)
        elif what == "save":
            self.saved.emit(data)
        elif what == "copy":
            self.copied.emit()
        elif what == "record":
            self.record.emit(data)
        elif what == "pin":
            self.pinned.emit(data)
        elif what == "ocr":
            self.ocr_req.emit(data)
        self.finished.emit()
