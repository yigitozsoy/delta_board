"""Ana pencere: çerçevesiz (gamma gibi, Windows Snap çalışır), tuval + alttaki araç çubuğu + sağda notlar."""
import ctypes
import os
from ctypes import wintypes
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, QPointF, pyqtSignal, QByteArray
from PyQt6.QtGui import QCursor, QKeySequence, QShortcut, QGuiApplication
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
                             QMessageBox)

from .canvas import Board, render_scene
from .config import prefs, snapshot_dir
from .i18n import t
from .pages import NotesPanel
from .theme import theme, current_name, qcolor
from .titlebar import TitleBar
from .toolbar import ToolBar
from .widgets import Divider, IconButton

user32 = ctypes.windll.user32
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, wintypes.UINT]
user32.GetWindowLongW.restype = ctypes.c_long
user32.MonitorFromWindow.restype = wintypes.HANDLE
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
HWND_TOPMOST, HWND_NOTOPMOST = wintypes.HWND(-1), wintypes.HWND(-2)
GWL_STYLE = -16
WS_THICKFRAME, WS_CAPTION, WS_MAXIMIZEBOX, WS_MINIMIZEBOX, WS_SYSMENU = 0x40000, 0xC00000, 0x10000, 0x20000, 0x80000
WM_NCCALCSIZE, WM_NCHITTEST = 0x0083, 0x0084
SWP_FLAGS = 0x0002 | 0x0001 | 0x0010  # NOMOVE | NOSIZE | NOACTIVATE


class NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD)]


