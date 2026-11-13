"""Ekran videosu: seçilen alan ffmpeg (gdigrab) ile MP4'e kaydedilir, isteğe bağlı mikrofon sesiyle.

Kayıt sırasında alanın çevresinde kırmızı çerçeve ve küçük bir kontrol çubuğu (süre · durdur · vazgeç) durur.
İkisi de WDA_EXCLUDEFROMCAPTURE ile videoya girmez. "Ekrana çiz" katmanı ise bilerek videoya girer:
kayıt sırasında ekrana çizip anlatılabilir.
"""
import ctypes
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime

from PyQt6.QtCore import Qt, QObject, pyqtSignal, QProcess, QTimer, QRect, QRectF, QPoint, QSize
from PyQt6.QtGui import QPainter, QColor, QPen, QPainterPath
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel

from . import icons
from .config import prefs, video_dir
from .i18n import t

WDA_EXCLUDEFROMCAPTURE = 0x11
CREATE_NO_WINDOW = 0x08000000


def find_ffmpeg():
    """Donmuş exe'de yanındaki ffmpeg, kaynaktan çalışırken imageio-ffmpeg ya da PATH."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        for name in ("ffmpeg.exe",):
            p = os.path.join(base, name)
            if os.path.exists(p):
                return p
    try:
        import imageio_ffmpeg
        p = imageio_ffmpeg.get_ffmpeg_exe()
        if p and os.path.exists(p):
            return p
    except Exception:
        pass
    return shutil.which("ffmpeg")


_mics = None


def list_mics(refresh=False):
    """DirectShow ses giriş aygıtlarının adları."""
    global _mics
    if _mics is not None and not refresh:
        return _mics
    ff = find_ffmpeg()
    out = []
    if ff:
        try:
            r = subprocess.run([ff, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                               capture_output=True, timeout=8, creationflags=CREATE_NO_WINDOW)
            txt = (r.stderr or b"").decode("utf-8", errors="ignore")
            out = re.findall(r'"([^"]+)"\s*\(audio\)', txt)
        except Exception:
            out = []
    _mics = out
    return out


def exclude_from_capture(widget):
    try:
        ctypes.windll.user32.SetWindowDisplayAffinity(int(widget.winId()), WDA_EXCLUDEFROMCAPTURE)
    except Exception:
        pass


def _fmt(sec):
    sec = int(sec)
    return f"{sec // 3600}:{sec // 60 % 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60:02d}:{sec % 60:02d}"


class RecordFrame(QWidget):
    """Kaydedilen alanın dışında kırmızı çerçeve; fareye geçirgen, videoya girmez."""
    M = 4

    def __init__(self, rect: QRect):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setGeometry(rect.adjusted(-self.M, -self.M, self.M, self.M))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(255, 48, 48, 230), 2.5, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawRect(QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5))


BAR_QSS = """
QPushButton { background: transparent; color: #f1f1f1; border: none; border-radius: 15px;
              padding: 0px 12px; min-height: 30px; max-height: 30px; font-size: 13px; font-weight: 500; }
