"""Notlar: her not ayrı bir tuval (sahne + geri al yığını). Otomatik kaydedilir.
%LOCALAPPDATA%\\delta\\notes\\<id>.json (içerik) + <id>.png (küçük resim) + index.json (başlıklar, tarihler)."""
import json
import os
import shutil
import time
import uuid
from datetime import datetime

from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer, QRectF, QSize, QRect
from PyQt6.QtGui import QUndoStack, QPixmap, QPainter, QPainterPath, QFontMetrics, QFont, QImage
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                             QStyledItemDelegate, QStyle, QMenu, QAbstractItemView)

from . import items as I
from . import icons
from .config import NOTES_DIR, TRASH_DIR
from .i18n import t, month_short
from .theme import theme, qcolor, color as tcolor
from .widgets import IconButton

INDEX_FILE = os.path.join(NOTES_DIR, "index.json")
THUMB_W, THUMB_H = 240, 150


def _now():
    return time.time()


def fmt_date(ts):
    d = datetime.fromtimestamp(ts)
    today = datetime.now().date()
    hm = d.strftime("%H:%M")
    if d.date() == today:
        return t("today_at", hm=hm)
    if (today - d.date()).days == 1:
        return t("yesterday_at", hm=hm)
    return f"{d.day} {month_short(d.month)} {d.year if d.year != today.year else ''} {hm}".replace("  ", " ")


class Page(QObject):
    dirty = pyqtSignal(object)

    def __init__(self, pid, meta=None, temp=False):
        super().__init__()
        meta = meta or {}
        self.id = pid
        self.title = meta.get("title", "")
        self.auto = meta.get("auto", "")
        self.created = meta.get("created", _now())
        self.modified = meta.get("modified", self.created)
        self.view = meta.get("view") or {}
        self.temp = temp
        self.scene = None
        self.undo = None
        self.saved_once = bool(meta)

    @property
    def path(self):
        return os.path.join(NOTES_DIR, self.id + ".json")

    @property
    def thumb_path(self):
        return os.path.join(NOTES_DIR, self.id + ".png")

    def display_title(self):
        return self.title or self.auto or t("note_untitled", d=fmt_date(self.created))

    def ensure_loaded(self):
        if self.scene is not None:
            return
        self.scene = I.DeltaScene()
        self.undo = QUndoStack(self)
        self.undo.setUndoLimit(400)
        if not self.temp and os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                zmax = 0
                for d in data.get("items", []):
                    it = I.from_dict(d)
                    if it is not None:
                        self.scene.addItem(it)
                        z = it.zValue()
                        seq = z + 3_000_000 if z < -2_500_000 else z + 2_000_000 if z < -1_500_000 else z
                        zmax = max(zmax, int(seq))
                self.scene.zseq = zmax + 1
            except (OSError, ValueError):
                pass
        self.undo.indexChanged.connect(self._changed)

    def _changed(self, _i):
        self.modified = _now()
        self.dirty.emit(self)

    def is_empty(self):
        return self.scene is None or not self.scene.content_items()

    def meta(self):
        return {"title": self.title, "auto": self.auto, "created": self.created, "modified": self.modified,
                "view": self.view}

    def compute_auto_title(self):
        """İlk yazı kutusunun ilk satırı otomatik başlık olur."""
        texts = [it for it in self.scene.content_items() if isinstance(it, I.TextItem) and it.toPlainText().strip()]
        if not texts:
            self.auto = ""
            return
        texts.sort(key=lambda it: (round(it.pos().y() / 40), it.pos().x()))
        line = texts[0].toPlainText().strip().splitlines()[0].strip()
        self.auto = line[:48] + ("…" if len(line) > 48 else "")


