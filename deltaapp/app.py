"""Uygulama girişi: tek örnek, tema, sistem tepsisi, her yerde çalışan kısayollar.

python main.py           pencereyle açılır
python main.py --tray    sessizce tepside başlar (Windows ile başlat bunu kullanır)
python main.py --snip    ekran alıntısını başlatır (masaüstündeki "delta alıntı" simgesi; delta kapalıysa tepside açılır)
python main.py --quit    çalışan delta'yı notları kaydedip kapatır (kurulum / kaldırma kullanır)
"""
import ctypes
import os
import sys

from PyQt6.QtCore import Qt, QObject, QTimer
from PyQt6.QtGui import QIcon, QFont, QAction
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu

from .config import prefs, asset

SERVER_NAME = "delta-whiteboard-single-instance-v1"


def _send_to_running(cmd: str) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(300):
        return False
    try:
        ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
    except Exception:
        pass
    sock.write(cmd.encode("utf-8"))
    sock.flush()
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True


class DeltaApp(QObject):
    def __init__(self, app, start_hidden=False):
        super().__init__()
        self.app = app
        from .theme import theme
        theme.apply()
        from .pages import NoteStore
        from .window import MainWindow
        from .hotkeys import HotkeyManager
        from .capture import CaptureController
        from .annotate import AnnotateOverlay
        from .recorder import Recorder
        from .pin import PinManager
        self.store = NoteStore()
        self.win = MainWindow(self.store)
        self.hotkeys = HotkeyManager()
        self.capture = CaptureController()
        self.annotate = AnnotateOverlay()
        self.recorder = Recorder()
        self.pins = PinManager()
        self._restore_after_capture = False

        self.win.request_capture.connect(self.start_capture_from_window)
        self.win.request_annotate.connect(self.annotate.toggle)
        self.win.request_record.connect(self.start_record_from_window)
        self.win.request_prefs.connect(self.show_prefs)
        self.win.request_quit.connect(self.quit)
        self.capture.to_delta.connect(self.win.receive_image)
        self.capture.saved.connect(lambda p: self.notify(self._t("saved_to", p=os.path.basename(p))))
        self.capture.finished.connect(self._capture_done)
        self.capture.record.connect(self._begin_record)
        self.capture.pinned.connect(lambda d: self.pins.add(*d))
        self.capture.ocr_req.connect(self.ocr_snip)
        self.pins.to_delta.connect(self.win.receive_image)
        self.pins.saved.connect(lambda p: self.notify(self._t("saved_to", p=os.path.basename(p))))
        self.recorder.saved.connect(self._record_saved)
        self.recorder.failed.connect(lambda m: self.notify(self._t("rec_failed"), m))
        self.recorder.stopped.connect(self._record_stopped)
        self._last_video = None
        self.annotate.export.connect(self.win.receive_image)
        self.hotkeys.triggered.connect(self.on_hotkey)

        self._make_tray()
        self.apply_hotkeys()
        if not start_hidden:
            self.win.show()
        # güncelleme denetimi: açılıştan biraz sonra, günde en fazla bir kez
        from .updater import UpdateChecker
        self.updater = UpdateChecker(self)
        self.updater.found.connect(self._update_found)
        self._update_page = None
        QTimer.singleShot(6000, self.updater.check_auto)

    def _t(self, k, **kw):
        from .i18n import t
        return t(k, **kw)

    # --- tepsi
    def _make_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.win.tray_ok = False
            return
        self.tray = QSystemTrayIcon(self.app.windowIcon(), self)
        self.tray.setToolTip("delta")
        m = QMenu()
        self.tray_menu = m
        self.act_cap = QAction(self._t("tray_capture"), m)
        self.act_cap.triggered.connect(lambda: self.capture.start(150))
        self.act_ann = QAction(self._t("tray_annotate"), m)
        self.act_ann.triggered.connect(self.annotate.toggle)
        self.act_rec = QAction(self._t("tray_record"), m)
        self.act_rec.triggered.connect(lambda: self.on_hotkey("record"))
        self.act_note = QAction(self._t("tray_note"), m)
        self.act_note.triggered.connect(self.win.quick_note)
        self.act_unpin = QAction(self._t("pin_close_all"), m)
        self.act_unpin.triggered.connect(self.pins.close_all)
        self.act_unpin.setVisible(False)
        self.pins.changed.connect(lambda: self.act_unpin.setVisible(bool(self.pins.pins)))
        a_show = QAction(self._t("tray_show"), m)
        a_show.triggered.connect(self.win.bring_front)
        a_prefs = QAction(self._t("preferences"), m)
        a_prefs.triggered.connect(self.show_prefs)
        a_quit = QAction(self._t("tray_quit"), m)
        a_quit.triggered.connect(self.win.quit_app)
        for a in (self.act_cap, self.act_rec, self.act_ann, self.act_note, self.act_unpin):
            m.addAction(a)
        m.addSeparator()
        m.addAction(a_show)
        m.addAction(a_prefs)
        m.addSeparator()
        m.addAction(a_quit)
        self.tray.setContextMenu(m)
        self.tray.activated.connect(self._tray_activated)
        self.tray.messageClicked.connect(self._message_clicked)
        self.tray.show()
        self.win.tray_ok = True
        self.win.tray_message = self.notify

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            if self.win.isVisible() and not self.win.isMinimized() and self.win.isActiveWindow():
                self.win.hide()
            else:
                self.win.bring_front()

    def notify(self, title, text=""):
        if self.tray is not None:
            if not text:
                title, text = "delta", title
            self.tray.showMessage(title, text, self.app.windowIcon(), 3500)

    # --- kısayollar
    def apply_hotkeys(self):
        for name in ("capture", "annotate", "note", "record"):
            self.hotkeys.set(name, prefs.get("hotkey_" + name, ""))
        cap, ann, note, rec = (prefs.get("hotkey_" + n, "") for n in ("capture", "annotate", "note", "record"))
        self.win.titlebar.set_hotkey_tips(cap, ann, rec)
        if self.tray is not None:
            self.act_cap.setText(self._t("tray_capture") + (f"\t{cap}" if cap else ""))
            self.act_ann.setText(self._t("tray_annotate") + (f"\t{ann}" if ann else ""))
            self.act_note.setText(self._t("tray_note") + (f"\t{note}" if note else ""))
            self._rec_text = self._t("tray_record") + (f"\t{rec}" if rec else "")
            self.act_rec.setText(self._t("rec_stop") if self.recorder.active() else self._rec_text)

    def on_hotkey(self, name):
        if name == "record":
            if self.recorder.active():
                self.recorder.stop()
            elif not self.capture.active():
                self.capture.start(0, mode="record")
            return
        if name == "capture":
            if self.annotate.isVisible():
                self.annotate.close_overlay()
            self.capture.start()
        elif name == "annotate":
            if not self.capture.active():
                self.annotate.toggle()
        elif name == "note":
            self.win.quick_note()

    def start_capture_from_window(self):
        """Pencereden basılınca delta önce çekilir, arkadaki ekran alınır."""
        self._restore_after_capture = self.win.isVisible() and not self.win.isMinimized()
        self.win.hide()
        self.capture.start(220)

    def start_record_from_window(self):
        if self.recorder.active():
            self.recorder.stop()
            return
        self._restore_after_capture = self.win.isVisible() and not self.win.isMinimized()
        self.win.hide()
        self.capture.start(220, mode="record")

    def _begin_record(self, data):
        scr, sel, dpr = data
        self._restore_after_capture = False   # kayıt boyunca delta gizli kalsın
        QTimer.singleShot(120, lambda: self.recorder.start(scr, sel, dpr))
        if self.tray is not None:
            self.act_rec.setText(self._t("rec_stop"))

    def _update_found(self, ver, page):
        self._update_page = page
        self._last_video = None
        self.notify(self._t("update_notify", v=ver), self._t("update_notify_sub"))

    def _record_saved(self, path):
        self._update_page = None
        self._last_video = path
        self.notify(self._t("rec_saved_title"), self._t("rec_saved", p=os.path.basename(path)))

    def _record_stopped(self):
        if self.tray is not None:
            self.act_rec.setText(getattr(self, "_rec_text", self._t("tray_record")))

    def _message_clicked(self):
        """Bildirime tıklanınca: yeni sürüm sayfası açılır ya da son video Gezgin'de seçili gösterilir."""
        if getattr(self, "_update_page", None):
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl(self._update_page))
            self._update_page = None
            return
        if self._last_video and os.path.exists(self._last_video):
            import subprocess
            subprocess.Popen(["explorer", "/select,", os.path.normpath(self._last_video)])
            self._last_video = None

    def _capture_done(self):
        if self._restore_after_capture and not self.win.isVisible():
            self.win.bring_front()
        self._restore_after_capture = False

    def show_prefs(self):
        from .dialogs import PrefsDialog
        parent = self.win if self.win.isVisible() else None
        d = PrefsDialog(parent, self.hotkeys, self.apply_hotkeys, getattr(self, "updater", None))
        d.exec()

    def ocr_snip(self, pm):
        """Alıntıdaki yazıyı oku, panoya kopyala, bildirimle göster."""
        from .ocr import read_text

        def done(text):
            if text:
                QApplication.clipboard().setText(text)
                first = text.splitlines()[0][:60]
                self.notify(self._t("ocr_done", n=text.count("\n") + 1), first)
            else:
                self.notify(self._t("ocr_empty"))
        read_text(pm.toImage(), done, lambda m: self.notify(self._t("ocr_failed"), m))

    def handle_message(self, cmd):
        if cmd == "show":
            self.win.bring_front()
        elif cmd == "snip":   # "delta alıntı" simgesi: tıklanan kısayolun izi ekrandan kalksın diye kısa bekle
            if self.annotate.isVisible():
                self.annotate.close_overlay()
            self.capture.start(250)
        elif cmd == "quit":   # kurulum / kaldırma: notları kaydedip kapan
            self.win.quit_app()

    def quit(self):
        if self.recorder.active():
            self.recorder.stop()
            if self.recorder.proc is not None:
                self.recorder.proc.waitForFinished(8000)
        self.win.save_state()
        self.hotkeys.unregister_all()
        if self.tray is not None:
            self.tray.hide()
        self.app.quit()