QPushButton:hover { background: rgba(255,255,255,0.12); }
QPushButton#RecStop { background: #f1f1f1; color: #0f0f0f; font-weight: 600; }
QPushButton#RecStop:hover { background: #d9d9d9; }
QLabel { color: #f1f1f1; font-size: 13px; font-weight: 600; }
QLabel#RecMic { color: #aaaaaa; font-weight: 500; font-size: 12px; }
"""


class RecordBar(QWidget):
    """Kayıt sırasında: ● süre · Durdur · Vazgeç. Sürüklenerek taşınabilir."""

    def __init__(self, rec):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.Tool)
        self.rec = rec
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet(BAR_QSS)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 6, 6, 6)
        lay.setSpacing(6)
        # yanıp sönme: nokta hiç gizlenmez, yalnız rengi söner — yoksa süre ve düğmeler kayar
        self.dot = QLabel("●")
        self.set_blink(True)
        self.dot.setFixedSize(self.dot.sizeHint() + QSize(2, 0))
        self.dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.dot)
        self.time = QLabel("00:00")
        self.time.setMinimumWidth(44)
        lay.addWidget(self.time)
        self.mic = QLabel("")
        self.mic.setObjectName("RecMic")
        lay.addWidget(self.mic)
        b = QPushButton(icons.icon("stop", "#0f0f0f", 18), " " + t("rec_stop"))
        b.setObjectName("RecStop")
        b.setToolTip(t("rec_stop_tip"))
        b.clicked.connect(rec.stop)
        lay.addWidget(b)
        c = QPushButton(icons.icon("close", "#f1f1f1", 18), "")
        c.setToolTip(t("rec_discard"))
        c.clicked.connect(rec.discard)
        lay.addWidget(c)
        for w in self.findChildren(QPushButton):
            w.setCursor(Qt.CursorShape.PointingHandCursor)
            w.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._drag = None

    def set_blink(self, on):
        c = "#ff3030" if on else "rgba(255,48,48,0.25)"
        self.dot.setStyleSheet(f"color: {c}; font-size: 14px;")

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path.addRoundedRect(r, r.height() / 2, r.height() / 2)
        p.fillPath(path, QColor(28, 28, 28, 240))
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.drawPath(path)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None


class Recorder(QObject):
    started = pyqtSignal()
    saved = pyqtSignal(str)
    failed = pyqtSignal(str)
    stopped = pyqtSignal()   # her durumda (kaydedildi / vazgeçildi / hata)

    def __init__(self):
        super().__init__()
        self.proc = None
        self.path = None
        self.frame = None
        self.bar = None
        self._t0 = 0.0
        self._discard = False
        self._err = b""
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._tick)

    def active(self):
        return self.proc is not None

    def start(self, screen, sel: QRect, dpr: float):
        """sel: ekranın içindeki mantıksal seçim; ffmpeg fiziksel piksel ister."""
        if self.proc is not None:
            return
        ff = find_ffmpeg()
        if not ff:
            self.failed.emit(t("rec_no_ffmpeg"))
            self.stopped.emit()
            return
        geo = screen.geometry()
        # Qt (Windows) ekranın sol üst köşesini yerel pikselde tutar, boyutu ölçekler
        x = geo.x() + round(sel.x() * dpr)
        y = geo.y() + round(sel.y() * dpr)
        w = round(sel.width() * dpr) // 2 * 2   # H.264 çift boyut ister
        h = round(sel.height() * dpr) // 2 * 2
        if w < 16 or h < 16:
            self.failed.emit(t("rec_too_small"))
            self.stopped.emit()
            return
        fps = int(prefs.get("record_fps", 30) or 30)
        name = "delta " + datetime.now().strftime("%Y-%m-%d %H.%M.%S") + ".mp4"
        self.path = os.path.join(video_dir(), name)
        args = ["-hide_banner", "-loglevel", "error", "-y",
                "-thread_queue_size", "512", "-f", "gdigrab", "-framerate", str(fps), "-draw_mouse", "1",
                "-offset_x", str(x), "-offset_y", str(y), "-video_size", f"{w}x{h}", "-i", "desktop"]
        mic = prefs.get("record_mic", "") or ""
        if mic and mic in list_mics():
            args += ["-thread_queue_size", "512", "-f", "dshow", "-i", f"audio={mic}"]
        else:
            mic = ""
        args += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-pix_fmt", "yuv420p"]
        if mic:
            args += ["-c:a", "aac", "-b:a", "128k"]
        args += ["-movflags", "+faststart", self.path]
        self._err = b""
        self._discard = False
        p = QProcess(self)
        p.setProgram(ff)
        p.setArguments(args)
        p.readyReadStandardError.connect(lambda: self._read_err(p))
        p.finished.connect(self._finished)
        p.errorOccurred.connect(self._error)
        self.proc = p
        p.start()
        if not p.waitForStarted(3000):
            return
        self._t0 = time.monotonic()
        lrect = QRect(geo.x() + sel.x(), geo.y() + sel.y(), sel.width(), sel.height())
        self.frame = RecordFrame(lrect)
        self.frame.show()
        exclude_from_capture(self.frame)
        self.bar = RecordBar(self)
        self.bar.mic.setText("🎙 " + t("rec_mic_on") if mic else "")
        self.bar.mic.setVisible(bool(mic))
        self.bar.adjustSize()
        bx = lrect.center().x() - self.bar.width() // 2
        by = lrect.bottom() + 12
        if by + self.bar.height() > geo.y() + geo.height() - 8:   # alttan taşarsa ekranın üstüne
            by = geo.y() + 12 if lrect.top() - geo.y() > self.bar.height() + 24 else lrect.top() + 12
        bx = max(geo.x() + 8, min(bx, geo.x() + geo.width() - self.bar.width() - 8))
        self.bar.move(QPoint(bx, by))
        self.bar.show()
        exclude_from_capture(self.bar)
        self._timer.start()
        self.started.emit()

    def _read_err(self, p):
        self._err += bytes(p.readAllStandardError())

    def _tick(self):
        if self.bar is not None:
            el = time.monotonic() - self._t0
            self.bar.time.setText(_fmt(el))
            self.bar.set_blink(int(el * 2) % 2 == 0)

    def stop(self):
        """ffmpeg'e 'q' gönderilir: dosyayı düzgün kapatıp çıkar."""
        if self.proc is None:
            return
        self._hide_ui()
        self.proc.write(b"q")
        self.proc.closeWriteChannel()
        QTimer.singleShot(8000, self._force_kill)

    def discard(self):
        self._discard = True
        self.stop()

    def _force_kill(self):
        if self.proc is not None and self.proc.state() != QProcess.ProcessState.NotRunning:
            self.proc.kill()

    def _hide_ui(self):
        self._timer.stop()
        for w in (self.frame, self.bar):
            if w is not None:
                w.close()
                w.deleteLater()
        self.frame = self.bar = None

    def _error(self, err):
        if err == QProcess.ProcessError.FailedToStart:
            self._hide_ui()
            self.proc = None
            self.failed.emit(t("rec_no_ffmpeg"))
            self.stopped.emit()

    def _finished(self, code, _status):
        self._hide_ui()
        self.proc = None
        path = self.path
        ok = path and os.path.exists(path) and os.path.getsize(path) > 1000
        if self._discard:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
        elif ok:
            self.saved.emit(path)
        else:
            msg = self._err.decode("utf-8", errors="ignore").strip().splitlines()
            self.failed.emit(msg[-1] if msg else t("rec_failed"))
        self.stopped.emit()