class NoteStore(QObject):
    list_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.pages = {}
        self._dirty = set()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(700)
        self._timer.timeout.connect(self.flush)
        self._load_index()

    def _load_index(self):
        idx = {}
        try:
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                idx = json.load(f)
        except (OSError, ValueError):
            pass
        for fn in os.listdir(NOTES_DIR):
            if fn.endswith(".json") and fn != "index.json":
                pid = fn[:-5]
                meta = idx.get(pid)
                if not isinstance(meta, dict):
                    st = os.stat(os.path.join(NOTES_DIR, fn))
                    meta = {"created": st.st_ctime, "modified": st.st_mtime}
                self._add(Page(pid, meta))

    def _add(self, page):
        self.pages[page.id] = page
        page.dirty.connect(self.mark_dirty)

    def sorted(self):
        return sorted(self.pages.values(), key=lambda p: p.modified, reverse=True)

    def get(self, pid):
        return self.pages.get(pid)

    def create(self):
        pid = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        p = Page(pid)
        p.saved_once = False
        self._add(p)
        self.list_changed.emit()
        return p

    def mark_dirty(self, page):
        self._dirty.add(page.id)
        self._timer.start()

    def flush(self):
        changed = False
        for pid in list(self._dirty):
            p = self.pages.get(pid)
            if p is not None:
                self.save(p)
                changed = True
        self._dirty.clear()
        if changed:
            self.write_index()
            self.list_changed.emit()

    def save(self, p):
        if p.scene is None:
            return
        items = p.scene.content_items()
        if not items and not p.saved_once:
            return
        p.compute_auto_title()
        data = {"version": 1, "items": [I.to_dict(it) for it in sorted(items, key=lambda i: i.zValue())]}
        tmp = p.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp, p.path)
            p.saved_once = True
        except OSError:
            return
        self.save_thumb(p)

    def save_thumb(self, p):
        from .canvas import render_scene
        img = render_scene(p.scene, fit=(THUMB_W, THUMB_H), margin=30) if not p.is_empty() else None
        if img is None:
            img = QImage(THUMB_W, THUMB_H, QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(qcolor("bg"))
        img.save(p.thumb_path, "PNG")
        _thumb_cache.pop(p.id, None)

    def write_index(self):
        idx = {pid: p.meta() for pid, p in self.pages.items() if p.saved_once}
        tmp = INDEX_FILE + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(idx, f, ensure_ascii=False, indent=1)
            os.replace(tmp, INDEX_FILE)
        except OSError:
            pass

    def rename(self, p, title):
        p.title = title.strip()
        if p.saved_once:
            self.write_index()
        self.list_changed.emit()

    def delete(self, p):
        """Not çöpe taşınır (%LOCALAPPDATA%\\delta\\trash) — kalıcı silinmez."""
        for src in (p.path, p.thumb_path):
            if os.path.exists(src):
                try:
                    shutil.move(src, os.path.join(TRASH_DIR, os.path.basename(src)))
                except OSError:
                    pass
        self.pages.pop(p.id, None)
        self._dirty.discard(p.id)
        self.write_index()
        self.list_changed.emit()

    def discard_if_empty(self, p):
        """Hiç kaydedilmemiş boş not listeden düşer."""
        if p is not None and not p.saved_once and p.is_empty() and p.id in self.pages:
            self.pages.pop(p.id, None)
            self.list_changed.emit()
            return True
        return False

    def restyle_all(self):
        for p in self.pages.values():
            if p.scene is not None:
                p.scene.restyle()


_thumb_cache = {}


def thumb_pixmap(p):
    pm = _thumb_cache.get(p.id)
    if pm is None:
        pm = QPixmap(p.thumb_path) if os.path.exists(p.thumb_path) else QPixmap()
        _thumb_cache[p.id] = pm
    return pm


# ---------------------------------------------------------------- yan panel

class NoteDelegate(QStyledItemDelegate):
    H = 74

    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel

    def sizeHint(self, opt, idx):
        return QSize(200, self.H)

    def paint(self, p, opt, idx):
        page = self.panel.store.get(idx.data(Qt.ItemDataRole.UserRole))
        if page is None:
            return
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(opt.rect).adjusted(6, 2, -6, -2)
        sel = bool(opt.state & QStyle.StateFlag.State_Selected)
        hov = bool(opt.state & QStyle.StateFlag.State_MouseOver)
        if sel or hov:
            path = QPainterPath()
            path.addRoundedRect(r, 10, 10)
            p.fillPath(path, qcolor("selected" if sel else "hover"))
        tr = QRectF(r.left() + 6, r.top() + 6, 96, r.height() - 12)
        clip = QPainterPath()
        clip.addRoundedRect(tr, 6, 6)
        p.fillPath(clip, qcolor("surface"))
        pm = thumb_pixmap(page)
        if not pm.isNull():
            p.setClipPath(clip)
            s = pm.size().scaled(tr.size().toSize(), Qt.AspectRatioMode.KeepAspectRatioByExpanding)
            x = tr.left() + (tr.width() - s.width()) / 2
            y = tr.top() + (tr.height() - s.height()) / 2
            p.drawPixmap(QRect(int(x), int(y), s.width(), s.height()), pm)
            p.setClipping(False)
        tx = tr.right() + 10
        tw = r.right() - tx - 6
        f = QFont(opt.font)
        f.setPixelSize(13)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(qcolor("text"))
        fm = QFontMetrics(f)
        title = fm.elidedText(page.display_title(), Qt.TextElideMode.ElideRight, int(tw))
        p.drawText(QRectF(tx, r.top() + 14, tw, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)
        f2 = QFont(opt.font)
        f2.setPixelSize(12)
        p.setFont(f2)
        p.setPen(qcolor("text2"))
        p.drawText(QRectF(tx, r.top() + 36, tw, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   fmt_date(page.modified))
        p.restore()


class NotesPanel(QWidget):
    open_page = pyqtSignal(object)
    new_page = pyqtSignal()
    rename_page = pyqtSignal(object)
    delete_page = pyqtSignal(object)
    export_page = pyqtSignal(object)
    export_all = pyqtSignal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setObjectName("NotesPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(284)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 8)
        lay.setSpacing(4)
        head = QHBoxLayout()
        head.setContentsMargins(10, 0, 4, 0)
        lbl = QLabel(t("notes"))
        lbl.setObjectName("SectionTitle")
        head.addWidget(lbl)
        head.addStretch(1)
        b = IconButton("add", t("new_note") + " (Ctrl+N)", 36, 22)
        b.clicked.connect(self.new_page.emit)
        head.addWidget(b)
        lay.addLayout(head)
        self.list = QListWidget(self)
        self.list.setObjectName("NotesList")
        self.list.setItemDelegate(NoteDelegate(self))
        self.list.setMouseTracking(True)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self.list.itemClicked.connect(self._clicked)
        self.list.itemDoubleClicked.connect(lambda it: self._emit(it, self.rename_page))
        lay.addWidget(self.list, 1)
        self._current = None
        store.list_changed.connect(self.refresh)
        theme.changed.connect(lambda _: self.list.viewport().update())

    def _emit(self, it, sig):
        p = self.store.get(it.data(Qt.ItemDataRole.UserRole))
        if p is not None:
            sig.emit(p)

    def _clicked(self, it):
        self._emit(it, self.open_page)

    def set_current(self, pid):
        self._current = pid
        self.refresh()

    def refresh(self):
        self.list.blockSignals(True)
        self.list.clear()
        pages = [p for p in self.store.sorted() if p.saved_once or p.id == self._current]
        for p in pages:
            it = QListWidgetItem()
            it.setData(Qt.ItemDataRole.UserRole, p.id)
            it.setToolTip(p.display_title())
            self.list.addItem(it)
            if p.id == self._current:
                it.setSelected(True)
                self.list.setCurrentItem(it)
        self.list.blockSignals(False)

    def _menu(self, pos):
        it = self.list.itemAt(pos)
        if it is None:
            return
        p = self.store.get(it.data(Qt.ItemDataRole.UserRole))
        if p is None:
            return
        col = tcolor("text")
        m = QMenu(self)
        m.addAction(icons.icon("open_in", col, 18), t("open"), lambda: self.open_page.emit(p))
        m.addAction(icons.icon("edit", col, 18), t("rename"), lambda: self.rename_page.emit(p))
        m.addAction(icons.icon("download", col, 18), t("export_as"), lambda: self.export_page.emit(p))
        m.addAction(icons.icon("download", col, 18), t("export_all_pdf"), self.export_all.emit)
        m.addSeparator()
        m.addAction(icons.icon("delete", col, 18), t("delete_note"), lambda: self.delete_page.emit(p))
        m.exec(self.list.viewport().mapToGlobal(pos))
