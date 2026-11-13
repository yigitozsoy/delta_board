"""Uçtan uca test: gerçek arayüzü açar, fareyle çizer / siler / yazar, notu kaydedip geri okur.
Gerçek tercihlere dokunmaz (LOCALAPPDATA geçici klasöre yönlendirilir). Ekranın kendisini yakalamaz.

python tests/smoke_test.py [--shots KLASÖR]
"""
import math
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="delta_test_")
os.environ["LOCALAPPDATA"] = TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import Qt, QPoint, QPointF, QEvent, QRect, QRectF  # noqa: E402
from PyQt6.QtGui import QMouseEvent, QImage, QColor, QPixmap, QKeyEvent, QWheelEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication, QScrollArea  # noqa: E402

SHOTS = sys.argv[sys.argv.index("--shots") + 1] if "--shots" in sys.argv else None
steps = []
L, R, M, NB = (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton,
               Qt.MouseButton.NoButton)
NOMOD, CTRL = Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ControlModifier
PRESS, MOVE, REL, DBL = (QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove, QEvent.Type.MouseButtonRelease,
                         QEvent.Type.MouseButtonDblClick)


def step(name, ok):
    ok = bool(ok)
    steps.append((name, ok))
    print(("OK   " if ok else "FAIL ") + name, flush=True)


def pump(n=5):
    for _ in range(n):
        QApplication.processEvents()


def mouse(w, typ, pos, btn, btns, mods=NOMOD):
    pos = QPointF(pos)
    ev = QMouseEvent(typ, pos, QPointF(w.mapToGlobal(pos.toPoint())), btn, btns, mods)
    QApplication.sendEvent(w, ev)


def drag(w, pts, btn=L, mods=NOMOD):
    mouse(w, PRESS, pts[0], btn, btn, mods)
    for p in pts[1:]:
        mouse(w, MOVE, p, NB, btn, mods)
    mouse(w, REL, pts[-1], btn, NB, mods)
    pump()


def click(w, p, btn):
    mouse(w, PRESS, p, btn, btn)
    mouse(w, REL, p, btn, NB)
    pump()


def key(w, k, text="", mods=NOMOD):
    QApplication.sendEvent(w, QKeyEvent(QEvent.Type.KeyPress, k, mods, text))
    QApplication.sendEvent(w, QKeyEvent(QEvent.Type.KeyRelease, k, mods, text))
    pump()


