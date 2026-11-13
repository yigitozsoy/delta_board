"""Görseldeki yazıyı okur (OCR): Windows'un kendi metin tanıması (Windows.Media.Ocr), ek kurulum gerekmez.
Windows PowerShell 5.1 üzerinden çağrılır (her Windows 10/11'de var); arayüz donmasın diye QProcess ile arka planda.
Dil: kullanıcının Windows dilleri (Türkçe varsa Türkçe), yoksa İngilizce."""
import os
import tempfile

from PyQt6.QtCore import QObject, pyqtSignal, QProcess, Qt
from PyQt6.QtGui import QImage

from .config import DATA_DIR

PS_SCRIPT = r"""
param([string]$Path)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$t) {
    $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op))
    $task.Wait(-1) | Out-Null
    $task.Result
}
[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime] | Out-Null
[Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime] | Out-Null
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bmp = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$eng = $null
foreach ($tag in @('tr', 'tr-TR')) {
    if (-not $eng) { try { $eng = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new($tag)) } catch {} }
}
if (-not $eng) { $eng = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
if (-not $eng) { $eng = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('en-US')) }
if (-not $eng) { [Console]::Error.WriteLine('no-ocr-language'); exit 3 }
$res = Await ($eng.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
$stream.Dispose()
foreach ($l in $res.Lines) { [Console]::Out.WriteLine($l.Text) }
"""


def _script_path():
    d = os.path.join(DATA_DIR, "ocr")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "ocr.ps1")
    try:
        if not os.path.exists(p) or open(p, encoding="utf-8-sig").read() != PS_SCRIPT:
            with open(p, "w", encoding="utf-8-sig") as f:
                f.write(PS_SCRIPT)
    except OSError:
        pass
    return p


def prepare(img: QImage) -> QImage:
    """Küçük yazılar daha iyi okunsun diye küçük görseller büyütülür; OCR sınırı (10000 px) aşılmaz."""
    img = img.convertToFormat(QImage.Format.Format_RGB32)
    w, h = img.width(), img.height()
    if max(w, h) < 1600:
        k = min(2.0, 3000 / max(w, h, 1))
        img = img.scaled(round(w * k), round(h * k), Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    elif max(w, h) > 9000:
        img = img.scaled(9000, 9000, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return img


_ACTIVE = set()   # çalışan işler: Python çöp toplayıcısı ortada silmesin


class OcrJob(QObject):
    """Tek seferlik okuma. done(metin) — boş metin "yazı bulunamadı" demek; failed(hata)."""
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, img: QImage, parent=None):
        super().__init__(parent)
        fd, self.path = tempfile.mkstemp(prefix="delta-ocr-", suffix=".png")
        os.close(fd)
        prepare(img).save(self.path, "PNG")
        self.proc = QProcess(self)
        self.proc.finished.connect(self._finished)
        self.proc.errorOccurred.connect(self._error)
        self._ended = False

    def start(self):
        exe = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0",
                           "powershell.exe")
        # konsolu olmayan uygulamadan QProcess, konsol penceresi açmadan başlatır (CREATE_NO_WINDOW)
        args = ["-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File", _script_path(), self.path]
        self.proc.setStandardInputFile(QProcess.nullDevice())   # PowerShell stdin'i beklemesin
        self.proc.setProgram(exe)
        self.proc.setArguments(args)
        _ACTIVE.add(self)
        self.proc.start()
        return self

    def _cleanup(self):
        _ACTIVE.discard(self)
        try:
            os.remove(self.path)
        except OSError:
            pass

    def _finished(self, code, status):
        if self._ended:
            return
        self._ended = True
        out = bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace").lstrip("\ufeff")
        err = bytes(self.proc.readAllStandardError()).decode("utf-8", "replace").strip()
        self._cleanup()
        if code != 0:
            self.failed.emit(err.splitlines()[-1] if err else f"exit {code}")
        else:
            lines = [ln.rstrip() for ln in out.replace("\r\n", "\n").split("\n")]
            self.done.emit("\n".join(ln for ln in lines if ln).strip())
        self.deleteLater()

    def _error(self, _e):
        if self._ended or self.proc.state() != QProcess.ProcessState.NotRunning:
            return
        self._ended = True
        self._cleanup()
        self.failed.emit(self.proc.errorString())
        self.deleteLater()


def read_text(img: QImage, on_done, on_failed=None, parent=None):
    """Kısa yol: read_text(görsel, lambda metin: ..., lambda hata: ...)"""
    job = OcrJob(img, parent)
    job.done.connect(on_done)
    if on_failed is not None:
        job.failed.connect(on_failed)
    return job.start()
