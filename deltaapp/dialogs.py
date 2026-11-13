"""Seçenekler ve kısayol / fare kontrolleri yardımı."""
import os
import sys

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton, QScrollArea,
                             QWidget, QFileDialog, QGridLayout)

from .config import prefs, snapshot_dir, video_dir, BASE_DIR
from .i18n import t
from .theme import theme, VARIANTS, variant_label, current_variant
from .widgets import ThemedDialog, ToggleSwitch, Divider


class HotkeyEdit(QLineEdit):
    """Tıklayıp tuş kombinasyonuna basınca kaydeder. Backspace/Delete: kısayolu kapat."""
    changed = pyqtSignal(str)

    def __init__(self, value, mgr, parent=None):
        super().__init__(parent)
        self.setObjectName("HotkeyEdit")
        self.setReadOnly(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedWidth(170)
        self.mgr = mgr
        self._value = value or ""
        self._show()

    def _show(self):
        self.setText(self._value or t("hotkey_off"))

    def focusInEvent(self, e):
        super().focusInEvent(e)
        if self.mgr:
            self.mgr.suspend()
        self.setText(t("hotkey_press"))

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        if self.mgr:
            self.mgr.resume()
        self._show()

    def keyPressEvent(self, e):
        k = e.key()
        K = Qt.Key
        if k in (K.Key_Control, K.Key_Shift, K.Key_Alt, K.Key_Meta, K.Key_AltGr):
            return
        if k == K.Key_Escape:
            self.clearFocus()
            return
        if k in (K.Key_Backspace, K.Key_Delete) and not e.modifiers():
            self._value = ""
            self.changed.emit("")
            self.clearFocus()
            return
        m = e.modifiers()
        parts = []
        if m & Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if m & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        if m & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")
        if m & Qt.KeyboardModifier.MetaModifier:
            parts.append("Win")
        name = None
        if K.Key_A <= k <= K.Key_Z or K.Key_0 <= k <= K.Key_9:
            name = chr(k)
        elif K.Key_F1 <= k <= K.Key_F24:
            name = f"F{k - K.Key_F1 + 1}"
        elif k == K.Key_Print:
            name = "Print"
        elif k == K.Key_Pause:
            name = "Pause"
        elif k == K.Key_Insert:
            name = "Insert"
        elif k == K.Key_Space:
            name = "Space"
        if name is None:
            return
        self._value = "+".join(parts + [name])
        self.changed.emit(self._value)
        self.clearFocus()


def _row(label, widget, sub=None):
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 6, 0, 6)
    lay.setSpacing(16)
    box = QVBoxLayout()
    box.setSpacing(2)
    lbl = QLabel(label)
    lbl.setWordWrap(True)
    box.addWidget(lbl)
    if sub:
        s = QLabel(sub)
        s.setObjectName("Secondary")
        s.setWordWrap(True)
        box.addWidget(s)
    lay.addLayout(box, 1)
    if isinstance(widget, QWidget):
        lay.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
    else:
        lay.addLayout(widget)
    return w


def _combo(items, current):
    c = QComboBox()
    c.setMinimumWidth(170)
    for key, label in items:
        c.addItem(label, key)
    i = c.findData(current)
    c.setCurrentIndex(max(0, i))
    return c


def autostart_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --tray'
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pyw):
        exe = pyw
    return f'"{exe}" "{os.path.join(BASE_DIR, "main.py")}" --tray'


def set_autostart(on):
    import winreg
    key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, "delta", 0, winreg.REG_SZ, autostart_command())
            else:
                try:
                    winreg.DeleteValue(k, "delta")
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