def wheel(w, pos, delta, mods=NOMOD):
    ev = QWheelEvent(QPointF(pos), QPointF(w.mapToGlobal(pos)), QPoint(0, 0), delta, NB, mods,
                     Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(w, ev)
    pump()


def shot(widget, name):
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        widget.grab().save(os.path.join(SHOTS, name + ".png"))


def main():
    from deltaapp.config import prefs
    for n in ("capture", "annotate", "note", "record"):
        prefs.set("hotkey_" + n, "")  # testte gerçek kısayolları kapmayalım
    prefs.set("video_dir", os.path.join(TMP, "videos"))
    prefs.set("record_mic", "")
    prefs.set("check_updates", False)   # testte ağa çıkma
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    from deltaapp.app import DeltaApp
    from deltaapp import items as I
    from deltaapp.tools import state
    d = DeltaApp(app)
    win = d.win
    win.resize(1280, 800)
    pump(20)
    b = win.board
    vp = b.viewport()
    sc = b.scene()
    step("pencere açıldı, boş not", b.is_empty() and win.area.hint.isVisible())
    shot(win, "01_bos")

    state.set_tool("pen")
    drag(vp, [QPoint(200 + i * 8, 200 + int(40 * math.sin(i / 4))) for i in range(60)])
    strokes = [it for it in sc.content_items() if isinstance(it, I.StrokeItem)]
    step("kalemle çizim", len(strokes) == 1 and len(strokes[0].pts) > 5)
    step("boş ipucu gizlendi", not win.area.hint.isVisible())

    state.set_color("#ff453a")
    drag(vp, [QPoint(200, 380), QPoint(300, 383), QPoint(400, 380)], mods=Qt.KeyboardModifier.ShiftModifier)
    lines = [it for it in sc.content_items() if isinstance(it, I.StrokeItem) and it.kind == "line"]
    step("Shift+sürükle düz çizgi", len(lines) == 1)

    for tool, a, bb in (("rect", QPoint(600, 150), QPoint(800, 300)), ("ellipse", QPoint(850, 150), QPoint(1000, 300)),
                        ("arrow", QPoint(600, 400), QPoint(800, 480))):
        state.set_tool(tool)
        drag(vp, [a, QPoint((a.x() + bb.x()) // 2, (a.y() + bb.y()) // 2), bb])
    kinds = sorted(it.kind for it in sc.content_items() if isinstance(it, I.StrokeItem))
    step("şekiller (dikdörtgen/elips/ok)", kinds == ["arrow", "ellipse", "line", "pen", "rect"])

    state.set_tool("hl")
    state.set_color("#ffd60a")
    drag(vp, [QPoint(180, 240), QPoint(340, 242), QPoint(500, 240)])
    step("fosforlu kalem", any(it.kind == "hl" for it in sc.content_items() if isinstance(it, I.StrokeItem)))

    # yazı: çift tık (ilk tıklamanın noktası geri alınmalı)
    state.set_tool("pen")
    state.set_color("auto")
    p = QPoint(250, 560)
    mouse(vp, PRESS, p, L, L)
    mouse(vp, REL, p, L, NB)
    mouse(vp, DBL, p, L, L)
    mouse(vp, REL, p, L, NB)
    pump()
    ed = b.editing_text()
    dots = [i for i in sc.content_items() if isinstance(i, I.StrokeItem) and i.kind == "pen" and len(i.pts) <= 2]
    step("çift tık yazı kutusu açtı (nokta geri alındı)", ed is not None and not dots)
    for ch in "Toplantı notu: Q3 hedefleri":
        key(vp, 0, ch)
    key(vp, Qt.Key.Key_Escape)
    texts = [it for it in sc.content_items() if isinstance(it, I.TextItem)]
    step("klavyeden yazı", len(texts) == 1 and texts[0].toPlainText() == "Toplantı notu: Q3 hedefleri"
         and b.editing_text() is None)
    pump(5)
    step("otomatik başlık", win.page.auto.startswith("Toplantı notu"))
    tt = win.titlebar.title
    mouse(tt, PRESS, QPoint(10, 10), L, L)
    mouse(tt, REL, QPoint(10, 10), L, NB)
    pump()
    step("not adı: tek tık düzenlemeye açmaz, kutu dar", not tt.editing() and tt.width() <= tt.MAX_W)
    mouse(tt, DBL, QPoint(10, 10), L, L)
    pump()
    step("not adı: çift tık düzenler", tt.editing() and tt.hasFocus())
    key(tt, Qt.Key.Key_Escape)
    b.setFocus()
    pump()
    step("not adı: Esc / odak kaybı kilitler", not tt.editing())

    # Enter: imlecin olduğu yere yazı
    b.setFocus()
    key(vp, Qt.Key.Key_Return)
    step("Enter yazı kutusu açar", b.editing_text() is not None)
    key(vp, Qt.Key.Key_Escape)
    step("boş yazı kutusu iz bırakmaz", len([i for i in sc.content_items() if isinstance(i, I.TextItem)]) == 1)

    # rakam tuşları araç seçer, Shift+rakam renk (gerçek sanal tuş koduyla)
    def vkey(w, k, vk, text="", mods=NOMOD):
        for typ in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QApplication.sendEvent(w, QKeyEvent(typ, k, mods, 0, vk, 0, text))
        pump()
    got_tools = []
    for k, vk in ((Qt.Key.Key_3, 0x33), (Qt.Key.Key_8, 0x38), (Qt.Key.Key_0, 0x30), (Qt.Key.Key_1, 0x31)):
        vkey(vp, k, vk, chr(vk))
        got_tools.append(state.tool)
    step("1-9/0 araç seçer (3 ok, 8 lazer, 0 seç, 1 kalem)", got_tools == ["arrow", "laser", "select", "pen"])
    vkey(vp, Qt.Key.Key_Exclam, 0x32, "'", Qt.KeyboardModifier.ShiftModifier)   # Shift+2 (Türkçe klavyede ')
    step("Shift+2 kırmızı renk", state.color == "#ff453a" and state.tool == "pen")
    state.set_color("auto")
    # hızlı yazı: harfe basınca imlecin olduğu yerde yazı başlar
    n_txt = len([i for i in sc.content_items() if isinstance(i, I.TextItem)])
    b.setFocus()
    key(vp, Qt.Key.Key_M, "M")
    ed = b.editing_text()
    for ch in "erhaba":
        key(vp, 0, ch)
    txt = ed.toPlainText() if ed is not None else ""
    key(vp, Qt.Key.Key_Escape)
    step("harfe basınca hızlı yazı (Merhaba)", txt == "Merhaba" and
         len([i for i in sc.content_items() if isinstance(i, I.TextItem)]) == n_txt + 1)

    # görsel yapıştır
    img = QImage(320, 200, QImage.Format.Format_RGB32)
    img.fill(QColor("#3ea6ff"))
    QApplication.clipboard().setImage(img)
    b.setFocus()
    key(vp, Qt.Key.Key_V, "", CTRL)
    imgs = [it for it in sc.content_items() if isinstance(it, I.ImageItem)]
    step("Ctrl+V görsel yapıştırma", len(imgs) == 1)
    # görsel boyutlandırma: yapıştırılan görsel seçili gelir, kalem açıkken de köşeden büyür
    if imgs:
        g = imgs[0]
        state.set_tool("pen")
        pump()
        step("eklenen görsel seçili geliyor", g.isSelected())
        def vcorner(c):
            return b.mapFromScene(g.mapToScene(c))

        def grect():
            return g.mapRectToScene(QRectF(0, 0, g.pixmap().width(), g.pixmap().height()))
        r0 = grect()
        n_strokes = len([i for i in sc.content_items() if isinstance(i, I.StrokeItem)])
        br = vcorner(QPointF(g.pixmap().width(), g.pixmap().height()))
        drag(vp, [br, br + QPoint(40, 10), br + QPoint(80, 20)])
        r1 = grect()
        same_strokes = n_strokes == len([i for i in sc.content_items() if isinstance(i, I.StrokeItem)])
        step("sağ alt köşeden büyüdü (kalemde, çizgi çizmeden)", r1.width() > r0.width() * 1.2 and
             abs(r1.left() - r0.left()) < 0.5 and abs(r1.top() - r0.top()) < 0.5 and same_strokes)
        tl = vcorner(QPointF(0, 0))
        drag(vp, [tl, tl + QPoint(30, 30), tl + QPoint(60, 60)])
        r2 = grect()
        step("sol üst köşeden küçüldü, sağ alt sabit", r2.width() < r1.width() and
             abs(r2.right() - r1.right()) < 0.5 and abs(r2.bottom() - r1.bottom()) < 0.5)
        key(vp, Qt.Key.Key_Z, "", CTRL)
        key(vp, Qt.Key.Key_Z, "", CTRL)
        r3 = grect()
        step("boyutlandırma geri alınır", abs(r3.width() - r0.width()) < 0.5 and abs(r3.left() - r0.left()) < 0.5)
    shot(win, "02_cizim")

    # sağ tık basılı sürükle = sil (dikdörtgenin üst kenarı + elipsin ortası üstünden geç)
    n0 = len(sc.content_items())
    drag(vp, [QPoint(590, 150), QPoint(700, 150), QPoint(850, 225), QPoint(1010, 225)], btn=R)
    left = [it.kind for it in sc.content_items() if isinstance(it, I.StrokeItem)]
    step("sağ tık sürükle sildi", "rect" not in left and "ellipse" not in left)
    step("görsel silgiden etkilenmedi", any(isinstance(i, I.ImageItem) for i in sc.content_items()))
    key(vp, Qt.Key.Key_Z, "", CTRL)
    step("Ctrl+Z silmeyi geri aldı", len(sc.content_items()) == n0)
    click(vp, QPoint(10, 10), Qt.MouseButton.BackButton)
    step("fare geri tuşu = geri al", len(sc.content_items()) == n0 - 1)
    click(vp, QPoint(10, 10), Qt.MouseButton.ForwardButton)
    step("fare ileri tuşu = yinele", len(sc.content_items()) == n0)

    # yakınlaştırma (tekerlek) + Alt+tekerlek kalınlık
    z0 = b.zoom()
    wheel(vp, QPoint(640, 400), QPoint(0, 120))
    step("tekerlek yakınlaştırır", b.zoom() > z0 * 1.1)
    w0 = state.width
    wheel(vp, QPoint(640, 400), QPoint(120, 0), Qt.KeyboardModifier.AltModifier)
    step("Alt+tekerlek kalınlık", state.width > w0)
    state.set_width(4.0)
    h0 = b.horizontalScrollBar().value()
    drag(vp, [QPoint(600, 400), QPoint(550, 400), QPoint(500, 400)], btn=M)
    step("orta tuşla kaydırma", b.horizontalScrollBar().value() != h0)
    key(vp, Qt.Key.Key_Home)
    step("F hepsini sığdırır", all(vp.rect().contains(b.mapFromScene(it.sceneBoundingRect().center()))
                                   for it in sc.content_items()))

    # Ctrl+sol ile taşıma + geri al
    tgt = texts[0]
    c = b.mapFromScene(tgt.sceneBoundingRect().center())
    pos0 = tgt.pos()
    drag(vp, [c, c + QPoint(40, 0), c + QPoint(80, 30)], mods=CTRL)
    moved = tgt.pos() != pos0
    key(vp, Qt.Key.Key_Z, "", CTRL)
    step("Ctrl+sürükle taşır, Ctrl+Z geri alır", moved and tgt.pos() == pos0)
    sc.clearSelection()

    # renk tuşu seçimi boyar
    tgt.setSelected(True)
    tool_before = state.tool
    QApplication.sendEvent(vp, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Ampersand, Qt.KeyboardModifier.ShiftModifier,
                                         0, 0x36, 0, "&"))
    pump()
    step("seçiliyken Shift+6 boyar, araç değişmez", tgt.color_name == "#3ea6ff" and state.tool == tool_before)
    key(vp, Qt.Key.Key_Z, "", CTRL)
    step("boyama geri alınır", tgt.color_name == "auto")
    sc.clearSelection()

    # lazer kaydedilmez
    state.set_tool("laser")
    n1 = len(sc.content_items())
    drag(vp, [QPoint(300, 300), QPoint(400, 350), QPoint(500, 300)])
    step("lazer içerik eklemez", len(sc.content_items()) == n1 and b._lasers)
    state.set_tool("pen")

    # tema değişince "auto" renk döner
    from deltaapp.theme import theme
    theme.apply("light")
    pump()
    step("açık temada otomatik renk siyah", texts[0].defaultTextColor().lightness() < 60)
    shot(win, "03_acik_tema")
    theme.apply("dark")
    pump()

    # kaydet + yeni not + geri dön
    pid = win.page.id
    win.store.flush()
    step("not dosyası yazıldı", os.path.exists(win.page.path) and os.path.exists(win.page.thumb_path))
    win.new_note()
    pump()
    step("yeni boş not", win.page.id != pid and b.is_empty())
    win.new_note()
    step("boş notta yeni not açılmaz", sum(1 for p in win.store.pages.values() if not p.saved_once) == 1)
    win.open_page(win.store.get(pid))
    pump()
    step("boş not listeden düştü, eski not açıldı", win.page.id == pid and len(win.store.pages) == 1)

    from deltaapp.pages import NoteStore
    s2 = NoteStore()
    p2 = s2.get(pid)
    p2.ensure_loaded()
    step("not diskten geri okundu", len(p2.scene.content_items()) == len(b.scene().content_items()))
    shot(win, "04_kayitli")

    # Ekran alıntısı: gerçek ekran yerine sahte görüntüyle (kişisel pencereler görüntüye girmesin)
    from deltaapp.capture import CaptureOverlay
    fake = QPixmap(1600, 1000)
    fake.fill(QColor("#203040"))
    scr = app.primaryScreen()
    got = []
    d.capture.to_delta.connect(lambda pm: got.append(pm))
    ov = CaptureOverlay(d.capture, scr, fake)
    d.capture.overlays.append(ov)
    ov.setGeometry(QRect(0, 0, 800, 500))
    ov.dpr = 2.0
    ov.show()
    pump(5)
    drag(ov, [QPoint(100, 100), QPoint(200, 150), QPoint(300, 250)])
    pump(5)
    step("alıntı alanı seçildi + çubuk çıktı", ov.sel.width() == 200 and ov.sel.height() == 150 and ov.bar.isVisible())
    clip = QApplication.clipboard().image()
    print("   panodaki görüntü:", clip.width(), "x", clip.height(), "(beklenen 400 x 300)")
    shot(ov, "05_alinti")
    n_pages = len(win.store.pages)
    key(ov, Qt.Key.Key_Return)
    pump(10)
    step("Enter: alıntı yeni notta görsel oldu", got and len(win.store.pages) == n_pages + 1 and
         any(isinstance(i, I.ImageItem) for i in b.scene().content_items()))
    im = [i for i in b.scene().content_items() if isinstance(i, I.ImageItem)]
    step("alıntı mantıksal boyutta (HiDPI)", im and im[0].pixmap().width() == 400 and
         abs(im[0].pixmap().width() * im[0].scale() - 200) < 2)

    # alıntıyı ekrana iğnele
    ov = CaptureOverlay(d.capture, scr, fake)
    d.capture.overlays.append(ov)
    ov.setGeometry(QRect(0, 0, 800, 500))
    ov.dpr = 2.0
    ov.show()
    pump(5)
    drag(ov, [QPoint(100, 100), QPoint(200, 150), QPoint(300, 250)])
    want = ov.mapToGlobal(QPoint(100, 100))
    key(ov, Qt.Key.Key_T, mods=Qt.KeyboardModifier.ControlModifier)
    pump(10)
    pins = d.pins.pins
    pw = pins[0] if pins else None
    step("Ctrl+T: alıntı iğnelendi (yerinde, mantıksal boyut)", pw is not None and pw.isVisible() and
         pw.pos() == want and pw.width() == 200 and pw.height() == 150 and not d.capture.active())
    if pw is not None:
        wheel(pw, QPoint(0, 0), QPoint(0, 120))
        step("iğne: tekerlek büyütür, sol üst sabit", pw.width() == 220 and pw.pos() == want)
        wheel(pw, QPoint(10, 10), QPoint(0, -120), Qt.KeyboardModifier.ControlModifier)
        step("iğne: Ctrl+tekerlek saydamlık", abs(pw.windowOpacity() - 0.9) < 0.02)
        drag(pw, [QPoint(10, 10), QPoint(60, 40)])
        step("iğne: sürükleyince taşınır", pw.pos() == want + QPoint(50, 30))
        key(pw, Qt.Key.Key_C, mods=Qt.KeyboardModifier.ControlModifier)
        cim = QApplication.clipboard().image()
        step("iğne: Ctrl+C tam çözünürlük kopyalar", cim.width() == 400 and cim.height() == 300)
        pw._hover = True
        shot(pw, "11_igne")
        mouse(pw, QEvent.Type.MouseButtonDblClick, QPoint(30, 30), L, L)
        pump(10)
        step("iğne: çift tık kapatır", not d.pins.pins)

    # ekrana çiz katmanı
    ann = d.annotate
    ann.open()
    pump(10)
    state.set_tool("pen")
    drag(ann.board.viewport(), [QPoint(100, 100), QPoint(200, 160), QPoint(300, 120)])
    step("ekrana çiz: çizim", len(ann.board.scene().content_items()) == 1)
    ann.set_passthrough(True)
    pump()
    step("fareyi bırak modu", ann.passthrough and not ann.toolbar.isVisible())
    ann.toggle()
    pump()
    step("kısayol tekrar: çizime dönüş", not ann.passthrough and ann.isVisible())
    if SHOTS:
        ann.toolbar.grab().save(os.path.join(SHOTS, "06_ekrana_ciz_arac.png"))
    ann.toggle()
    pump()
    step("kısayol tekrar: kapandı ve temizlendi", not ann.isVisible() and ann.board.is_empty())

    # ekran videosu: önce seçim ekranı (sahte görüntü) kayıt modunda
    from deltaapp.recorder import find_ffmpeg
    recs = []
    d.capture.record.connect(lambda data: recs.append(data))
    d.capture.mode = "record"
    ov2 = CaptureOverlay(d.capture, scr, fake)
    d.capture.overlays.append(ov2)
    ov2.setGeometry(QRect(0, 0, 800, 500))
    ov2.dpr = 1.0
    ov2.show()
    pump(5)
    drag(ov2, [QPoint(50, 50), QPoint(150, 120), QPoint(251, 201)])
    shot(ov2, "09_kayit_secim")
    key(ov2, Qt.Key.Key_Return)
    pump(5)
    step("kayıt modu: Enter alanı kayda gönderir", recs and recs[0][1].width() == 201)
    d.capture.mode = "snip"
    step("ffmpeg bulundu", find_ffmpeg() is not None)
    # gerçek kayıt: küçük bir alan, 2 sn; dosya geçici klasöre yazılır, içeriğine bakılmaz, sonra silinir
    from PyQt6.QtCore import QEventLoop, QTimer
    saved = []
    d.recorder.saved.connect(lambda pth: saved.append(pth))
    d.recorder.failed.connect(lambda m: print("   kayıt hatası:", m))
    d.recorder.start(scr, QRect(0, 0, 161, 121), 1.0)
    step("kayıt başladı (çerçeve + durdur çubuğu)", d.recorder.active() and d.recorder.bar is not None)
    if SHOTS and d.recorder.bar is not None:
        d.recorder.bar.grab().save(os.path.join(SHOTS, "10_kayit_cubugu.png"))
    if d.recorder.bar is not None:
        from PyQt6.QtWidgets import QPushButton as _QB
        rb = d.recorder.bar
        before = [w.geometry() for w in [rb.time] + rb.findChildren(_QB)] + [rb.size()]
        rb.set_blink(False)
        pump(5)
        after = [w.geometry() for w in [rb.time] + rb.findChildren(_QB)] + [rb.size()]
        rb.set_blink(True)
        step("kayıt çubuğu: nokta sönünce hiçbir şey kaymıyor", before == after)
    loop = QEventLoop()
    QTimer.singleShot(2200, loop.quit)
    loop.exec()
    d.recorder.stop()
    loop = QEventLoop()
    d.recorder.stopped.connect(loop.quit)
    QTimer.singleShot(10000, loop.quit)
    loop.exec()
    ok = bool(saved) and os.path.getsize(saved[0]) > 1000
    step("video kaydedildi (MP4, çift boyut)", ok and not d.recorder.active())
    for pth in saved:
        os.remove(pth)
    d.recorder.start(scr, QRect(0, 0, 100, 100), 1.0)
    loop = QEventLoop()
    QTimer.singleShot(800, loop.quit)
    loop.exec()
    n_saved = len(saved)
    d.recorder.discard()
    loop = QEventLoop()
    d.recorder.stopped.connect(loop.quit)
    QTimer.singleShot(10000, loop.quit)
    loop.exec()
    vids = os.listdir(os.path.join(TMP, "videos"))
    step("vazgeç: dosya silindi", len(saved) == n_saved and not vids)

    from deltaapp.hotkeys import parse
    step("kısayol ayrıştırma", parse("Win+Shift+A") == (0x8 | 0x4, ord("A")) and parse("A") is None
         and parse("Ctrl+Alt+F5") == (0x2 | 0x1, 0x74))
    ok = d.hotkeys.set("capture", "Ctrl+Alt+Shift+F11")
    step("global kısayol kaydı (RegisterHotKey)", ok is True)
    reg = {}
    for s in ("Win+Shift+A", "Win+Shift+D", "Win+Shift+N"):
        reg[s] = d.hotkeys.set("note", s)
    print("   varsayılan kısayollar boşta mı:", reg)
    d.hotkeys.unregister_all()

    from deltaapp.dialogs import PrefsDialog, HelpDialog
    pd = PrefsDialog(win, d.hotkeys, updater=getattr(d, "updater", None))
    pd.show()
    pump(5)
    shot(pd, "07_secenekler")
    sa = pd.findChild(QScrollArea)
    if SHOTS and sa is not None:
        for i, frac in enumerate((0.33, 0.66, 1.0)):
            sa.verticalScrollBar().setValue(int(sa.verticalScrollBar().maximum() * frac))
            pump(3)
            shot(pd, f"07_secenekler_{i + 2}")
    pd.close()
    hd = HelpDialog(win)
    hd.show()
    pump(5)
    shot(hd, "08_yardim")
    hd.close()
    step("seçenekler ve yardım pencereleri açıldı", True)

    # ---- 1.1.0: OCR, PNG/JPEG/PDF, araç çubuğu konumu, tahta kısayolları, güncelleme sürüm karşılaştırması
    from PyQt6.QtCore import QEventLoop, QTimer
    from PyQt6.QtGui import QPainter, QFont
    from deltaapp import ocr, export
    oimg = QImage(560, 120, QImage.Format.Format_RGB32)
    oimg.fill(QColor("white"))
    pt = QPainter(oimg)
    f = QFont("Segoe UI")
    f.setPixelSize(30)
    pt.setFont(f)
    pt.setPen(QColor("black"))
    pt.drawText(QRect(10, 10, 540, 100), 0, "Çarşamba toplantısı 2026")
    pt.end()
    got_txt = []
    loop = QEventLoop()
    ocr.read_text(oimg, lambda x: (got_txt.append(x), loop.quit()), lambda m: (got_txt.append("HATA " + m), loop.quit()))
    QTimer.singleShot(20000, loop.quit)
    loop.exec()
    print("   OCR:", got_txt)
    step("OCR Türkçe yazıyı okur", bool(got_txt) and "Çarşamba" in got_txt[0] and "2026" in got_txt[0])

    from deltaapp.canvas import render_scene
    rimg = render_scene(win.board.scene())
    outs = {}
    for ext in ("png", "jpg", "pdf"):
        path = os.path.join(TMP, "disa." + ext)
        ok = export.save_image(rimg, path, QColor("#0f0f0f"))
        outs[ext] = ok and os.path.exists(path) and os.path.getsize(path) > 500
    with open(os.path.join(TMP, "disa.pdf"), "rb") as fh:
        is_pdf = fh.read(5) == b"%PDF-"
    step("PNG / JPEG / PDF kaydı", all(outs.values()) and is_pdf)
    multi = os.path.join(TMP, "hepsi.pdf")
    ok = export.export_pdf([rimg, rimg], multi)
    with open(multi, "rb") as fh:
        pdf = fh.read()
    step("birden çok not tek PDF (2 sayfa)", ok and pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page\r") +
         pdf.count(b"/Type /Page ") + pdf.count(b"/Type /Page>") >= 2)
    step("dışa aktarma: uzantı ekleme", export.fix_ext("a", "PDF (*.pdf)") == "a.pdf" and
         export.fix_ext("b.jpeg", "") == "b.jpeg")

    from deltaapp.toolbar import set_position
    tb = win.area.toolbar
    set_position("left")
    pump(5)
    left_ok = tb.vertical and tb.x() < 40 and tb.height() > tb.width()
    shot(win, "12_dikey_arac_cubugu")
    set_position("top")
    pump(5)
    top_ok = (not tb.vertical) and tb.y() < 40
    # sürükle-bırak: sağ kenara taşı
    mouse(tb, PRESS, QPoint(3, tb.height() // 2), L, L)
    tgt = tb.mapFromGlobal(win.area.mapToGlobal(QPoint(win.area.width() - 5, win.area.height() // 2)))
    mouse(tb, MOVE, tgt, NB, L)
    mouse(tb, REL, tgt, L, NB)
    pump(5)
    right_ok = tb.vertical and tb.x() > win.area.width() // 2
    set_position("bottom")
    pump(5)
    step("araç çubuğu: sol/üst/sürükleyip sağ/alt", left_ok and top_ok and right_ok and not tb.vertical and
         tb.y() > win.area.height() // 2)

    from deltaapp.tools import set_tool_key, reset_tool_keys, tool_key
    set_tool_key("laser", "Q")
    vkey(vp, Qt.Key.Key_Q, 0x51, "q")
    q_ok = state.tool == "laser" and b.editing_text() is None
    set_tool_key("pen", "8")      # 8 lazerdeydi: lazerden kalkmalı değil (lazer Q), pen 8 olur
    vkey(vp, Qt.Key.Key_8, 0x38, "8")
    swap_ok = state.tool == "pen" and tool_key("pen") == "8"
    set_tool_key("eraser", "8")   # aynı tuş: kalemden kaldırılır
    steal_ok = tool_key("pen") == "" and tool_key("eraser") == "8"
    reset_tool_keys()
    step("tahta kısayolları özelleştirilir (Q→lazer, çakışma kaldırılır, sıfırlanır)",
         q_ok and swap_ok and steal_ok and tool_key("pen") == "1" and tool_key("laser") == "8")
    state.set_tool("pen")

    calls = []
    real_start = d.capture.start
    d.capture.start = lambda delay=0, mode="snip": calls.append((delay, mode))
    d.handle_message("snip")
    d.capture.start = real_start
    step("--snip / \"delta alıntı\" simgesi alıntıyı başlatır", calls == [(250, "snip")])

    from deltaapp.updater import is_newer, parse_version
    step("güncelleme: sürüm karşılaştırma", is_newer("v1.2.0", "1.1.0") and not is_newer("1.1.0", "1.1.0")
         and not is_newer("1.0.9", "1.1.0") and parse_version("v2") == (2, 0, 0))

    win.quit_app()
    pump()
    fails = [n for n, ok in steps if not ok]
    print(f"\n{len(steps) - len(fails)}/{len(steps)} adım geçti")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
