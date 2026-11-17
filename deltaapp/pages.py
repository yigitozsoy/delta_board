"""Notlar: her not ayrı bir tuval (sahne + geri al yığını). Otomatik kaydedilir.

Her not tek bir .delta dosyasıdır (Photoshop'taki .psd gibi): çizimler, yazılar, görseller, katmanlar içinde;
çift tıklayınca delta'da düzenlenebilir açılır. Yer: notes_root() — varsayılan Resimler\\delta.
Klasörler gerçek alt klasörlerdir (tek düzey): Resimler\\delta\\İş\\Toplantı.delta.
Dosya adı notun başlığından gelir; başlık değişince dosya da yeniden adlandırılır.
Önbellekler %LOCALAPPDATA%\\delta altında: küçük resimler (thumbs\\<id>.png), dosya özetleri (notes_cache.json).
Eski sürümün notları (%LOCALAPPDATA%\\delta\\notes\\*.json) ilk açılışta bir kez .delta'ya taşınır, eskiler yedek kalır."""
import json
import os
import shutil
import time
import uuid
from datetime import datetime

from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer, QRectF, QSize, QRect
from PyQt6.QtGui import QUndoStack, QPixmap, QPainter, QPainterPath, QFontMetrics, QFont, QImage
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QLineEdit,
                             QStyledItemDelegate, QStyle, QMenu, QAbstractItemView, QStackedWidget, QPushButton)

from . import items as I
from . import icons
from .config import NOTES_DIR, TRASH_DIR, DATA_DIR, prefs, notes_root
from .i18n import t, month_short
from .theme import theme, qcolor, color as tcolor
from .widgets import IconButton

EXT = ".delta"
FORMAT = "delta-note"
THUMBS_DIR = os.path.join(DATA_DIR, "thumbs")
CACHE_FILE = os.path.join(DATA_DIR, "notes_cache.json")
LEGACY_INDEX = os.path.join(NOTES_DIR, "index.json")
LEGACY_FOLDERS = os.path.join(NOTES_DIR, "folders.json")
ROLE_KIND = Qt.ItemDataRole.UserRole + 1      # "folder" | "note"
ROLE_INDENT = Qt.ItemDataRole.UserRole + 2    # klasör içindeki not: 1
THUMB_W, THUMB_H = 240, 150
os.makedirs(THUMBS_DIR, exist_ok=True)


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


def safe_name(name):
    """Windows dosya / klasör adına uygun hale getirir (":" → ".", yasak karakterler → "_")."""
    s = name.replace(":", ".")
    s = "".join("_" if c in '<>"/\\|?*' or ord(c) < 32 else c for c in s)
    s = " ".join(s.split()).strip().rstrip(".")
    if s.upper().split(".")[0] in ("CON", "PRN", "AUX", "NUL") or s.upper()[:3] in ("COM", "LPT") and s[3:4].isdigit():
        s = "_" + s
    return s[:80].strip() or "delta"


def unique_path(folder, base, ext, keep=None):
    """folder\\base.ext boşsa onu, doluysa "base (2).ext" … döner; keep: zaten bu notun olan yol."""
    cand = os.path.join(folder, base + ext)
    n = 2
    while os.path.exists(cand) and not (keep and os.path.normcase(cand) == os.path.normcase(keep)):
        cand = os.path.join(folder, f"{base} ({n}){ext}")
        n += 1
    return cand


def _norm(p):
    return os.path.normcase(os.path.abspath(p))


def read_note_file(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("items", []), list):
        raise ValueError("delta notu değil")
    return data


def write_json_atomic(path, data, **kw):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, **kw)
    os.replace(tmp, path)


