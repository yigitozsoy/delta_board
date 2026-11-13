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


class KeyButton(QPushButton):
    """Tahta kısayolu: tıkla, sonra bir tuşa bas. Esc vazgeçer, Backspace / Delete tuşu kaldırır."""
    changed = pyqtSignal(str)

    def __init__(self, value):
        super().__init__()
        self.value = value
        self.waiting = False
        self.setObjectName("Pill")
        self.setMinimumWidth(110)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._start)
        self._show()

    def _show(self):
        self.setText(t("key_press") if self.waiting else (self.value or "—"))

    def set_value(self, v):
        self.value = v
        self.waiting = False
        self._show()

    def _start(self):
        self.waiting = True
        self._show()
        self.setFocus()

    def focusOutEvent(self, e):
        if self.waiting:
            self.waiting = False
            self._show()
        super().focusOutEvent(e)

    def keyPressEvent(self, e):
        if not self.waiting:
            return super().keyPressEvent(e)
        from .tools import key_name
        k = e.key()
        if k == Qt.Key.Key_Escape:
            self.waiting = False
            self._show()
            return
        if k in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self.set_value("")
            self.changed.emit("")
            return
        if e.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier |
                            Qt.KeyboardModifier.ShiftModifier):
            return      # tek tuş: Ctrl / Alt / Shift'li tuşlar başka işlere ayrılmış
        name = key_name(e)
        if not name or k in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space, Qt.Key.Key_Tab,
                             Qt.Key.Key_Home):
            return
        self.set_value(name)
        self.changed.emit(name)


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
    def __init__(self, parent, hotkeys, on_hotkeys_changed=None, updater=None):
        super().__init__(parent, t("preferences"))
        self.hotkeys = hotkeys
        self.updater = updater
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
        from .toolbar import POSITIONS, set_position
        self.c_tb = _combo([(pos, t("tb_" + pos)) for pos in POSITIONS], prefs.get("toolbar_pos", "bottom"))
        self.c_tb.currentIndexChanged.connect(lambda: set_position(self.c_tb.currentData()))
        lay.addWidget(_row(t("toolbar_pos"), self.c_tb, t("tb_drag_hint")))

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

        # --- Tahta kısayolları (araç tuşları)
        section(t("board_keys"))
        sub = QLabel(t("board_keys_sub"))
        sub.setObjectName("Secondary")
        sub.setWordWrap(True)
        lay.addWidget(sub)
        from .tools import TOOL_ORDER, tool_keys, set_tool_key, reset_tool_keys, state as tstate
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(4)
        self.key_btns = {}
        keys = tool_keys()
        for i, tool in enumerate(TOOL_ORDER):
            lbl = QLabel(t("tool_" + tool))
            kb = KeyButton(keys.get(tool, ""))
            kb.changed.connect(lambda v, x=tool: set_tool_key(x, v))
            self.key_btns[tool] = kb
            grid.addWidget(lbl, i // 2, (i % 2) * 2)
            grid.addWidget(kb, i // 2, (i % 2) * 2 + 1)
        gw = QWidget()
        gw.setLayout(grid)
        lay.addWidget(gw)
        rb = QPushButton(t("keys_reset"))
        rb.setObjectName("Flat")
        rb.clicked.connect(reset_tool_keys)
        rr = QHBoxLayout()
        rr.addStretch(1)
        rr.addWidget(rb)
        lay.addLayout(rr)

        def _sync_keys():
            ks = tool_keys()
            for tool, b in self.key_btns.items():
                b.set_value(ks.get(tool, ""))
        tstate.keys_changed.connect(_sync_keys)
        self.finished.connect(lambda _r: tstate.keys_changed.disconnect(_sync_keys))

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
        c4 = _combo([("png", "PNG"), ("jpg", "JPEG"), ("pdf", "PDF")], prefs.get("save_format", "png"))
        c4.currentIndexChanged.connect(lambda: prefs.set("save_format", c4.currentData()))
        lay.addWidget(_row(t("save_format"), c4, t("save_format_sub")))

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

        # --- Güncellemeler
        section(t("updates"))
        sw = ToggleSwitch(prefs.get("check_updates", True))
        sw.toggled.connect(lambda v: prefs.set("check_updates", v))
        lay.addWidget(_row(t("check_updates"), sw, t("check_updates_sub")))
        ux = QHBoxLayout()
        self.upd_lbl = QLabel("")
        self.upd_lbl.setObjectName("Secondary")
        self.upd_lbl.setOpenExternalLinks(True)
        ub = QPushButton(t("check_now"))
        ub.setObjectName("Pill")
        ub.clicked.connect(self._check_now)
        ux.addWidget(self.upd_lbl, 1)
        ux.addWidget(ub)
        lay.addLayout(ux)

        # --- Künye
        section(t("about"))
        lay.addWidget(self._about_box())
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

    def _check_now(self):
        if self.updater is None:
            return
        from .updater import RELEASES
        self.upd_lbl.setText(t("checking"))

        def res(status, ver):
            try:
                self.updater.result.disconnect(res)
            except TypeError:
                pass
            if status == "new":
                self.upd_lbl.setText(f'{t("update_available", v=ver)} · <a href="{RELEASES}">{t("download")}</a>')
            elif status == "latest":
                self.upd_lbl.setText(t("up_to_date"))
            else:
                self.upd_lbl.setText(t("update_error"))
        self.updater.result.connect(res)
        self.updater.check(manual=True)

    def _about_box(self):
        import platform
        from PyQt6.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
        from . import __version__, __author__, REPO
        url = f"https://github.com/{REPO}"
        rows = [(t("about_app"), f"delta {__version__}"),
                (t("about_author"), __author__),
                (t("about_license"), "GNU GPL v3.0"),
                (t("about_desc_k"), t("about_line")),
                ("GitHub", f'<a href="{url}">{url.replace("https://", "")}</a>')]
        engines = []
        try:
            import imageio_ffmpeg
            engines.append(("FFmpeg", imageio_ffmpeg.get_ffmpeg_version()))
        except Exception:
            pass
        engines.append(("Qt / PyQt6", f"{QT_VERSION_STR} / {PYQT_VERSION_STR}"))
        engines.append(("Python", platform.python_version()))
        try:
            import PIL
            engines.append(("Pillow", PIL.__version__))
        except Exception:
            pass
        engines.append((t("about_ocr"), "Windows.Media.Ocr"))
        box = QWidget()
        g = QGridLayout(box)
        g.setContentsMargins(0, 6, 0, 0)
        g.setHorizontalSpacing(18)
        g.setVerticalSpacing(5)
        r = 0
        for k, v in rows:
            a = QLabel(k)
            a.setObjectName("Secondary")
            b = QLabel(v)
            b.setWordWrap(True)
            b.setOpenExternalLinks(True)
            b.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            g.addWidget(a, r, 0, Qt.AlignmentFlag.AlignTop)
            g.addWidget(b, r, 1)
            r += 1
        head = QLabel(t("about_engines"))
        head.setStyleSheet("font-weight: 700; margin-top: 8px;")
        g.addWidget(head, r, 0, 1, 2)
        r += 1
        for k, v in engines:
            a = QLabel(k)
            a.setObjectName("Secondary")
            b = QLabel(v)
            b.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            g.addWidget(a, r, 0)
            g.addWidget(b, r, 1)
            r += 1
        note = QLabel(t("about_licenses_note"))
        note.setObjectName("Secondary")
        note.setWordWrap(True)
        g.addWidget(note, r, 0, 1, 2)
        g.setColumnStretch(1, 1)
        return box

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
    ("1 · 2", "h_k_pen"), ("3 · 4 · 5 · 6", "h_k_shapes"), ("7", "h_k_text"), ("8", "h_k_laser"),
    ("9", "h_k_eraser"), ("0", "h_k_select"), ("A … Z", "h_k_type"), ("Enter", "h_k_enter"),
    ("Shift+1 – 7", "h_k_colors"), ("Ctrl+↑ / Ctrl+↓", "h_k_size"), ("Ctrl+I", "h_k_image"),
    ("Ctrl+Z / Ctrl+Y", "h_k_undo"), ("Ctrl+C / X / V / D", "h_k_clip"), ("Ctrl+A · Delete", "h_k_sel"),
    ("Home · Ctrl+0", "h_k_fit"), ("Ctrl+G", "h_k_grid"), ("Ctrl+N · Ctrl+Tab", "h_k_notes"),
    ("Ctrl+S · Ctrl+Shift+S", "h_k_save"), ("Ctrl+Shift+C", "h_k_copyall"), ("F11 · Ctrl+B", "h_k_view"),
    ("F1", "h_k_help"),
]
