"""Katmanlar paneli (sağdaki panelin ikinci sekmesi): nottaki her nesne küçük resmiyle, en öndeki en üstte.
Sürükleyerek sırala, tıklayınca tahtada seçilir, göz simgesi gizler, kilit simgesi kilitler."""
from PyQt6.QtCore import Qt, QTimer, QPointF, pyqtSignal
from PyQt6.QtGui import QPixmap, QPainter, QGuiApplication
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                             QAbstractItemView, QMenu, QStyleOptionGraphicsItem)

from . import items as I
from .i18n import t
from .theme import theme, color as tcolor
from .widgets import IconButton

THUMB_W, THUMB_H = 44, 32


def thumbnail(it, w=THUMB_W, h=THUMB_H):
    """Nesnenin kendi çizimiyle küçük resim (diğer nesneler karışmaz)."""
    app = QGuiApplication.instance()
    dpr = app.devicePixelRatio() if app else 1.0
    pm = QPixmap(int(w * dpr), int(h * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    br = it.boundingRect()
    if br.width() <= 0 or br.height() <= 0:
        return pm
    k = min((w - 4) / br.width(), (h - 4) / br.height())
    p = QPainter(pm)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform |
                     QPainter.RenderHint.TextAntialiasing)
    p.translate(QPointF(w / 2, h / 2))
    p.scale(k, k)
    p.translate(-br.center())
    try:
        it.paint(p, QStyleOptionGraphicsItem(), None)
    finally:
        p.end()
    return pm


def item_name(it):
    if isinstance(it, I.ImageItem):
        n = f"{t('layer_image')} {it.pixmap().width()}×{it.pixmap().height()}"
    elif isinstance(it, I.TableItem):
        n = t("layer_table", r=it.rows, c=it.cols)
    elif isinstance(it, I.TextItem):
        txt = " ".join(it.toPlainText().split())
        n = (txt[:26] + "…") if len(txt) > 27 else (txt or t("layer_text"))
    else:
        n = t("tool_" + it.kind)
    if I.group_of(it):
        n += f" · {t('in_group')}"
    return n


class LayerList(QListWidget):
    reordered = pyqtSignal()

    def dropEvent(self, e):
        super().dropEvent(e)
        QTimer.singleShot(0, self.reordered.emit)


class LayerRow(QWidget):
    def __init__(self, panel, it):
        super().__init__()
        self.it = it
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 2, 4, 2)
        lay.setSpacing(8)
        th = QLabel()
        th.setFixedSize(THUMB_W, THUMB_H)
        th.setPixmap(thumbnail(it))
        th.setObjectName("LayerThumb")
        lay.addWidget(th)
        name = QLabel(item_name(it))
        name.setObjectName("LayerName" if it.isVisible() else "LayerNameDim")
        lay.addWidget(name, 1)
        hidden, locked = not it.isVisible(), I.is_locked(it)
        # açık göz / açık kilit soluk durur; gizli / kilitli olan belirgin
        eye = IconButton("eye_off" if hidden else "eye", t("layer_show") if hidden else t("layer_hide"), 28, 16,
                         role="text" if hidden else "text3")
        eye.clicked.connect(lambda: panel.board.set_hidden([it], not hidden))
        lock = IconButton("lock" if locked else "lock_open", t("layer_unlock") if locked else t("layer_lock"), 28, 16,
                          role="text" if locked else "text3")
        lock.clicked.connect(lambda: panel.board.set_locked([it], not locked))
        for b in (eye, lock):
            lay.addWidget(b)


class LayersPanel(QWidget):
    def __init__(self, board, parent=None):
        super().__init__(parent)
        self.board = board
        self._items = []
        self._syncing = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        hint = QLabel(t("layers_hint"))
        hint.setObjectName("Secondary")
        hint.setContentsMargins(10, 0, 0, 2)
        lay.addWidget(hint)
        self.list = LayerList(self)
        self.list.setObjectName("LayersList")
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self.list.itemSelectionChanged.connect(self._list_selection)
        self.list.reordered.connect(self._reordered)
        lay.addWidget(self.list, 1)
        self.empty = QLabel(t("layers_empty"))
        self.empty.setObjectName("EmptyHint")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.empty, 1)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self.refresh)
        board.content_changed.connect(self.schedule)
        board.selection_changed.connect(self._board_selection)
        theme.changed.connect(lambda _: self.schedule())

    def schedule(self):
        if self.isVisible():
            self._timer.start()

    def showEvent(self, e):
        super().showEvent(e)
        self.refresh()

    def refresh(self):
        sc = self.board.scene()
        items = list(reversed(self.board.layer_order())) if sc else []   # en öndeki en üstte
        self._items = items
        self.list.blockSignals(True)
        self.list.clear()
        for i, it in enumerate(items):
            row = QListWidgetItem()
            row.setData(Qt.ItemDataRole.UserRole, i)
            w = LayerRow(self, it)
            row.setSizeHint(w.sizeHint().expandedTo(w.minimumSizeHint()))
            self.list.addItem(row)
            self.list.setItemWidget(row, w)
            if it.isSelected():
                row.setSelected(True)
        self.list.blockSignals(False)
        self.empty.setVisible(not items)
        self.list.setVisible(bool(items))

    def _board_selection(self):
        if self._syncing or not self.isVisible():
            return
        self.list.blockSignals(True)
        for r in range(self.list.count()):
            row = self.list.item(r)
            i = row.data(Qt.ItemDataRole.UserRole)
            row.setSelected(0 <= i < len(self._items) and self._items[i].isSelected())
        self.list.blockSignals(False)

    def _list_selection(self):
        sc = self.board.scene()
        if sc is None:
            return
        self._syncing = True
        try:
            sc.clearSelection()
            for row in self.list.selectedItems():
                i = row.data(Qt.ItemDataRole.UserRole)
                if 0 <= i < len(self._items) and self._items[i].isVisible():
                    self._items[i].setSelected(True)
        finally:
            self._syncing = False
        self.board._on_scene_selection()

    def _reordered(self):
        order = []
        for r in range(self.list.count()):
            i = self.list.item(r).data(Qt.ItemDataRole.UserRole)
            if 0 <= i < len(self._items):
                order.append(self._items[i])
        if len(order) == len(self._items):
            self.board.set_layer_order(list(reversed(order)))   # listede üstteki öndedir
        self.refresh()

    def _menu(self, pos):
        row = self.list.itemAt(pos)
        if row is None:
            return
        i = row.data(Qt.ItemDataRole.UserRole)
        if not 0 <= i < len(self._items):
            return
        it = self._items[i]
        col = tcolor("text")
        from . import icons
        m = QMenu(self)
        self.board.build_layer_menu(m, [it])
        m.addSeparator()
        hidden, locked = not it.isVisible(), I.is_locked(it)
        m.addAction(icons.icon("eye" if hidden else "eye_off", col, 18), t("layer_show") if hidden else t("layer_hide"),
                    lambda: self.board.set_hidden([it], not hidden))
        m.addAction(icons.icon("lock_open" if locked else "lock", col, 18),
                    t("layer_unlock") if locked else t("layer_lock"),
                    lambda: self.board.set_locked([it], not locked))
        m.addAction(icons.icon("delete", col, 18), t("delete_this"), lambda: self.board.delete_item(it))
        m.exec(self.list.viewport().mapToGlobal(pos))
