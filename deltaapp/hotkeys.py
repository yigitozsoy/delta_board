"""Her yerde çalışan (global) kısayollar — Win32 RegisterHotKey.
delta arka planda (sistem tepsisinde) açıkken başka bir programdayken bile tetiklenir."""
import ctypes
from ctypes import wintypes

from PyQt6.QtCore import QObject, pyqtSignal, QAbstractNativeEventFilter, QCoreApplication, QTimer

user32 = ctypes.windll.user32
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
MODS = {"ctrl": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN}
SPECIAL = {"print": 0x2C, "prtsc": 0x2C, "printscreen": 0x2C, "space": 0x20, "insert": 0x2D, "pause": 0x13,
           "scrolllock": 0x91, "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22}
NAMES = ("capture", "annotate", "note", "record")


def parse(seq: str):
    """"Win+Shift+A" -> (mods, vk). Geçersizse None."""
    if not seq:
        return None
    parts = [p.strip() for p in seq.replace(" ", "").split("+") if p.strip()]
    mods, vk = 0, None
    for p in parts:
        lp = p.lower()
        if lp in MODS:
            mods |= MODS[lp]
        elif lp in SPECIAL:
            vk = SPECIAL[lp]
        elif len(p) == 1 and (p.isalpha() or p.isdigit()) and p.isascii():
            vk = ord(p.upper())
        elif lp.startswith("f") and lp[1:].isdigit() and 1 <= int(lp[1:]) <= 24:
            vk = 0x6F + int(lp[1:])
        else:
            return None
    if vk is None:
        return None
    if mods == 0 and not (0x70 <= vk <= 0x87 or vk in (0x2C, 0x13, 0x91)):
        return None  # tek harfi her yerde kapmayalım
    return mods, vk


class _Filter(QAbstractNativeEventFilter):
    def __init__(self, mgr):
        super().__init__()
        self.mgr = mgr

    def nativeEventFilter(self, event_type, message):
        try:
            if bytes(event_type) == b"windows_generic_MSG":
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY:
                    self.mgr._fire(int(msg.wParam))
                    return True, 0
        except Exception:
            pass
        return False, 0


class HotkeyManager(QObject):
    triggered = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._seq = {}      # ad -> metin
        self._ok = {}       # ad -> kayıt başarılı mı
        self._ids = {n: 0xD000 + i for i, n in enumerate(NAMES)}
        self._suspended = False
        self._filter = _Filter(self)
        QCoreApplication.instance().installNativeEventFilter(self._filter)

    def _fire(self, hid):
        for n, i in self._ids.items():
            if i == hid:
                QTimer.singleShot(0, lambda n=n: self.triggered.emit(n))

    def set(self, name, seq):
        self._seq[name] = seq or ""
        if self._suspended:
            return None
        return self._register(name)

    def _register(self, name):
        hid = self._ids[name]
        user32.UnregisterHotKey(None, hid)
        parsed = parse(self._seq.get(name, ""))
        if parsed is None:
            self._ok[name] = None if not self._seq.get(name) else False
            return self._ok[name]
        mods, vk = parsed
        ok = bool(user32.RegisterHotKey(None, hid, mods | MOD_NOREPEAT, vk))
        self._ok[name] = ok
        return ok

    def status(self, name):
        """True: çalışıyor, False: başka program kullanıyor / geçersiz, None: kapalı."""
        return self._ok.get(name)

    def suspend(self):
        """Kısayol düzenlenirken mevcut kısayollar tetiklenmesin."""
        self._suspended = True
        for hid in self._ids.values():
            user32.UnregisterHotKey(None, hid)

    def resume(self):
        self._suspended = False
        for n in NAMES:
            if n in self._seq:
                self._register(n)

    def unregister_all(self):
        for hid in self._ids.values():
            user32.UnregisterHotKey(None, hid)
