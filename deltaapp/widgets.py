"""Ortak küçük bileşenler (gamma ile aynı görünüm)."""
import ctypes

from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, pyqtProperty, QRectF, QPointF, QTimer
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QToolButton, QWidget, QDialog, QLabel

from .theme import theme, current_name


class IconButton(QToolButton):
    def __init__(self, name, tip="", size=40, icon_size=22, role="text", parent=None, checkable=False,
                 obj="IconBtn"):
        super().__init__(parent)
        self.setObjectName(obj)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCheckable(checkable)
        self.setToolTip(tip)
        self._icon_size = icon_size
        self._role = role
        theme.icon(self, name, role, icon_size)

    def set_icon_name(self, name, role=None):
        theme.icon(self, name, role or self._role, self._icon_size)


class ToggleSwitch(QWidget):
    """YouTube tarzı açma/kapama anahtarı."""
    toggled = pyqtSignal(bool)

    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self.setFixedSize(36, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._checked = bool(checked)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(140)

    def _get_pos(self):
        return self._pos

    def _set_pos(self, v):
        self._pos = v
        self.update()

    knob = pyqtProperty(float, _get_pos, _set_pos)

    def isChecked(self):
        return self._checked

    def setChecked(self, c, emit=True):
        c = bool(c)
        if c == self._checked:
            return
        self._checked = c
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if c else 0.0)
        self._anim.start()
        if emit:
            self.toggled.emit(c)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        track_h = 14
        ty = (h - track_h) / 2
        dark = current_name() == "dark"
        off_track = QColor("#3d3d3d") if dark else QColor("#cfcfcf")
        off_knob = QColor("#9e9e9e") if dark else QColor("#ffffff")
        on_track = QColor("#e8e8e8" if dark else "#3a3a3a")
        on_knob = QColor("#1a1a1a") if on_track.lightness() > 185 else QColor("#ffffff")
        t_ = max(0.0, min(1.0, self._pos))

        def mix(a, b):
            return QColor(int(a.red() + (b.red() - a.red()) * t_), int(a.green() + (b.green() - a.green()) * t_),
                          int(a.blue() + (b.blue() - a.blue()) * t_))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mix(off_track, on_track))
        p.drawRoundedRect(QRectF(2, ty, w - 4, track_h), track_h / 2, track_h / 2)
        r = 9
        cx = r + self._pos * (w - 2 * r)
        p.setBrush(QColor(0, 0, 0, 70))
        p.drawEllipse(QPointF(cx, h / 2 + 1), r, r)
        p.setBrush(mix(off_knob, on_knob))
        p.drawEllipse(QPointF(cx, h / 2), r, r)


class Divider(QWidget):
    def __init__(self, parent=None, vertical=False):
        super().__init__(parent)
        self.setObjectName("Divider")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        if vertical:
            self.setFixedWidth(1)
        else:
            self.setFixedHeight(1)


class Toast(QLabel):
    """Ortada beliren kısa bilgi (YouTube'daki ses göstergesi gibi)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_text(self, text, ms=1400, top=18):
        self.setText(text)
        self.adjustSize()
        par = self.parentWidget()
        self.move((par.width() - self.width()) // 2, top)
        self.show()
        self.raise_()
        self._timer.start(ms)


def set_dark_titlebar(widget, dark: bool):
    """Windows 10/11 standart pencere başlığını koyu/açık yapar."""
    try:
        hwnd = int(widget.winId())
        val = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), ctypes.sizeof(val)) == 0:
                break
    except Exception:
        pass


class ThemedDialog(QDialog):
    def __init__(self, parent=None, title=""):
        super().__init__(parent)
        self.setObjectName("ThemedDialog")
        self.setWindowTitle(title)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        theme.bind(self, lambda d: set_dark_titlebar(d, current_name() == "dark"))

    def showEvent(self, e):
        set_dark_titlebar(self, current_name() == "dark")
        super().showEvent(e)