class PrefsDialog(ThemedDialog):
    def __init__(self, parent, hotkeys, on_hotkeys_changed=None):
        super().__init__(parent, t("preferences"))
        self.hotkeys = hotkeys
        self.on_hotkeys_changed = on_hotkeys_changed
        self.resize(620, 680)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(28, 20, 28, 20)
        lay.setSpacing(2)
        scroll.setWidget(page)
        outer.addWidget(scroll, 1)

        def section(title):
            if lay.count():
                lay.addSpacing(10)
                lay.addWidget(Divider())
                lay.addSpacing(6)
            l = QLabel(title)
            l.setObjectName("SubTitle")
            lay.addWidget(l)

        # --- Görünüm
        section(t("appearance"))
        self.c_theme = _combo([(v, variant_label(v)) for v in VARIANTS], current_variant())
        self.c_theme.currentIndexChanged.connect(lambda: theme.apply(self.c_theme.currentData()))
        lay.addWidget(_row(t("theme"), self.c_theme))
        self.c_grid = _combo([("dots", t("grid_dots")), ("lines", t("grid_lines")), ("none", t("grid_none"))],
                             prefs.get("grid", "dots"))
        self.c_grid.currentIndexChanged.connect(self._grid)
        lay.addWidget(_row(t("background"), self.c_grid, t("background_sub")))
        self.c_lang = _combo([("tr", "Türkçe"), ("en", "English")], prefs.get("language", "tr"))
        self.c_lang.currentIndexChanged.connect(lambda: prefs.set("language", self.c_lang.currentData()))
        lay.addWidget(_row(t("language"), self.c_lang, t("language_sub")))

        # --- Kısayollar
        section(t("global_hotkeys"))
        sub = QLabel(t("global_hotkeys_sub"))
        sub.setObjectName("Secondary")
        sub.setWordWrap(True)
        lay.addWidget(sub)
        self.hk_status = {}
        for name, label in (("capture", t("hk_capture")), ("record", t("hk_record")),
                            ("annotate", t("hk_annotate")), ("note", t("hk_note"))):
            ed = HotkeyEdit(prefs.get("hotkey_" + name, ""), hotkeys)
            st = QLabel()
            st.setFixedWidth(110)
            st.setObjectName("Secondary")
            self.hk_status[name] = st
            ed.changed.connect(lambda v, n=name: self._hotkey(n, v))
            box = QHBoxLayout()
            box.setSpacing(10)
            box.addWidget(ed)
            box.addWidget(st)
            lay.addWidget(_row(label, box))
            self._show_status(name)

        # --- Davranış
        section(t("behavior"))
        sw = ToggleSwitch(prefs.get("close_to_tray", True))
        sw.toggled.connect(lambda v: prefs.set("close_to_tray", v))
        lay.addWidget(_row(t("close_to_tray"), sw, t("close_to_tray_sub")))
        sw = ToggleSwitch(prefs.get("autostart", False))
        sw.toggled.connect(self._autostart)
        lay.addWidget(_row(t("autostart"), sw, t("autostart_sub")))
        sw = ToggleSwitch(prefs.get("capture_autocopy", True))
        sw.toggled.connect(lambda v: prefs.set("capture_autocopy", v))
        lay.addWidget(_row(t("cap_autocopy"), sw, t("cap_autocopy_sub")))
        c = _combo([("new", t("target_new")), ("current", t("target_current"))], prefs.get("capture_target", "new"))
        c.currentIndexChanged.connect(lambda: prefs.set("capture_target", c.currentData()))
        lay.addWidget(_row(t("cap_target"), c))
        c2 = _combo([("zoom", t("wheel_zoom")), ("scroll", t("wheel_scroll"))], prefs.get("wheel", "zoom"))
        c2.currentIndexChanged.connect(lambda: prefs.set("wheel", c2.currentData()))
        lay.addWidget(_row(t("wheel"), c2, t("wheel_sub")))

        # --- Ekran videosu
        section(t("recording"))
        from .recorder import list_mics
        mics = list_mics()
        cur = prefs.get("record_mic", "") or ""
        items = [("", t("rec_silent"))] + [(m, m) for m in mics]
        if cur and cur not in mics:
            items.append((cur, cur))
        c3 = _combo(items, cur)
        c3.setMaximumWidth(260)
        c3.currentIndexChanged.connect(lambda: prefs.set("record_mic", c3.currentData()))
        lay.addWidget(_row(t("rec_mic"), c3, t("rec_mic_sub")))
        self.vdir_lbl = QLabel(video_dir())
        self.vdir_lbl.setObjectName("Secondary")
        self.vdir_lbl.setWordWrap(True)
        vx = QHBoxLayout()
        v1 = QPushButton(t("change"))
        v1.setObjectName("Pill")
        v1.clicked.connect(self._pick_vdir)
        v2 = QPushButton(t("open_folder"))
        v2.setObjectName("Pill")
        v2.clicked.connect(lambda: os.startfile(video_dir()))
        vx.addWidget(v1)
        vx.addWidget(v2)
        lay.addWidget(_row(t("video_folder_sub"), vx))
        lay.addWidget(self.vdir_lbl)

        # --- Kayıt klasörü
        section(t("save_folder"))
        self.dir_lbl = QLabel(snapshot_dir())
        self.dir_lbl.setObjectName("Secondary")
        self.dir_lbl.setWordWrap(True)
        bx = QHBoxLayout()
        b1 = QPushButton(t("change"))
        b1.setObjectName("Pill")
        b1.clicked.connect(self._pick_dir)
        b2 = QPushButton(t("open_folder"))
        b2.setObjectName("Pill")
        b2.clicked.connect(lambda: os.startfile(snapshot_dir()))
        bx.addWidget(b1)
        bx.addWidget(b2)
        lay.addWidget(_row(t("save_folder_sub"), bx))
        lay.addWidget(self.dir_lbl)
        lay.addStretch(1)

        foot = QHBoxLayout()
        foot.setContentsMargins(20, 10, 20, 16)
        bh = QPushButton(t("controls"))
        bh.setObjectName("Flat")
        bh.clicked.connect(lambda: HelpDialog(self).exec())
        foot.addWidget(bh)
        foot.addStretch(1)
        ok = QPushButton(t("done"))
        ok.setObjectName("Primary")
        ok.clicked.connect(self.accept)
        foot.addWidget(ok)
        outer.addLayout(foot)

    def _grid(self):
        prefs.set("grid", self.c_grid.currentData())
        theme.apply()

    def _autostart(self, v):
        if set_autostart(v):
            prefs.set("autostart", v)

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, t("save_folder"), snapshot_dir())
        if d:
            prefs.set("snapshot_dir", d)
            self.dir_lbl.setText(d)

    def _pick_vdir(self):
        d = QFileDialog.getExistingDirectory(self, t("recording"), video_dir())
        if d:
            prefs.set("video_dir", d)
            self.vdir_lbl.setText(d)

    def _hotkey(self, name, value):
        prefs.set("hotkey_" + name, value)
        if self.hotkeys:
            self.hotkeys.set(name, value)
        self._show_status(name)
        if self.on_hotkeys_changed:
            self.on_hotkeys_changed()

    def _show_status(self, name):
        st = self.hotkeys.status(name) if self.hotkeys else None
        lbl = self.hk_status[name]
        if st is True:
            lbl.setText("✓ " + t("hk_ok"))
        elif st is False:
            lbl.setText("⚠ " + t("hk_busy"))
        else:
            lbl.setText(t("hotkey_off"))


