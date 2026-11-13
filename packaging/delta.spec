# -*- mode: python ; coding: utf-8 -*-
# PyInstaller tanımı. packaging\build.ps1 üzerinden çalıştırın.
# Çıktı: build\dist\delta\delta.exe — Görev Yöneticisi'nde ve görev çubuğunda "delta" adı ve logosu görünür.
import os
from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [(os.path.join(ROOT, "deltaapp", "assets"), os.path.join("deltaapp", "assets"))]
binaries = []
hiddenimports = ["PyQt6.QtSvg"]
d, b, h = collect_all("imageio_ffmpeg")   # ekran videosu için ffmpeg
datas += d
binaries += b
hiddenimports += h

EXCLUDES = [
    "tkinter", "unittest", "pydoc", "test", "lib2to3", "matplotlib", "scipy", "pandas", "numpy", "IPython",
    "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.QtWebChannel", "PyQt6.QtQml",
    "PyQt6.QtQuick", "PyQt6.QtQuickWidgets", "PyQt6.Qt3DCore", "PyQt6.QtBluetooth", "PyQt6.QtSql",
    "PyQt6.QtTest", "PyQt6.QtDesigner", "PyQt6.QtHelp", "PyQt6.QtPdf", "PyQt6.QtPdfWidgets",
    "PyQt6.QtMultimedia", "PyQt6.QtMultimediaWidgets", "PyQt6.QtPositioning", "PyQt6.QtSensors",
    "PyQt6.QtSerialPort", "PyQt6.QtCharts", "PyQt6.QtOpenGL", "PyQt6.QtOpenGLWidgets",
]

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="delta",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    version=os.path.join(SPECPATH, "version_info.txt"),
    icon=[os.path.join(ROOT, "deltaapp", "assets", "logo.ico")],
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="delta")