class BoardArea(QWidget):
    """Tuval + üstünde yüzen araç çubuğu, yakınlaştırma çipi ve boş not ipucu."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BoardArea")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.board = Board(self)
        self.toolbar = ToolBar(self, lambda: self.board)
        self.hint = QLabel(self)
        self.hint.setObjectName("EmptyHint")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.hint.setText(t("empty_hint"))
        self.zoom_box = QWidget(self)
        zl = QHBoxLayout(self.zoom_box)
        zl.setContentsMargins(0, 0, 0, 0)
        zl.setSpacing(4)
        self.btn_fit = IconButton("fit", t("fit_all") + " (Home)", 34, 18)
        self.btn_fit.clicked.connect(self.board.fit_all)
        self.zoom_chip = QPushButton("100%")
        self.zoom_chip.setObjectName("Chip")
        self.zoom_chip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.zoom_chip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.zoom_chip.setToolTip(t("zoom_reset_tip"))
        self.zoom_chip.clicked.connect(lambda: self.board.set_zoom(1.0))
        zl.addWidget(self.btn_fit)
        zl.addWidget(self.zoom_chip)
        self.toolbar.placed.connect(self._place_overlays)
        self.board.zoom_changed.connect(lambda z: self.zoom_chip.setText(f"{round(z * 100)}%"))
        self.board.content_changed.connect(self._update_hint)

    def _update_hint(self):
        self.hint.setVisible(self.board.is_empty())

    def resizeEvent(self, e):
        self.board.setGeometry(self.rect())
        self.toolbar.place(16)          # placed → _place_overlays
        super().resizeEvent(e)

    def _place_overlays(self):
        """Yakınlaştırma çipi ve boş not ipucu, araç çubuğunun konumuna göre yerleşir."""
        tb = self.toolbar.geometry()
        self.zoom_box.adjustSize()
        zx = self.width() - self.zoom_box.width() - 16
        zy = self.height() - self.zoom_box.height() - 22
        if self.toolbar.vertical and tb.left() > self.width() // 2:      # sağda dikey çubuk
            zx = tb.left() - self.zoom_box.width() - 10
        elif not self.toolbar.vertical and tb.top() > self.height() // 2 and zx < tb.right() + 8:
            zy = tb.top() - self.zoom_box.height() - 8                  # dar pencerede alttaki çubuğa binmesin
        self.zoom_box.move(zx, zy)
        self.hint.setGeometry(0, 0, self.width(), self.height() - 80)
        for w in (self.hint, self.toolbar, self.zoom_box):
            w.raise_()
        self.board.toast_label.raise_()


class MainWindow(QMainWindow):
    request_capture = pyqtSignal()
    request_annotate = pyqtSignal()
    request_record = pyqtSignal()
    request_prefs = pyqtSignal()
    request_quit = pyqtSignal()

    def __init__(self, store):
        super().__init__()
        self.store = store
        self.page = None
        self._really_quit = False
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window |
                            Qt.WindowType.WindowMinMaxButtonsHint)
        self.setWindowTitle("delta")
        self.setMinimumSize(780, 520)

        root = QWidget(self)
        root.setObjectName("Root")
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.titlebar = TitleBar(root)
        v.addWidget(self.titlebar)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.area = BoardArea(root)
        self.board = self.area.board
        body.addWidget(self.area, 1)
        self.panel_div = Divider(root, vertical=True)
        body.addWidget(self.panel_div)
        self.panel = NotesPanel(store, root)
        body.addWidget(self.panel)
        v.addLayout(body, 1)
        self.setCentralWidget(root)

        tb = self.titlebar
        tb.minimize.connect(self.showMinimized)
        tb.maximize.connect(self.toggle_maximize)
        tb.close.connect(self.close)
        tb.prefs_clicked.connect(self.request_prefs.emit)
        tb.new_note.connect(self.new_note)
        tb.capture.connect(self.request_capture.emit)
        tb.annotate.connect(self.request_annotate.emit)
        tb.record.connect(self.request_record.emit)
        tb.theme_clicked.connect(self.toggle_theme)
        tb.pin_clicked.connect(lambda: self.set_pinned(not prefs.get("pinned", False)))
        tb.panel_clicked.connect(lambda: self.set_panel(not self.panel.isVisible()))
        tb.title_edited.connect(self._title_edited)
        self.panel.open_page.connect(self.open_page)
        self.panel.new_page.connect(self.new_note)
        self.panel.rename_page.connect(self.rename_page)
        self.panel.delete_page.connect(self.delete_page)
        self.panel.export_page.connect(self.export_page)
        self.panel.export_all.connect(self.export_all_pdf)
        self.board.content_changed.connect(self._refresh_title)
        store.list_changed.connect(self._refresh_title)
        theme.changed.connect(lambda _: store.restyle_all())

        for seq, fn in (("Ctrl+N", self.new_note), ("Ctrl+S", self.save_png), ("Ctrl+Shift+S", self.save_png_as),
                        ("Ctrl+Shift+C", lambda: self.board.copy(only_image=True)), ("F11", self.toggle_fullscreen),
                        ("Ctrl+,", self.request_prefs.emit), ("Ctrl+Tab", lambda: self._cycle(1)),
                        ("Ctrl+Shift+Tab", lambda: self._cycle(-1)), ("F1", self.show_help),
                        ("F2", lambda: self.rename_page(self.page) if self.page is not None else None),
                        ("Ctrl+B", lambda: self.set_panel(not self.panel.isVisible()))):
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(fn)

        self.set_panel(bool(prefs.get("sidebar_visible", True)), save=False)
        self._restore_geometry()
        last = store.get(prefs.get("last_note"))
        pages = store.sorted()
        self.open_page(last or (pages[0] if pages else store.create()))
        self.titlebar.set_pinned(bool(prefs.get("pinned", False)))

    # ============================================================ notlar
    def open_page(self, page):
        if page is None or page is self.page:
            return
        old = self.page
        self.board.set_page(page)
        self.page = page
        prefs.set("last_note", page.id)
        if old is not None:
            if not self.store.discard_if_empty(old):
                if old.saved_once:
                    self.store.mark_dirty(old)
        self.panel.set_current(page.id)
        self._refresh_title()
        self.board.setFocus()

    def new_note(self):
        if self.page is not None and self.page.is_empty() and not self.page.saved_once:
            self.board.setFocus()
            self.board.toast(t("already_empty"))
            return self.page
        p = self.store.create()
        self.open_page(p)
        return p

    def _cycle(self, d):
        pages = [p for p in self.store.sorted() if p.saved_once or p is self.page]
        if len(pages) < 2 or self.page not in pages:
            return
        i = (pages.index(self.page) + d) % len(pages)
        self.open_page(pages[i])

    def _refresh_title(self):
        if self.page is None:
            return
        p = self.page
        if p.scene is not None:
            p.compute_auto_title()
        self.titlebar.set_title(p.title, p.auto or t("note_untitled", d=_short_now(p.created)))

    def _title_edited(self, text):
        if self.page is not None and text.strip() != self.page.title:
            if not self.page.saved_once and self.page.is_empty():
                self.page.title = text.strip()
                return
            self.store.rename(self.page, text)
        self.board.setFocus()

    def rename_page(self, p):
        if p is not self.page:
            self.open_page(p)
        self.titlebar.title.begin_edit()

    def delete_page(self, p):
        r = QMessageBox.question(self, t("delete_note"), t("delete_confirm", name=p.display_title()))
        if r != QMessageBox.StandardButton.Yes:
            return
        if p is self.page:
            others = [x for x in self.store.sorted() if x is not p and x.saved_once]
            nxt = others[0] if others else self.store.create()
            self.board.set_page(nxt)
            self.page = nxt
            prefs.set("last_note", nxt.id)
            self.panel.set_current(nxt.id)
        self.store.delete(p)
        self._refresh_title()

    def export_page(self, p):
        p.ensure_loaded()
        img = render_scene(p.scene)
        if img is None:
            self.board.toast(t("nothing_to_copy"))
            return
        from .export import file_filter, fix_ext, save_image
        fmt = prefs.get("save_format", "png")
        name = _safe(p.display_title())
        path, flt = QFileDialog.getSaveFileName(self, t("export_as"), os.path.join(snapshot_dir(), name + "." + fmt),
                                                file_filter(fmt))
        if path:
            path = fix_ext(path, flt)
            if save_image(img, path, qcolor("bg")):
                self.board.toast(t("saved_to", p=os.path.basename(path)))
            else:
                self.board.toast(t("save_failed"))

    def export_all_pdf(self):
        """Tüm notlar tek PDF'te (en yeni not ilk sayfada)."""
        from .export import export_pdf
        imgs = []
        for p in self.store.pages:
            p.ensure_loaded()
            img = render_scene(p.scene)
            if img is not None:
                imgs.append(img)
        if not imgs:
            self.board.toast(t("nothing_to_copy"))
            return
        default = os.path.join(snapshot_dir(), "delta " + datetime.now().strftime("%Y-%m-%d") + ".pdf")
        path, _ = QFileDialog.getSaveFileName(self, t("export_all_pdf"), default, "PDF (*.pdf)")
        if path:
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
            ok = export_pdf(imgs, path)
            self.board.toast(t("saved_to", p=os.path.basename(path)) if ok else t("save_failed"), 2600)

    def save_png(self):
        """Ctrl+S: Seçenekler'deki biçimde (PNG / JPEG / PDF) Resimler\\delta klasörüne hemen kaydeder."""
        from .export import save_image
        img = render_scene(self.board.scene())
        if img is None:
            self.board.toast(t("nothing_to_copy"))
            return
        fmt = prefs.get("save_format", "png")
        name = _safe(self.page.display_title()) + " " + datetime.now().strftime("%H.%M.%S")
        path = os.path.join(snapshot_dir(), name + "." + fmt)
        if save_image(img, path, qcolor("bg")):
            self.board.toast(t("saved_to", p=path), 2600)
        else:
            self.board.toast(t("save_failed"))

    def save_png_as(self):
        if self.page is not None:
            self.export_page(self.page)

    # ============================================================ dışarıdan gelen görüntü
    def receive_image(self, pm):
        """Ekran alıntısı / ekrana çiz çıktısı: yeni nota (veya açık nota) görsel olarak eklenir."""
        self.bring_front()
        if prefs.get("capture_target", "new") == "new" and not (self.page.is_empty() and not self.page.saved_once):
            self.new_note()
        dpr = pm.devicePixelRatio()
        img = pm.toImage()
        img.setDevicePixelRatio(1.0)
        at = self.board.mapToScene(self.board.viewport().rect().center())
        it = self.board.insert_image(img, at, dpr)
        if it is not None and self.page.is_empty() is False:
            self.board.toast(t("cap_added"))

    def quick_note(self):
        """Kısayolla hızlı not: pencere öne gelir, boş not açılır, imleç yazmaya hazır."""
        self.bring_front()
        p = self.new_note()
        if p is not None:
            QTimer.singleShot(60, lambda: self.board.new_text(
                self.board.mapToScene(self.board.viewport().rect().center()) + QPointF(-120, -60)))

    def bring_front(self):
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        try:
            user32.SetForegroundWindow(int(self.winId()))
        except Exception:
            pass
        self.board.setFocus()

    # ============================================================ görünüm
    def set_panel(self, on, save=True):
        self.panel.setVisible(on)
        self.panel_div.setVisible(on)
        self.titlebar.btn_panel.setChecked(on)
        if save:
            prefs.set("sidebar_visible", on)

    def toggle_theme(self):
        theme.apply("light" if current_name() == "dark" else "dark")

    def set_pinned(self, on):
        prefs.set("pinned", on)
        self.titlebar.set_pinned(on)
        try:
            user32.SetWindowPos(wintypes.HWND(int(self.winId())), HWND_TOPMOST if on else HWND_NOTOPMOST,
                                0, 0, 0, 0, SWP_FLAGS)
        except Exception:
            pass

    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.titlebar.show()
        else:
            self.titlebar.hide()
            self.showFullScreen()

    def show_help(self):
        from .dialogs import HelpDialog
        HelpDialog(self).exec()

    def changeEvent(self, e):
        if e.type() == e.Type.WindowStateChange:
            self.titlebar.set_maximized(self.isMaximized())
        super().changeEvent(e)

    def _restore_geometry(self):
        g = prefs.get("window_geometry")
        ok = False
        if g:
            try:
                ok = self.restoreGeometry(QByteArray.fromBase64(g.encode("ascii")))
            except Exception:
                ok = False
        if not ok:
            scr = QGuiApplication.primaryScreen().availableGeometry()
            w, h = min(1320, scr.width() - 80), min(840, scr.height() - 80)
            self.resize(w, h)
            self.move(scr.x() + (scr.width() - w) // 2, scr.y() + (scr.height() - h) // 2)

    def save_state(self):
        self.board.store_view()
        if self.page is not None and self.page.saved_once:
            self.store.mark_dirty(self.page)
        self.store.flush()
        prefs.set("window_geometry", bytes(self.saveGeometry().toBase64()).decode("ascii"))

    def closeEvent(self, e):
        self.board.finish_text()
        self.save_state()
        if prefs.get("close_to_tray", True) and not self._really_quit and getattr(self, "tray_ok", False):
            e.ignore()
            self.hide()
            if not prefs.get("tray_hint_shown", False):
                prefs.set("tray_hint_shown", True)
                self.tray_message(t("tray_hint_title"), t("tray_hint"))
            return
        e.accept()
        self.request_quit.emit()

    def tray_message(self, title, text):
        pass  # app.py bağlar

    def quit_app(self):
        self._really_quit = True
        self.close()

    def showEvent(self, e):
        super().showEvent(e)
        self._apply_native_frame()
        hwnd = int(self.winId())
        if getattr(self, "_ident_hwnd", None) != hwnd:  # görev çubuğunda "Python" değil "delta" + logo
            from .winident import apply_to_window
            apply_to_window(hwnd)
            self._ident_hwnd = hwnd
        if prefs.get("pinned", False):
            QTimer.singleShot(0, lambda: self.set_pinned(True))

    # ============================================================ Windows Snap
    def _apply_native_frame(self):
        """Çerçevesiz pencereye Windows'un boyutlandırma / Snap / animasyon stillerini geri verir."""
        if self.isFullScreen():
            return
        try:
            hwnd = int(self.winId())
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            want = style | WS_THICKFRAME | WS_CAPTION | WS_MAXIMIZEBOX | WS_MINIMIZEBOX | WS_SYSMENU
            if want != style:
                user32.SetWindowLongW(hwnd, GWL_STYLE, want)
                user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0002 | 0x0001 | 0x0004 | 0x0010 | 0x0020)
        except Exception:
            pass

    def nativeEvent(self, event_type, message):
        try:
            msg = wintypes.MSG.from_address(int(message))
        except Exception:
            return False, 0
        if msg.message == WM_NCCALCSIZE and msg.wParam:
            if user32.IsZoomed(msg.hWnd) and not self.isFullScreen():
                params = NCCALCSIZE_PARAMS.from_address(msg.lParam)
                mon = user32.MonitorFromWindow(msg.hWnd, 2)
                mi = MONITORINFO()
                mi.cbSize = ctypes.sizeof(MONITORINFO)
                if user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
                    params.rgrc[0] = mi.rcWork
            return True, 0
        if msg.message == WM_NCHITTEST and not self.isFullScreen():
            gp = QCursor.pos()
            if not self.isMaximized():
                g = self.frameGeometry()
                m = 6
                left, right = gp.x() <= g.left() + m, gp.x() >= g.right() - m
                top, bottom = gp.y() <= g.top() + m, gp.y() >= g.bottom() - m
                code = {(True, False, True, False): 13, (False, True, True, False): 14,
                        (True, False, False, True): 16, (False, True, False, True): 17}.get((left, right, top, bottom))
                if code is None:
                    code = 10 if left else 11 if right else 12 if top else 15 if bottom else None
                if code is not None:
                    return True, code
            tb = self.titlebar
            if tb.isVisible():
                local = tb.mapFromGlobal(gp)
                if tb.rect().contains(local):
                    child = tb.childAt(local)
                    if tb.is_drag_area(child):
                        return True, 2  # HTCAPTION
        return False, 0


def _short_now(ts):
    from .pages import fmt_date
    return fmt_date(ts)


def _safe(name):
    bad = '<>:"/\\|?*'
    s = "".join("_" if c in bad else c for c in name).strip().rstrip(".")
    return s[:80] or "delta"