class HelpDialog(ThemedDialog):
    def __init__(self, parent=None):
        super().__init__(parent, t("controls"))
        self.resize(760, 640)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        page = QWidget()
        grid = QGridLayout(page)
        grid.setContentsMargins(28, 20, 28, 20)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(5)
        scroll.setWidget(page)
        outer.addWidget(scroll, 1)
        row = 0
        for title, rows in ((t("help_mouse"), MOUSE), (t("help_keys"), KEYS), (t("help_global"), None)):
            h = QLabel(title)
            h.setObjectName("SubTitle")
            grid.addWidget(h, row, 0, 1, 2)
            row += 1
            if rows is None:
                rows = [(prefs.get("hotkey_capture") or "—", t("hk_capture")),
                        (prefs.get("hotkey_annotate") or "—", t("hk_annotate")),
                        (prefs.get("hotkey_note") or "—", t("hk_note")),
                        (prefs.get("hotkey_record") or "—", t("hk_record")),
                        (t("pin"), t("h_pin"))]
            for k, d in rows:
                kl = QLabel(t(k) if k.startswith("m_") else k)
                kl.setStyleSheet("font-weight: 600;")
                dl = QLabel(t(d) if d.startswith("h_") else d)
                dl.setObjectName("Secondary")
                dl.setWordWrap(True)
                grid.addWidget(kl, row, 0, Qt.AlignmentFlag.AlignTop)
                grid.addWidget(dl, row, 1)
                row += 1
            grid.addWidget(QLabel(""), row, 0)
            row += 1
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(row, 1)
        foot = QHBoxLayout()
        foot.setContentsMargins(20, 10, 20, 16)
        foot.addStretch(1)
        ok = QPushButton(t("close"))
        ok.setObjectName("Primary")
        ok.clicked.connect(self.accept)
        foot.addWidget(ok)
        outer.addLayout(foot)


MOUSE = [
    ("m_left", "h_left"), ("m_right_hold", "h_right_hold"), ("m_right_click", "h_right_click"),
    ("m_middle", "h_middle"), ("m_wheel", "h_wheel"), ("m_ctrl_wheel", "h_ctrl_wheel"),
    ("m_alt_wheel", "h_alt_wheel"), ("m_shift_left", "h_shift_left"), ("m_ctrl_left", "h_ctrl_left"),
    ("m_double", "h_double"), ("m_middle_double", "h_middle_double"), ("m_side", "h_side"),
    ("m_drop", "h_drop"),
]
KEYS = [
    ("P / B", "h_k_pen"), ("H", "h_k_hl"), ("K", "h_k_laser"), ("E", "h_k_eraser"), ("V", "h_k_select"),
    ("L · A · R · O", "h_k_shapes"), ("T", "h_k_text"), ("Enter", "h_k_enter"), ("I", "h_k_image"),
    ("1 – 7", "h_k_colors"), ("[  ]   ,  .", "h_k_size"), ("Ctrl+Z / Ctrl+Y", "h_k_undo"),
    ("Ctrl+C / X / V / D", "h_k_clip"), ("Ctrl+A · Delete", "h_k_sel"), ("F · Ctrl+0", "h_k_fit"),
    ("G", "h_k_grid"), ("Ctrl+N · Ctrl+Tab", "h_k_notes"), ("Ctrl+S · Ctrl+Shift+S", "h_k_save"),
    ("Ctrl+Shift+C", "h_k_copyall"), ("F11 · Ctrl+B", "h_k_view"), ("F1", "h_k_help"),
]
