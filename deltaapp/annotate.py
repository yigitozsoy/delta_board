"""Ekrana çiz: o anki ekranın üstüne saydam bir katman açılır, toplantıda paylaşılan ekranın üzerine
çizilir / lazerle gösterilir. Kısayol (varsayılan Win+Shift+D) aç-kapa yapar.

  Esc ............... kapat (çizimler silinir)
  "Fareyi bırak" .... çizimler ekranda kalır, fare alttaki programa geçer; kısayola tekrar basınca çizime dönülür
  "Tahta" ........... arkayı temayla kapatır (boş beyaz/siyah tahta)
  "delta'ya aktar" .. ekran + çizimler tek görüntü olarak yeni nota gider
"""
import ctypes

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPointF
from PyQt6.QtGui import QGuiApplication, QCursor, QPainter, QPixmap
from PyQt6.QtWidgets import QWidget

from .canvas import Board
from .i18n import t
from .pages import Page
from .toolbar import ToolBar
from .tools import state
from .widgets import Toast

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT, WS_EX_LAYERED = 0x20, 0x80000
user32 = ctypes.windll.user32
user32.GetWindowLongW.restype = ctypes.c_long


class AnnotateOverlay(QWidget):
    export = pyqtSignal(object)   # QPixmap

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.page = Page("annotate", temp=True)
        self.board = Board(self, transparent=True, fixed=True)
        self.board.set_page(self.page)
        self.board.escape_pressed.connect(self.close_overlay)
        self.passthrough = False
        self._prev_tool = None
        self.toolbar = ToolBar(self, lambda: self.board, extras=[
            ("board", "whiteboard", t("ann_board"), self._toggle_board, True),
            ("pass", "passthrough", t("ann_pass"), lambda: self.set_passthrough(True), False),
            ("send", "open_in", t("ann_send"), self.send_to_delta, False),
            ("clear", "delete", t("clear_all"), self.board.clear_all, False),
            ("close", "close", t("close") + " (Esc)", self.close_overlay, False),
        ])
        self.hint = Toast(self)

    def resizeEvent(self, e):
        self.board.setGeometry(self.rect())
        self.board.setSceneRect(0, 0, self.width(), self.height())
        self._place_toolbar()
        super().resizeEvent(e)

    def _place_toolbar(self):
        self.toolbar.place(28)

    # --- aç / kapa
    def toggle(self):
        if not self.isVisible():
            self.open()
        elif self.passthrough:
            self.set_passthrough(False)
        else:
            self.close_overlay()

    def open(self):
        scr = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        self.setScreen(scr)
        self.setGeometry(scr.geometry())
        self.board.resetTransform()
        if state.tool in ("select", "text"):
            state.set_tool("pen")
        self.show()
        self.raise_()
        self.activateWindow()
        self.board.setFocus()
        self._place_toolbar()
        self.board.centerOn(QPointF(self.width() / 2, self.height() / 2))
        self.hint.show_text(t("ann_hint"), 2600, top=24)

    def close_overlay(self):
        self.board.finish_text()
        self.set_passthrough(False, show=False)
        for it in self.page.scene.items():
            self.page.scene.removeItem(it)
        self.page.undo.clear()
        self.board.opaque_bg = False
        self.toolbar.extra_btns["board"].setChecked(False)
        self.hide()

    def _toggle_board(self):
        self.board.opaque_bg = self.toolbar.extra_btns["board"].isChecked()
        self.board.viewport().update()

    def set_passthrough(self, on, show=True):
        """Fare alttaki programa geçer; çizimler ekranda kalır."""
        self.passthrough = on
        try:
            hwnd = int(self.winId())
            ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ex = (ex | WS_EX_TRANSPARENT | WS_EX_LAYERED) if on else (ex & ~WS_EX_TRANSPARENT)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)
        except Exception:
            pass
        self.toolbar.setVisible(not on)
        if on:
            self.hint.show_text(t("ann_pass_hint"), 3200, top=24)
        elif show and self.isVisible():
            self.raise_()
            self.activateWindow()
            self.board.setFocus()

    # --- delta'ya aktar
    def send_to_delta(self):
        self.board.finish_text()
        self.toolbar.hide()
        self.hint.hide()
        drawing = self.board.viewport().grab()
        scr = self.screen()
        self.hide()

        def grab():
            base = scr.grabWindow(0)
            dpr = base.width() / max(1, scr.geometry().width())
            base.setDevicePixelRatio(dpr)
            out = QPixmap(base.size())
            out.setDevicePixelRatio(dpr)
            out.fill(Qt.GlobalColor.black)
            p = QPainter(out)
            p.drawPixmap(0, 0, base)
            if self.board.opaque_bg:
                p.fillRect(out.rect(), Qt.GlobalColor.transparent)
            p.drawPixmap(0, 0, drawing)
            p.end()
            self.toolbar.show()
            self.close_overlay()
            self.export.emit(out)
        QTimer.singleShot(180, grab)
