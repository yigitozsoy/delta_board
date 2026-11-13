"""delta logosunu gamma ile aynı tarzda üretir (Pillow gerekir):
  deltaapp/assets/logo.ico — açık gri degrade yuvarlak kare, ince gri çerçeve, koyu Georgia Δ (gamma'nın Γ'sı ile
                             aynı yazı tipi, renk ve boyut; ölçüler gamma'nın 256 px simgesinden alındı)
  deltaapp/assets/logo.png — beyaz Δ (arayüzde renklendirilir), gamma'nın logo.png'si ile aynı tuval ve yükseklik
Çalıştır: python packaging/make_logo.py"""
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "deltaapp", "assets")
FONT = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "georgia.ttf")
GLYPH = "Δ"
SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]

# gamma simgesinden (256 px) ölçülenler
RADIUS = 56 / 256          # köşe yarıçapı
TOP, BOTTOM = 236, 190     # dikey degrade (gri tonu)
BORDER = 154               # çerçeve rengi, 2 px, 1 px içeride
INK = (33, 33, 33, 255)    # harf rengi
GLYPH_H = 162 / 256        # harf yüksekliği
CENTER = (127.5 / 256, 128 / 256)


def glyph_mask(height_px, ss):
    """Harfin tam yükseklikte, kırpılmış alfa maskesi."""
    f = ImageFont.truetype(FONT, int(height_px * 1.6))
    m = Image.new("L", (int(height_px * 3), int(height_px * 3)), 0)
    ImageDraw.Draw(m).text((height_px // 2, height_px // 4), GLYPH, font=f, fill=255)
    m = m.crop(m.getbbox())
    k = height_px / m.height
    return m.resize((max(1, round(m.width * k)), round(height_px)), Image.LANCZOS)


def icon(n):
    ss = 8                       # süper örnekleme
    s = n * ss
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    grad = Image.new("RGBA", (s, s))
    d = ImageDraw.Draw(grad)
    for y in range(s):
        v = round(TOP + (BOTTOM - TOP) * y / (s - 1))
        d.line([(0, y), (s, y)], fill=(v, v, v, 255))
    shape = Image.new("L", (s, s), 0)
    r = RADIUS * s
    ImageDraw.Draw(shape).rounded_rectangle([0, 0, s - 1, s - 1], radius=r, fill=255)
    img.paste(grad, (0, 0), shape)
    # ince çerçeve: 256'da 2 px, küçük boyutlarda en az 1 px
    bw = max(1.0, 2 * n / 256) * ss
    inset = max(0.5, n / 256) * ss
    ImageDraw.Draw(img).rounded_rectangle([inset, inset, s - 1 - inset, s - 1 - inset], radius=r - inset,
                                         outline=(BORDER, BORDER, BORDER, 255), width=round(bw))
    # harf
    m = glyph_mask(GLYPH_H * s, ss)
    cx, cy = CENTER[0] * s, CENTER[1] * s
    ink = Image.new("RGBA", m.size, INK)
    img.paste(ink, (round(cx - m.width / 2), round(cy - m.height / 2)), m)
    return img.resize((n, n), Image.LANCZOS)


def white_png():
    """Arayüz logosu: gamma'nın logo.png'si gibi 262×306 tuval, 246 px yükseklikte beyaz harf."""
    W, H, gh, top = 262, 306, 246, 30
    m = glyph_mask(gh * 4, 4)
    m = m.resize((round(m.width / 4), gh), Image.LANCZOS)
    img = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    img.paste(Image.new("RGBA", m.size, (255, 255, 255, 255)), ((W - m.width) // 2, top), m)
    return img


def main():
    imgs = [icon(n) for n in SIZES]
    imgs[-1].save(os.path.join(ASSETS, "logo.ico"), sizes=[(n, n) for n in SIZES], append_images=imgs[:-1])
    white_png().save(os.path.join(ASSETS, "logo.png"))
    print("logo.ico + logo.png üretildi")


if __name__ == "__main__":
    main()
