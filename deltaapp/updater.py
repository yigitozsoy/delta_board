"""Güncelleme denetimi: GitHub'daki en son sürüme bakar (günde en fazla bir kez, arka planda).
Yalnızca herkese açık sürüm bilgisi okunur; hiçbir kişisel bilgi gönderilmez."""
import re
import time

from PyQt6.QtCore import QObject, pyqtSignal, QUrl
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from . import __version__, REPO
from .config import prefs

API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES = f"https://github.com/{REPO}/releases/latest"
DAY = 24 * 3600


def parse_version(s):
    nums = [int(x) for x in re.findall(r"\d+", s or "")[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def is_newer(remote, local=__version__):
    return parse_version(remote) > parse_version(local)


class UpdateChecker(QObject):
    """found(sürüm, sayfa) — daha yeni sürüm var; result(durum, sürüm) — elle denetim sonucu:
    durum "new" | "latest" | "error"."""
    found = pyqtSignal(str, str)
    result = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.net = QNetworkAccessManager(self)
        self._busy = False

    def check_auto(self):
        """Açılışta: ayar açıksa ve son denetimden 1 gün geçtiyse."""
        if not prefs.get("check_updates", True):
            return
        if time.time() - float(prefs.get("last_update_check", 0) or 0) < DAY:
            return
        self.check(manual=False)

    def check(self, manual=True):
        if self._busy:
            return
        self._busy = True
        req = QNetworkRequest(QUrl(API))
        req.setRawHeader(b"Accept", b"application/vnd.github+json")
        req.setRawHeader(b"User-Agent", f"delta/{__version__}".encode())
        req.setTransferTimeout(10000)
        reply = self.net.get(req)
        reply.finished.connect(lambda: self._done(reply, manual))

    def _done(self, reply, manual):
        self._busy = False
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                if manual:
                    self.result.emit("error", "")
                return
            import json
            data = json.loads(bytes(reply.readAll()).decode("utf-8", "replace"))
            tag = str(data.get("tag_name", "")).lstrip("vV")
            page = str(data.get("html_url", RELEASES))
            prefs.set("last_update_check", time.time())
            if tag and is_newer(tag):
                self.found.emit(tag, page)
                if manual:
                    self.result.emit("new", tag)
            elif manual:
                self.result.emit("latest", tag or __version__)
        except Exception:
            if manual:
                self.result.emit("error", "")
        finally:
            reply.deleteLater()
