"""Görev çubuğu kimliği: pencereye "delta" adını, logosunu ve yeniden açma komutunu yazar.
Kaynaktan (pythonw.exe) çalışırken görev çubuğu menüsünde "Python" yerine "delta" görünür,
"Görev çubuğuna sabitle" de doğru programı açar. delta.exe olarak çalışırken de zararsızdır."""
import ctypes
import os
import sys
from ctypes import wintypes

from .config import asset

APP_ID = "delta.whiteboard"


class _GUID(ctypes.Structure):
    _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD), ("d3", wintypes.WORD), ("d4", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, s):
        s = s.strip("{}").replace("-", "")
        b = bytes.fromhex(s[16:])
        return cls(int(s[:8], 16), int(s[8:12], 16), int(s[12:16], 16), (ctypes.c_ubyte * 8)(*b))


class _PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", _GUID), ("pid", wintypes.DWORD)]


class _PROPVARIANT(ctypes.Structure):
    _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort), ("r2", ctypes.c_ushort), ("r3", ctypes.c_ushort),
                ("ptr", ctypes.c_void_p), ("pad", ctypes.c_void_p)]


_FMT = "{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}"  # PKEY_AppUserModel_*
_IID_IPropertyStore = "{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}"
VT_LPWSTR = 31


def relaunch_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    exe = sys.executable
    w = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(w):
        exe = w
    main = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "main.py"))
    return f'"{exe}" "{main}"'


def set_process_id():
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass


def apply_to_window(hwnd):
    """Pencerenin özellik deposuna AppUserModel kimliği, adı, simgesi ve yeniden açma komutunu yazar."""
    try:
        shell32 = ctypes.windll.shell32
        store = ctypes.c_void_p()
        iid = _GUID.parse(_IID_IPropertyStore)
        if shell32.SHGetPropertyStoreForWindow(wintypes.HWND(hwnd), ctypes.byref(iid), ctypes.byref(store)) != 0:
            return False
        vtbl = ctypes.cast(ctypes.cast(store, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
        SetValue = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(_PROPERTYKEY),
                                      ctypes.POINTER(_PROPVARIANT))(vtbl[6])
        Commit = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p)(vtbl[7])
        Release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])
        ico = asset("logo.ico")
        vals = [(5, APP_ID), (2, relaunch_command()), (3, f"{ico},0"), (4, "delta")]
        keep = []
        try:
            for pid, text in vals:
                buf = ctypes.create_unicode_buffer(text)
                keep.append(buf)
                pv = _PROPVARIANT(VT_LPWSTR, 0, 0, 0, ctypes.cast(buf, ctypes.c_void_p), None)
                SetValue(store, ctypes.byref(_PROPERTYKEY(_GUID.parse(_FMT), pid)), ctypes.byref(pv))
            Commit(store)
        finally:
            Release(store)
        return True
    except Exception:
        return False