class Page(QObject):
    dirty = pyqtSignal(object)

    def __init__(self, pid, meta=None, temp=False, file=None, folder=""):
        super().__init__()
        meta = meta or {}
        self.id = pid
        self.title = meta.get("title", "")
        self.auto = meta.get("auto", "")
        self.created = meta.get("created", _now())
        self.modified = meta.get("modified", self.created)
        self.view = meta.get("view") or {}
        self.folder = folder            # notes_root altındaki klasör adı ("" = kökte)
        self.file = file                # .delta dosyasının yolu (henüz kaydedilmediyse None)
        self.external = False           # notes_root dışında bir .delta (çift tıkla açılmış)
        self.temp = temp
        self.scene = None
        self.undo = None
        self.saved_once = file is not None

    @property
    def path(self):
        return self.file

    @property
    def thumb_path(self):
        return os.path.join(THUMBS_DIR, self.id + ".png")

    def display_title(self):
        if self.external and not self.title and self.file:      # dışarıdaki dosya: kendi adıyla görünür
            return os.path.splitext(os.path.basename(self.file))[0]
        return self.title or self.auto or t("note_untitled", d=fmt_date(self.created))

    def ensure_loaded(self):
        if self.scene is not None:
            return
        self.scene = I.DeltaScene()
        self.undo = QUndoStack(self)
        self.undo.setUndoLimit(400)
        if not self.temp and self.file and os.path.exists(self.file):
            try:
                data = read_note_file(self.file)
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
    error = pyqtSignal(str)

    def __init__(self, root=None):
        super().__init__()
        self.root = root or notes_root()
        os.makedirs(self.root, exist_ok=True)
        self.pages = {}
        self.folders = []          # [{"id": klasör adı, "name": klasör adı, "open"}] — alfabetik
        self._dirty = set()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(700)
        self._timer.timeout.connect(self.flush)
        self._cache = self._load_cache()
        self.migrate_legacy()
        self.scan()

    # ------------------------------------------------------------ tarama / önbellek
    def _load_cache(self):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                c = json.load(f)
            return c if isinstance(c, dict) else {}
        except (OSError, ValueError):
            return {}

    def write_index(self):
        """Dosya özetleri önbelleği: açılışta her .delta'yı baştan okumamak için (yol → boyut, tarih, özet)."""
        c = {}
        for p in self.pages.values():
            if p.file and os.path.exists(p.file):
                st = os.stat(p.file)
                c[_norm(p.file)] = {"size": st.st_size, "mtime": st.st_mtime, "id": p.id, "meta": p.meta()}
        self._cache = c
        try:
            write_json_atomic(CACHE_FILE, c)
        except OSError:
            pass

    def _meta_of(self, path):
        """(id, meta) — önbellekten ya da dosyadan."""
        st = os.stat(path)
        c = self._cache.get(_norm(path))
        if c and c.get("size") == st.st_size and abs(c.get("mtime", 0) - st.st_mtime) < 1e-3:
            return c.get("id"), c.get("meta") or {}
        data = read_note_file(path)
        meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
        if "created" not in meta:
            meta = dict(meta, created=st.st_ctime, modified=st.st_mtime)
        return data.get("id"), meta

    def _load_file(self, path, folder, external=False):
        try:
            pid, meta = self._meta_of(path)
        except (OSError, ValueError):
            return None
        known = self.page_for_file(path)
        if known is not None:
            return known
        if not pid or pid in self.pages:      # kopyalanmış dosya: aynı kimlik → yenisini ver
            pid = self.new_id()
        p = Page(str(pid), meta, file=path, folder=folder)
        p.external = external
        self._add(p)
        return p

    def scan(self):
        """notes_root içindeki .delta dosyalarını ve tek düzey alt klasörleri okur."""
        states = prefs.get("folder_open", {}) or {}
        folders = []
        try:
            entries = sorted(os.scandir(self.root), key=lambda e: e.name.casefold())
        except OSError:
            entries = []
        for e in entries:
            if e.is_dir() and not e.name.startswith("."):
                folders.append({"id": e.name, "name": e.name, "open": bool(states.get(e.name, True))})
                try:
                    for f in os.scandir(e.path):
                        if f.is_file() and f.name.lower().endswith(EXT):
                            self._load_file(f.path, e.name)
                except OSError:
                    pass
            elif e.is_file() and e.name.lower().endswith(EXT):
                self._load_file(e.path, "")
        self.folders = folders
        for path in list(prefs.get("external_notes", []) or []):
            if os.path.isfile(path) and not self._inside_root(path):
                self._load_file(path, "", external=True)

    def _inside_root(self, path):
        r = _norm(self.root)
        d = os.path.dirname(_norm(path))
        return d == r or os.path.dirname(d) == r

    def page_for_file(self, path):
        n = _norm(path)
        return next((p for p in self.pages.values() if p.file and _norm(p.file) == n), None)

    def open_file(self, path):
        """Çift tıklanan .delta: notes_root içindeyse o not, dışındaysa yerinde açılır (kaydedince oraya yazar)."""
        if not path or not os.path.isfile(path):
            return None
        p = self.page_for_file(path)
        if p is not None:
            return p
        if self._inside_root(path):
            d = os.path.dirname(_norm(path))
            folder = "" if d == _norm(self.root) else os.path.basename(os.path.dirname(path))
            if folder and self.folder(folder) is None:
                self.scan()
            p = self._load_file(path, folder)
        else:
            p = self._load_file(path, "", external=True)
            if p is not None:
                ext = [x for x in (prefs.get("external_notes", []) or []) if _norm(x) != _norm(path)]
                prefs.set("external_notes", ext + [path])
        if p is not None:
            self.list_changed.emit()
        return p

    # ------------------------------------------------------------ eski sürümden taşıma
    def migrate_legacy(self):
        """1.2 ve öncesinin notları (%LOCALAPPDATA%\\delta\\notes\\<id>.json) .delta'ya çevrilir.
        Her not bir kez taşınır (prefs "migrated_ids"): eski sürüm arada yine kullanılırsa yeni notları da gelir.
        Eski dosyalar silinmez (yedek)."""
        done = set(prefs.get("migrated_ids", []) or [])
        try:
            olds = [f for f in os.listdir(NOTES_DIR) if f.endswith(".json") and f not in ("index.json", "folders.json")
                    and f[:-5] not in done]
        except OSError:
            olds = []
        if not olds:
            return
        try:
            with open(LEGACY_INDEX, "r", encoding="utf-8") as f:
                idx = json.load(f)
        except (OSError, ValueError):
            idx = {}
        try:
            with open(LEGACY_FOLDERS, "r", encoding="utf-8") as f:
                fnames = {d["id"]: d.get("name") for d in json.load(f) if isinstance(d, dict) and d.get("id")}
        except (OSError, ValueError, TypeError, KeyError):
            fnames = {}

        for fn in olds:
            pid = fn[:-5]
            src = os.path.join(NOTES_DIR, fn)
            try:
                data = read_note_file(src)
            except (OSError, ValueError):
                continue
            meta = idx.get(pid) if isinstance(idx.get(pid), dict) else {}
            if not meta:
                st = os.stat(src)
                meta = {"created": st.st_ctime, "modified": st.st_mtime}
            folder = safe_name(fnames.get(meta.get("folder"), "") or "") if meta.get("folder") in fnames else ""
            d = os.path.join(self.root, folder) if folder else self.root
            os.makedirs(d, exist_ok=True)
            pg = Page(pid, meta)
            title = pg.display_title()
            dst = unique_path(d, safe_name(title), EXT)
            out = {"format": FORMAT, "version": 2, "id": pid,
                   "meta": {k: v for k, v in meta.items() if k != "folder"}, "items": data.get("items", [])}
            try:
                write_json_atomic(dst, out, separators=(",", ":"))
                old_thumb = os.path.join(NOTES_DIR, pid + ".png")
                if os.path.exists(old_thumb):
                    shutil.copy2(old_thumb, os.path.join(THUMBS_DIR, pid + ".png"))
                done.add(pid)
            except OSError:
                continue
        prefs.set("migrated_ids", sorted(done))

    def _add(self, page):
        self.pages[page.id] = page
        page.dirty.connect(self.mark_dirty)

    @staticmethod
    def new_id():
        return datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]

    def sorted(self):
        return sorted(self.pages.values(), key=lambda p: p.modified, reverse=True)

    def get(self, pid):
        return self.pages.get(pid)

    # ------------------------------------------------------------ klasörler (gerçek alt klasörler)
    def folder(self, fid):
        return next((f for f in self.folders if f["id"] == fid), None)

    def _folder_dir(self, fid):
        return os.path.join(self.root, fid) if fid else self.root

    def _save_folder_states(self):
        prefs.set("folder_open", {f["id"]: f["open"] for f in self.folders})

    def _sort_folders(self):
        self.folders.sort(key=lambda f: f["name"].casefold())

    def create_folder(self, name):
        base = safe_name(name.strip() or t("new_folder"))
        path = unique_path(self.root, base, "")
        try:
            os.makedirs(path)
        except OSError as e:
            self.error.emit(str(e))
            return ""
        fid = os.path.basename(path)
        self.folders.append({"id": fid, "name": fid, "open": True})
        self._sort_folders()
        self._save_folder_states()
        self.list_changed.emit()
        return fid

    def rename_folder(self, fid, name):
        f = self.folder(fid)
        new = safe_name(name.strip()) if name.strip() else ""
        if f is None or not new or new == fid:
            return fid
        dst = unique_path(self.root, new, "")
        self.flush()
        try:
            os.rename(self._folder_dir(fid), dst)
        except OSError as e:
            self.error.emit(str(e))
            return fid
        nid = os.path.basename(dst)
        for p in self.pages.values():
            if p.folder == fid:
                p.folder = nid
                if p.file:
                    p.file = os.path.join(dst, os.path.basename(p.file))
        f["id"] = f["name"] = nid
        self._sort_folders()
        self._save_folder_states()
        self.write_index()
        self.list_changed.emit()
        return nid

    def set_folder_open(self, fid, on):
        f = self.folder(fid)
        if f is not None and f["open"] != bool(on):
            f["open"] = bool(on)
            self._save_folder_states()
            self.list_changed.emit()

    def delete_folder(self, fid):
        """Klasör silinir; içindeki notlar silinmez, ana klasöre taşınır. Klasörde başka dosya varsa diskte kalır."""
        if self.folder(fid) is None:
            return
        for p in list(self.pages.values()):
            if p.folder == fid:
                self.move_to_folder(p, "", emit=False)
        try:
            os.rmdir(self._folder_dir(fid))
            self.folders = [f for f in self.folders if f["id"] != fid]
        except OSError:
            self.error.emit(t("folder_not_empty"))
        self._save_folder_states()
        self.write_index()
        self.list_changed.emit()

    def move_to_folder(self, p, fid, emit=True):
        fid = fid if self.folder(fid) is not None else ""
        if p.folder == fid and not p.external:
            return
        if p.file and os.path.exists(p.file):
            self.flush()
            dst = unique_path(self._folder_dir(fid), os.path.splitext(os.path.basename(p.file))[0], EXT)
            try:
                shutil.move(p.file, dst)
            except OSError as e:
                self.error.emit(str(e))
                return
            if p.external:
                p.external = False
                prefs.set("external_notes", [x for x in (prefs.get("external_notes", []) or [])
                                             if _norm(x) != _norm(p.file)])
            p.file = dst
        p.folder = fid
        if emit:
            self.write_index()
            self.list_changed.emit()

    def folder_pages(self, fid):
        return [p for p in self.sorted() if p.folder == fid and p.saved_once]

    def open_root_in_explorer(self):
        import subprocess
        try:
            subprocess.Popen(["explorer", os.path.normpath(self.root)])
        except OSError:
            pass

    # ------------------------------------------------------------ notlar
    def create(self, folder=""):
        p = Page(self.new_id(), folder=folder if self.folder(folder) is not None else "")
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

    def _target_path(self, p):
        """Başlığa göre dosya yolu (başlık değiştiyse yeni ad; aynı adda başka dosya varsa "(2)")."""
        if p.external and p.file:
            return p.file           # dışarıdan açılan dosyanın adına / yerine dokunulmaz
        d = os.path.dirname(p.file) if p.file else self._folder_dir(p.folder)
        os.makedirs(d, exist_ok=True)
        base = safe_name(p.display_title())
        if p.file and os.path.splitext(os.path.basename(p.file))[0] == base:
            return p.file
        if p.file:
            cur = os.path.splitext(os.path.basename(p.file))[0]
            # "Başlık (2)" gibi zaten benzersizleştirilmiş adı koru
            if cur.startswith(base + " (") and cur.endswith(")"):
                return p.file
        return unique_path(d, base, EXT, keep=p.file)

    def save(self, p):
        if p.scene is None:
            return
        items = p.scene.content_items()
        if not items and not p.saved_once:
            return
        p.compute_auto_title()
        data = {"format": FORMAT, "version": 2, "id": p.id, "meta": p.meta(),
                "items": [I.to_dict(it) for it in sorted(items, key=lambda i: i.zValue())]}
        dst = self._target_path(p)
        try:
            write_json_atomic(dst, data, separators=(",", ":"))
        except OSError as e:
            self.error.emit(str(e))
            return
        if p.file and _norm(p.file) != _norm(dst) and os.path.exists(p.file):
            try:
                os.remove(p.file)          # başlık değişti: eski adlı dosya kalkar
            except OSError:
                pass
            if p.external:
                prefs.set("external_notes", [x for x in (prefs.get("external_notes", []) or [])
                                             if _norm(x) != _norm(p.file)] + [dst])
        p.file = dst
        p.saved_once = True
        self.save_thumb(p)

    def save_thumb(self, p):
        from .canvas import render_scene
        img = render_scene(p.scene, fit=(THUMB_W, THUMB_H), margin=30) if not p.is_empty() else None
        if img is None:
            img = QImage(THUMB_W, THUMB_H, QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(qcolor("bg"))
        img.save(p.thumb_path, "PNG")
        _thumb_cache.pop(p.id, None)

    def rename(self, p, title):
        p.title = title.strip()
        if p.saved_once:
            self.mark_dirty(p)
            self.flush()        # dosya adı da başlıkla değişsin
        self.list_changed.emit()

    def delete(self, p):
        """Not çöpe taşınır (%LOCALAPPDATA%\\delta\\trash) — kalıcı silinmez."""
        if p.file and os.path.exists(p.file):
            try:
                shutil.move(p.file, unique_path(TRASH_DIR, os.path.splitext(os.path.basename(p.file))[0], EXT))
            except OSError:
                pass
        if p.external:
            prefs.set("external_notes", [x for x in (prefs.get("external_notes", []) or [])
                                         if not p.file or _norm(x) != _norm(p.file)])
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


def _reveal(path):
    """Gezgin'de dosyayı seçili gösterir."""
    import subprocess
    try:
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    except OSError:
        pass


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
    FH = 40          # klasör satırı
    INDENT = 16

    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel

    def sizeHint(self, opt, idx):
        return QSize(200, self.FH if idx.data(ROLE_KIND) == "folder" else self.H)

    # --- klasör adı satır içinde düzenlenir
    def createEditor(self, parent, opt, idx):
        if idx.data(ROLE_KIND) != "folder":
            return None
        ed = QLineEdit(parent)
        ed.setObjectName("FolderEdit")
        return ed

    def setEditorData(self, ed, idx):
        f = self.panel.store.folder(idx.data(Qt.ItemDataRole.UserRole))
        ed.setText(f["name"] if f else "")
        ed.selectAll()

    def setModelData(self, ed, model, idx):
        fid, name = idx.data(Qt.ItemDataRole.UserRole), ed.text()
        # liste düzenleyici kapandıktan sonra yenilensin
        QTimer.singleShot(0, lambda: self.panel.store.rename_folder(fid, name))

    def updateEditorGeometry(self, ed, opt, idx):
        ed.setGeometry(opt.rect.adjusted(52, 6, -44, -6))

    def _paint_folder(self, p, opt, idx):
        f = self.panel.store.folder(idx.data(Qt.ItemDataRole.UserRole))
        if f is None:
            return
        r = QRectF(opt.rect).adjusted(6, 2, -6, -2)
        hov = bool(opt.state & QStyle.StateFlag.State_MouseOver)
        drop = self.panel.list.drop_row == idx.row()
        if hov or drop:
            path = QPainterPath()
            path.addRoundedRect(r, 9, 9)
            p.fillPath(path, qcolor("selected" if drop else "hover"))
        # açık / kapalı oku
        cx, cy = r.left() + 14, r.center().y()
        arrow = QPainterPath()
        if f["open"]:
            arrow.moveTo(cx - 4, cy - 2)
            arrow.lineTo(cx, cy + 2.5)
            arrow.lineTo(cx + 4, cy - 2)
        else:
            arrow.moveTo(cx - 2, cy - 4)
            arrow.lineTo(cx + 2.5, cy)
            arrow.lineTo(cx - 2, cy + 4)
        pen = p.pen()
        pen.setColor(qcolor("text2"))
        pen.setWidthF(1.6)
        p.setPen(pen)
        p.drawPath(arrow)
        p.drawPixmap(QRect(int(r.left() + 26), int(cy - 10), 20, 20),
                     icons.pixmap("folder_open" if f["open"] else "folder", tcolor("text2"), 20))
        f1 = QFont(opt.font)
        f1.setPixelSize(13)
        f1.setWeight(QFont.Weight.DemiBold)
        p.setFont(f1)
        p.setPen(qcolor("text"))
        fm = QFontMetrics(f1)
        tw = r.width() - 52 - 40
        p.drawText(QRectF(r.left() + 54, r.top(), tw, r.height()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(f["name"], Qt.TextElideMode.ElideRight, int(tw)))
        f2 = QFont(opt.font)
        f2.setPixelSize(12)
        p.setFont(f2)
        p.setPen(qcolor("text3"))
        p.drawText(QRectF(r.right() - 40, r.top(), 32, r.height()),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(idx.data(ROLE_INDENT + 1) or 0))

    def paint(self, p, opt, idx):
        if idx.data(ROLE_KIND) == "folder":
            p.save()
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._paint_folder(p, opt, idx)
            p.restore()
            return
        page = self.panel.store.get(idx.data(Qt.ItemDataRole.UserRole))
        if page is None:
            return
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(opt.rect).adjusted(6 + (self.INDENT if idx.data(ROLE_INDENT) else 0), 2, -6, -2)
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


class NotesList(QListWidget):
    """Not satırları sürüklenip bir klasörün üstüne (ya da boşluğa: klasörsüz) bırakılır."""
    moved = pyqtSignal(str, str)     # not id, klasör id ("" = klasörsüz)

    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel
        self.drop_row = -1
        self._drag_pid = None
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

    def startDrag(self, actions):
        it = self.currentItem()
        if it is None or it.data(ROLE_KIND) != "note":
            return
        self._drag_pid = it.data(Qt.ItemDataRole.UserRole)
        super().startDrag(actions)
        self._drag_pid = None
        self._set_drop(-1)

    def target_folder(self, pos):
        it = self.itemAt(pos)
        if it is None:
            return ""
        if it.data(ROLE_KIND) == "folder":
            return it.data(Qt.ItemDataRole.UserRole)
        p = self.panel.store.get(it.data(Qt.ItemDataRole.UserRole))
        return p.folder if p is not None else ""

    def _set_drop(self, row):
        if row != self.drop_row:
            self.drop_row = row
            self.viewport().update()

    def dragEnterEvent(self, e):
        if e.source() is self:
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if e.source() is not self:
            e.ignore()
            return
        it = self.itemAt(e.position().toPoint())
        self._set_drop(self.row(it) if it is not None and it.data(ROLE_KIND) == "folder" else -1)
        e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self._set_drop(-1)
        super().dragLeaveEvent(e)

    def dropEvent(self, e):
        pid = self._drag_pid
        fid = self.target_folder(e.position().toPoint())
        self._set_drop(-1)
        e.setDropAction(Qt.DropAction.CopyAction)      # Qt kaynak satırı silmesin; liste yeniden kurulur
        e.accept()
        if pid:
            QTimer.singleShot(0, lambda: self.moved.emit(pid, fid))


class NotesPanel(QWidget):
    open_page = pyqtSignal(object)
    new_page = pyqtSignal()
    new_page_in = pyqtSignal(str)     # klasörde yeni not
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
        head.setContentsMargins(4, 0, 4, 0)
        head.setSpacing(2)
        # sekmeler: Notlar | Katmanlar (katmanlar sekmesi set_layers ile eklenir)
        self.tabs = []
        for i, key in enumerate(("notes", "layers")):
            tb = QPushButton(t(key))
            tb.setObjectName("PanelTab")
            tb.setCheckable(True)
            tb.setCursor(Qt.CursorShape.PointingHandCursor)
            tb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            tb.clicked.connect(lambda _=False, x=i: self.set_tab(x))
            head.addWidget(tb)
            self.tabs.append(tb)
        self.tabs[1].setToolTip(t("layers_tip"))
        self.tabs[1].hide()
        head.addStretch(1)
        self.folder_btn = IconButton("create_new_folder", t("new_folder"), 36, 21)
        self.folder_btn.clicked.connect(lambda: self.new_folder())
        head.addWidget(self.folder_btn)
        b = IconButton("add", t("new_note") + " (Ctrl+N)", 36, 22)
        b.clicked.connect(self.new_page.emit)
        head.addWidget(b)
        self.add_btn = b
        lay.addLayout(head)
        self.stack = QStackedWidget(self)
        lay.addWidget(self.stack, 1)
        self.list = NotesList(self)
        self.list.setObjectName("NotesList")
        self.list.moved.connect(self._moved)
        self.delegate = NoteDelegate(self)
        self.list.setItemDelegate(self.delegate)
        # klasör adı yazılırken liste yenilenmez (satır silinirse düzenleyici boşta kalır); bitince yenilenir
        self._pending_refresh = False
        self.delegate.closeEditor.connect(lambda *_: QTimer.singleShot(0, self._after_edit))
        self.list.setMouseTracking(True)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self.list.itemClicked.connect(self._clicked)
        self.list.itemDoubleClicked.connect(self._double_clicked)
        self.stack.addWidget(self.list)
        self.tabs[0].setChecked(True)
        self._current = None
        store.list_changed.connect(self.refresh)
        theme.changed.connect(lambda _: self.list.viewport().update())

    def set_layers(self, widget):
        self.stack.addWidget(widget)
        self.tabs[1].show()
        from .config import prefs
        self.set_tab(1 if prefs.get("side_tab", "notes") == "layers" else 0, save=False)

    def tab(self):
        return self.stack.currentIndex()

    def set_tab(self, i, save=True):
        if i >= self.stack.count():
            i = 0
        self.stack.setCurrentIndex(i)
        for k, tb in enumerate(self.tabs):
            tb.setChecked(k == i)
        self.add_btn.setVisible(i == 0)
        self.folder_btn.setVisible(i == 0)
        if save:
            from .config import prefs
            prefs.set("side_tab", "layers" if i == 1 else "notes")

    def _emit(self, it, sig):
        p = self.store.get(it.data(Qt.ItemDataRole.UserRole))
        if p is not None:
            sig.emit(p)

    def _clicked(self, it):
        if it.data(ROLE_KIND) == "folder":
            fid = it.data(Qt.ItemDataRole.UserRole)
            f = self.store.folder(fid)
            if f is not None:      # liste tıklama işleyicisinden çıkınca yenilensin
                QTimer.singleShot(0, lambda: self.store.set_folder_open(fid, not f["open"]))
            return
        self._emit(it, self.open_page)

    def _double_clicked(self, it):
        if it.data(ROLE_KIND) == "note":
            self._emit(it, self.rename_page)

    def _moved(self, pid, fid):
        p = self.store.get(pid)
        if p is not None:
            self.store.move_to_folder(p, fid)
            if fid:
                self.store.set_folder_open(fid, True)

    def folder_item(self, fid):
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.data(ROLE_KIND) == "folder" and it.data(Qt.ItemDataRole.UserRole) == fid:
                return it
        return None

    def edit_folder(self, fid):
        it = self.folder_item(fid)
        if it is not None:
            self.list.scrollToItem(it)
            self.list.editItem(it)

    def new_folder(self, move=None):
        """Yeni klasör açar, adını hemen yazdırır; move: içine taşınacak not."""
        fid = self.store.create_folder(t("new_folder"))
        if not fid:
            return ""
        if move is not None:
            self.store.move_to_folder(move, fid)
        self.set_tab(0)
        QTimer.singleShot(0, lambda: self.edit_folder(fid))
        return fid

    def set_current(self, pid):
        self._current = pid
        self.refresh()

    def _after_edit(self):
        if self._pending_refresh:
            self._pending_refresh = False
            self.refresh()

    def refresh(self):
        if self.list.state() == QAbstractItemView.State.EditingState:
            self._pending_refresh = True
            return
        self.list.blockSignals(True)
        self.list.clear()
        pages = [p for p in self.store.sorted() if p.saved_once or p.id == self._current]
        cur = self.store.get(self._current)
        fids = {f["id"] for f in self.store.folders}

        def add_note(p, indent):
            it = QListWidgetItem()
            it.setData(Qt.ItemDataRole.UserRole, p.id)
            it.setData(ROLE_KIND, "note")
            it.setData(ROLE_INDENT, 1 if indent else 0)
            it.setToolTip(p.display_title())
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.list.addItem(it)
            if p.id == self._current:
                it.setSelected(True)
                self.list.setCurrentItem(it)

        for f in self.store.folders:
            inside = [p for p in pages if p.folder == f["id"]]
            it = QListWidgetItem()
            it.setData(Qt.ItemDataRole.UserRole, f["id"])
            it.setData(ROLE_KIND, "folder")
            it.setData(ROLE_INDENT + 1, len([p for p in inside if p.saved_once]))
            it.setToolTip(f["name"])
            it.setFlags((it.flags() | Qt.ItemFlag.ItemIsEditable) & ~Qt.ItemFlag.ItemIsDragEnabled
                        & ~Qt.ItemFlag.ItemIsSelectable)
            self.list.addItem(it)
            # açık klasör ya da açık olan not bu klasördeyse içindekiler görünür
            if f["open"] or (cur is not None and cur.folder == f["id"]):
                for p in inside:
                    add_note(p, True)
        for p in pages:
            if not p.folder or p.folder not in fids:
                add_note(p, False)
        self.list.blockSignals(False)

    def _menu(self, pos):
        it = self.list.itemAt(pos)
        col = tcolor("text")
        m = QMenu(self)
        if it is None:
            m.addAction(icons.icon("add", col, 18), t("new_note"), self.new_page.emit)
            m.addAction(icons.icon("create_new_folder", col, 18), t("new_folder"), lambda: self.new_folder())
            m.addSeparator()
            m.addAction(icons.icon("folder_open", col, 18), t("open_notes_folder"), self.store.open_root_in_explorer)
            m.exec(self.list.viewport().mapToGlobal(pos))
            return
        if it.data(ROLE_KIND) == "folder":
            fid = it.data(Qt.ItemDataRole.UserRole)
            m.addAction(icons.icon("add", col, 18), t("new_note_here"), lambda: self.new_page_in.emit(fid))
            m.addAction(icons.icon("edit", col, 18), t("rename"), lambda: self.edit_folder(fid))
            m.addSeparator()
            m.addAction(icons.icon("delete", col, 18), t("delete_folder"), lambda: self.store.delete_folder(fid))
            m.exec(self.list.viewport().mapToGlobal(pos))
            return
        p = self.store.get(it.data(Qt.ItemDataRole.UserRole))
        if p is None:
            return
        m.addAction(icons.icon("open_in", col, 18), t("open"), lambda: self.open_page.emit(p))
        m.addAction(icons.icon("edit", col, 18), t("rename"), lambda: self.rename_page.emit(p))
        mv = m.addMenu(icons.icon("folder", col, 18), t("move_to_folder"))
        for f in self.store.folders:
            on = p.folder == f["id"]
            mv.addAction(icons.icon("check" if on else "folder", col, 18), f["name"],
                         lambda _=False, x=f["id"]: self.store.move_to_folder(p, x))
        if p.folder:
            mv.addAction(icons.icon("blank", col, 18), t("no_folder"), lambda: self.store.move_to_folder(p, ""))
        if self.store.folders:
            mv.addSeparator()
        mv.addAction(icons.icon("create_new_folder", col, 18), t("new_folder") + "…", lambda: self.new_folder(p))
        if p.file:
            m.addAction(icons.icon("folder_open", col, 18), t("show_in_folder"), lambda: _reveal(p.file))
        m.addAction(icons.icon("download", col, 18), t("export_as"), lambda: self.export_page.emit(p))
        m.addAction(icons.icon("download", col, 18), t("export_all_pdf"), self.export_all.emit)
        m.addSeparator()
        m.addAction(icons.icon("delete", col, 18), t("delete_note"), lambda: self.delete_page.emit(p))
        m.exec(self.list.viewport().mapToGlobal(pos))
