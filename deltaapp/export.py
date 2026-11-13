"""Notu dosyaya kaydetme: PNG, JPEG ve PDF (birden çok not tek PDF'te, her not bir sayfa)."""
import os

from PyQt6.QtCore import QMarginsF, QRectF, QSizeF, Qt
from PyQt6.QtGui import QImage, QPainter, QPageLayout, QPageSize, QPdfWriter, QColor

FORMATS = ("png", "jpg", "pdf")
FILTERS = {"png": "PNG (*.png)", "jpg": "JPEG (*.jpg *.jpeg)", "pdf": "PDF (*.pdf)"}


def ext_of(path):
    e = os.path.splitext(path)[1].lower().lstrip(".")
    return "jpg" if e == "jpeg" else e


def file_filter(first="png"):
    order = [first] + [f for f in FORMATS if f != first]
    return ";;".join(FILTERS[f] for f in order)


def fix_ext(path, selected_filter=""):
    """Kullanıcı uzantı yazmadıysa seçtiği türün uzantısını ekler."""
    if ext_of(path) in FORMATS:
        return path
    for f, flt in FILTERS.items():
        if flt == selected_filter:
            return path + "." + f
    return path + ".png"


def _opaque(img: QImage, bg: QColor):
    """JPEG saydamlık bilmez: arka plan rengiyle düzleştir."""
    out = QImage(img.size(), QImage.Format.Format_RGB32)
    out.fill(bg)
    p = QPainter(out)
    p.drawImage(0, 0, img)
    p.end()
    return out


def save_image(img: QImage, path: str, bg: QColor = None) -> bool:
    """Uzantıya göre PNG / JPEG / PDF kaydeder."""
    e = ext_of(path)
    if e == "pdf":
        return export_pdf([img], path)
    if e == "jpg":
        return _opaque(img, bg or QColor("#ffffff")).save(path, "JPEG", 92)
    return img.save(path, "PNG")


def export_pdf(images, path, title="delta") -> bool:
    """Her görsel ayrı bir sayfa; sayfa boyutu görselin oranında (kenar boşluksuz, 150 dpi)."""
    images = [im for im in images if im is not None and not im.isNull()]
    if not images:
        return False
    dpi = 150
    w = QPdfWriter(path)
    w.setTitle(title)
    w.setCreator("delta")
    w.setResolution(dpi)

    def page_for(im):
        size = QPageSize(QSizeF(im.width() * 72 / dpi, im.height() * 72 / dpi), QPageSize.Unit.Point,
                         "delta", QPageSize.SizeMatchPolicy.ExactMatch)
        return QPageLayout(size, QPageLayout.Orientation.Portrait, QMarginsF(0, 0, 0, 0))

    w.setPageLayout(page_for(images[0]))
    p = QPainter()
    if not p.begin(w):
        return False
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    for i, im in enumerate(images):
        if i:
            w.setPageLayout(page_for(im))
            w.newPage()
        target = QRectF(0, 0, w.width(), w.height())
        p.drawImage(target, im, QRectF(im.rect()), Qt.ImageConversionFlag.AutoColor)
    p.end()
    return True