def _install_excepthook():
    """PyQt varsayılan olarak yakalanmamış hatada uygulamayı kapatır; toplantı ortasında çökmesin,
    hata %LOCALAPPDATA%\\delta\\error.log dosyasına yazılsın."""
    import traceback
    from .config import DATA_DIR

    def hook(etype, value, tb):
        txt = "".join(traceback.format_exception(etype, value, tb))
        try:
            sys.__stderr__.write(txt)
        except Exception:
            pass
        try:
            with open(os.path.join(DATA_DIR, "error.log"), "a", encoding="utf-8") as f:
                f.write(txt + "\n")
        except OSError:
            pass
    sys.excepthook = hook


def _selfcheck():
    """delta.exe --selfcheck: derlenmiş pakette tüm modüller, logo ve ffmpeg yerinde mi? (çıkış kodu 0 = tamam)"""
    import importlib
    from .config import asset
    for m in ("window", "canvas", "items", "pages", "capture", "annotate", "recorder", "pin", "hotkeys",
              "dialogs", "titlebar", "toolbar", "theme", "icons", "widgets", "winident", "ocr", "export", "updater"):
        importlib.import_module("deltaapp." + m)
    from .recorder import find_ffmpeg
    from PyQt6.QtGui import QGuiApplication, QImage
    _ = QGuiApplication(sys.argv[:1])
    ok = find_ffmpeg() is not None and not QImage(asset("logo.png")).isNull() and os.path.exists(asset("logo.ico")) \
        and os.path.exists(asset("snip.ico"))
    return 0 if ok else 3


