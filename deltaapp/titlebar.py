"""Üst çubuk (gamma ile aynı düzen): solda logo + delta + •••, ortada not başlığı, sağda işlemler ve pencere düğmeleri."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QLineEdit, QToolButton

from .i18n import t
from .theme import theme, tinted_logo, current_name
from .widgets import IconButton


class NoteTitle(QLineEdit):
    """Not başlığı: yazı kadar geniş, kilitli. Tek tıkla sürükleyince pencere taşınır (yanlışlıkla düzenlenmez);
    çift tık ya da F2 ile adı değiştirilir."""
    MIN_W, MAX_W = 90, 300

    def __init__(self, parent):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.textChanged.connect(self._fit)
        self._fit()

    def _fit(self, *_):
        fm = self.fontMetrics()
        txt = self.text() or self.placeholderText()
        w = fm.horizontalAdvance(txt) + 36
        self.setFixedWidth(max(self.MIN_W, min(self.MAX_W, w)))

    def setPlaceholderText(self, text):
        super().setPlaceholderText(text)
        self._fit()

    def editing(self):
        return not self.isReadOnly()

    def begin_edit(self):
        self.setReadOnly(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.setMaximumWidth(self.MAX_W)
        self.setMinimumWidth(self.MAX_W)   # düzenlerken uzun ad yazılabilsin
        self.setFocus()
        self.selectAll()

    def end_edit(self):
        self.setReadOnly(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.deselect()
        self.setCursorPosition(0)
        self._fit()

    def mousePressEvent(self, e):
        if not self.editing():
            if e.button() == Qt.MouseButton.LeftButton and not self.window().isFullScreen():
                h = self.window().windowHandle()
                if h:
                    h.startSystemMove()
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        if not self.editing() and e.button() == Qt.MouseButton.LeftButton:
            self.begin_edit()
            return
        super().mouseDoubleClickEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape and self.editing():
            self.setText(self._orig if hasattr(self, "_orig") else self.text())
            self.clearFocus()
            return
        super().keyPressEvent(e)

    def focusInEvent(self, e):
        self._orig = self.text()
        super().focusInEvent(e)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        if self.editing():
            self.end_edit()


class TitleBar(QWidget):
    prefs_clicked = pyqtSignal()
    new_note = pyqtSignal()
    capture = pyqtSignal()
    annotate = pyqtSignal()
    record = pyqtSignal()
    theme_clicked = pyqtSignal()
    pin_clicked = pyqtSignal()
    panel_clicked = pyqtSignal()
    title_edited = pyqtSignal(str)
    minimize = pyqtSignal()
    maximize = pyqtSignal()
    close = pyqtSignal()

    HEIGHT = 56

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(self.HEIGHT)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 0, 0)
        lay.setSpacing(4)

        brand = QWidget(self)
        bl = QHBoxLayout(brand)
        bl.setContentsMargins(8, 0, 4, 0)
        bl.setSpacing(5)
        self.logo = QLabel()
        theme.bind(self.logo, lambda l: l.setPixmap(tinted_logo(24, l.devicePixelRatioF())))
        bl.addWidget(self.logo)
        self.wordmark = QLabel("delta")
        self.wordmark.setObjectName("Wordmark")
        bl.addWidget(self.wordmark)
        lay.addWidget(brand)
        self.btn_prefs = IconButton("more_horiz", t("preferences"), 36, 24)
        self.btn_prefs.clicked.connect(self.prefs_clicked.emit)
        box = QHBoxLayout()
        box.setContentsMargins(0, 6, 0, 0)  # "delta" küçük harflerinin görsel ortasıyla hizalı
        box.addWidget(self.btn_prefs)
        lay.addLayout(box)

        lay.addStretch(1)
        self.title = NoteTitle(self)
        self.title.setObjectName("NoteTitle")
        self.title.setFixedHeight(32)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setToolTip(t("rename_tip"))
        self.title.editingFinished.connect(self._title_done)
        self.title.returnPressed.connect(lambda: self.title.clearFocus())
        lay.addWidget(self.title, 0)
        lay.addStretch(1)

        self.btn_new = IconButton("note_add", t("new_note") + " (Ctrl+N)", 40, 22)
        self.btn_new.clicked.connect(self.new_note.emit)
        self.btn_cap = IconButton("capture", t("capture_tip"), 40, 22)
        self.btn_cap.clicked.connect(self.capture.emit)
        self.btn_rec = IconButton("videocam", t("record_tip"), 40, 22)
        self.btn_rec.clicked.connect(self.record.emit)
        self.btn_ann = IconButton("screen_draw", t("annotate_tip"), 40, 22)
        self.btn_ann.clicked.connect(self.annotate.emit)
        self.btn_theme = IconButton("moon", t("theme_tip"), 40, 22)
        self.btn_theme.clicked.connect(self.theme_clicked.emit)
        self.btn_pin = IconButton("pin_outline", t("pin_tip"), 40, 21, checkable=True)
        self.btn_pin.clicked.connect(self.pin_clicked.emit)
        self.btn_panel = IconButton("queue", t("toggle_panel"), 40, 22, checkable=True)
        self.btn_panel.clicked.connect(self.panel_clicked.emit)
        for b in (self.btn_new, self.btn_cap, self.btn_rec, self.btn_ann, self.btn_theme, self.btn_pin, self.btn_panel):
            lay.addWidget(b)
        lay.addSpacing(10)
        self.btn_min = self._win_btn("win_min", "WinBtn", self.minimize)
        self.btn_max = self._win_btn("win_max", "WinBtn", self.maximize)
        self.btn_close = self._win_btn("close", "WinClose", self.close)
        for b in (self.btn_min, self.btn_max, self.btn_close):
            lay.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
        self.update_theme_icon()
        theme.changed.connect(lambda _: self.update_theme_icon())

    def _title_done(self):
        if self.title.editing() or self.title.hasFocus():
            self.title_edited.emit(self.title.text())

    def set_title(self, text, placeholder):
        if not self.title.hasFocus():
            self.title.setText(text)
        self.title.setPlaceholderText(placeholder)

    def set_hotkey_tips(self, cap, ann, rec=""):
        self.btn_cap.setToolTip(t("capture_tip") + (f" ({cap})" if cap else ""))
        self.btn_rec.setToolTip(t("record_tip") + (f" ({rec})" if rec else ""))
        self.btn_ann.setToolTip(t("annotate_tip") + (f" ({ann})" if ann else ""))

    def is_drag_area(self, widget):
        return widget is self or widget is None or widget is self.wordmark or widget is self.logo

    def _win_btn(self, icon_name, obj, sig):
        b = QToolButton(self)
        b.setObjectName(obj)
        b.setFixedSize(46, 34)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        theme.icon(b, icon_name, "text", 16)
        b.clicked.connect(sig.emit)
        return b

    def update_theme_icon(self):
        dark = current_name() == "dark"
        self.btn_theme.set_icon_name("sun" if dark else "moon")
        self.btn_theme.setToolTip(t("light_mode") if dark else t("dark_mode"))

    def set_pinned(self, on):
        self.btn_pin.setChecked(on)
        self.btn_pin.set_icon_name("pin" if on else "pin_outline")
        self.btn_pin.setToolTip(t("unpin_tip") if on else t("pin_tip"))

    def set_maximized(self, on):
        theme.icon(self.btn_max, "win_restore" if on else "win_max", "text", 16)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and not self.window().isFullScreen():
            h = self.window().windowHandle()
            if h:
                h.startSystemMove()
                return
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.maximize.emit()
            return
        super().mouseDoubleClickEvent(e)