def main():
    if "--selfcheck" in sys.argv:
        return _selfcheck()
    _install_excepthook()
    from .winident import set_process_id
    set_process_id()
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("delta")
    app.setOrganizationName("delta")
    app.setQuitOnLastWindowClosed(False)  # tepside yaşamaya devam
    f = QFont("Segoe UI Variable Text")
    f.setPointSizeF(9.5)
    app.setFont(f)
    ico = asset("logo.ico") if os.path.exists(asset("logo.ico")) else asset("logo.png")
    app.setWindowIcon(QIcon(ico))

    try:
        from PyQt6.QtCore import QTranslator, QLibraryInfo
        if prefs.get("language", "tr") == "tr":
            tr = QTranslator(app)
            if tr.load("qtbase_tr", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
                app.installTranslator(tr)
    except Exception:
        pass

    if "--quit" in sys.argv:   # çalışan delta'yı düzgünce kapat (kurulum betiği kullanır)
        _send_to_running("quit")
        return 0
    snip = "--snip" in sys.argv
    hidden = "--tray" in sys.argv or snip
    if _send_to_running("snip" if snip else "tray" if hidden else "show"):
        return 0
    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    server.listen(SERVER_NAME)

    d = DeltaApp(app, start_hidden=hidden)

    def on_conn():
        s = server.nextPendingConnection()
        if s is None:
            return

        def read():
            cmd = bytes(s.readAll()).decode("utf-8", errors="ignore").strip()
            QTimer.singleShot(0, lambda: d.handle_message(cmd))
        s.readyRead.connect(read)
        s.disconnected.connect(s.deleteLater)
    server.newConnection.connect(on_conn)
    app._delta = d
    if snip:
        QTimer.singleShot(300, lambda: d.handle_message("snip"))
    return app.exec()
