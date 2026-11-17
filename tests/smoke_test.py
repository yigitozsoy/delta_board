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
    prefs.set("notes_dir", os.path.join(TMP, "notes"))       # gerçek Resimler\delta'ya dokunma
    prefs.set("snapshot_dir", os.path.join(TMP, "pictures"))
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    from deltaapp.app import DeltaApp
    from deltaapp import items as I
    from deltaapp.tools import state
    prefs.set("sidebar_visible", False)     # kapatılıp çıkılmış gibi: yine açık gelmeli
    d = DeltaApp(app)
    win = d.win
    panel_at_start = not win.panel.isHidden()
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
    vkey(vp, Qt.Key.Key_Dollar, 0x34, "$", Qt.KeyboardModifier.ShiftModifier)   # Shift+4
    step("Shift+4 kırmızı renk", state.color == "#ff453a" and state.tool == "pen")
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
    step("seçiliyken Shift+6 boyar, araç değişmez", tgt.color_name == "#ffd60a" and state.tool == tool_before)
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
    vis = b.mapToScene(b.viewport().rect()).boundingRect()
    step("alıntı yapıştırılmış gelir: seçili değil, kalem hazır, görünüm alıntıya sığar",
         im and not im[0].isSelected() and state.tool in ("pen", "hl", "line", "arrow", "rect", "ellipse")
         and vis.contains(I.exact_rect(im[0])) and b.zoom() <= 1.0 + 1e-6)

    # alıntının üstüne çiz + Ctrl+C: çizimli alıntı, alıntının kendi boyutunda kopyalanır (eski alıntı değil)
    if im:
        g = im[0]
        was_sel = g.isSelected()
        state.set_tool("pen")
        old_color = state.color
        state.set_color("#ff2020")
        r = g.mapRectToScene(QRectF(g.pixmap().rect()))
        p1 = b.mapFromScene(QPointF(r.left() + r.width() * 0.2, r.center().y()))
        p2 = b.mapFromScene(QPointF(r.left() + r.width() * 0.8, r.center().y()))
        drag(vp, [p1, (p1 + p2) / 2, p2])
        state.set_color(old_color)
        b.setFocus()
        key(vp, Qt.Key.Key_C, "", CTRL)
        cim = QApplication.clipboard().image()
        mid = QColor(cim.pixel(cim.width() // 2, cim.height() // 2)) if not cim.isNull() else QColor()
        print("   çizimli alıntı:", cim.width(), "x", cim.height(), "orta:", mid.name(), "seçiliydi:", was_sel)
        step("alıntıya çizip Ctrl+C: çizimiyle, alıntı boyutunda kopyalanır",
             cim.width() == 400 and cim.height() == 300 and mid.red() > 200 and mid.green() < 100)

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

    # pencereden "ekrana çiz": delta görev çubuğuna iner, kapanınca geri gelir
    win.bring_front()
    pump(10)
    win.request_annotate.emit()
    pump(10)
    went_down = win.isMinimized()
    from PyQt6.QtTest import QTest
    QTest.qWait(300)
    opened = ann.isVisible()
    ann.close_overlay()
    pump(10)
    step("pencereden ekrana çiz: delta iner, kapanınca geri gelir",
         went_down and opened and not win.isMinimized() and win.isVisible())

    # ekrana çiz açıkken alıntı: delta alıntıya girmesin, alıntı bitince geri gelsin
    win.request_annotate.emit()
    pump(10)
    QTest.qWait(300)
    real_start = d.capture.start
    d.capture.start = lambda delay=0, mode="snip": None
    d.handle_message("snip")
    pump(10)
    still_down = win.isMinimized() and not ann.isVisible()
    d.capture.start = real_start
    d.capture.finished.emit()
    pump(10)
    step("ekrana çiz → alıntı: delta alıntı süresince aşağıda, sonra geri gelir",
         still_down and not win.isMinimized() and win.isVisible())

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

    # ---- 1.3: hizala / diz / grupla / katman / kilit / gizle / kılavuz / ok tuşları / katmanlar paneli
    import random
    SHIFT = Qt.KeyboardModifier.ShiftModifier
    win.new_note()
    pump(5)
    b = win.board
    vp = b.viewport()
    sc = b.scene()
    b.set_zoom(1.0)
    b.centerOn(QPointF(0, 0))
    random.seed(7)
    pics = []
    for i in range(10):
        im10 = QImage(random.randint(60, 120), random.randint(40, 90), QImage.Format.Format_RGB32)
        im10.fill(QColor.fromHsv(i * 36, 160, 230))
        pics.append(b.insert_image(im10, QPointF(random.uniform(-300, 300), random.uniform(-200, 200))))
    pump()

    def rects():
        return [I.exact_rect(it) for it in pics]

    def overlap_free(rs):
        return not any(rs[i].intersects(rs[j]) for i in range(len(rs)) for j in range(i + 1, len(rs)))
    b.select_all()
    pump()
    step("seçim çubuğu: seçince görünür", b.selbar.isVisible())
    before = [it.pos() for it in pics]
    b.arrange("grid")
    rs = rects()
    xs = {round(r.center().x(), 1) for r in rs}
    ys = {round(r.center().y(), 1) for r in rs}
    step("ızgaraya diz: 10 görsel 4 sütun × 3 satır, üst üste binmez", len(xs) == 4 and len(ys) == 3 and overlap_free(rs))
    win.page.undo.undo()
    step("dizmeyi geri al: yerler geri gelir", all(it.pos() == p0 for it, p0 in zip(pics, before)))
    b.arrange("circle")
    rs = rects()
    c = QPointF(sum(r.center().x() for r in rs) / len(rs), sum(r.center().y() for r in rs) / len(rs))
    ds = [math.hypot(r.center().x() - c.x(), r.center().y() - c.y()) for r in rs]
    angs = sorted(math.atan2(r.center().y() - c.y(), r.center().x() - c.x()) for r in rs)
    steps_ = [angs[i + 1] - angs[i] for i in range(len(angs) - 1)]
    step("çembere diz: merkeze eşit uzaklık, eşit açı, çakışma yok",
         max(ds) - min(ds) < 1.0 and max(steps_) - min(steps_) < 0.01 and overlap_free(rs))
    b.arrange("row")
    rs = sorted(rects(), key=lambda r: r.left())
    gaps = [rs[i + 1].left() - rs[i].right() for i in range(len(rs) - 1)]
    step("yan yana diz: aynı hizada, eşit boşluk",
         max(gaps) - min(gaps) < 0.01 and len({round(r.center().y(), 1) for r in rs}) == 1)
    for it in pics:
        it.setPos(it.pos() + QPointF(random.uniform(-40, 40), random.uniform(-60, 60)))
    b.align("top")
    tops = {round(r.top(), 2) for r in rects()}
    b.distribute("h")
    rs = sorted(rects(), key=lambda r: r.left())
    gaps = [rs[i + 1].left() - rs[i].right() for i in range(len(rs) - 1)]
    step("üste hizala + yatayda eşit dağıt", len(tops) == 1 and max(gaps) - min(gaps) < 0.01)
    b.arrange("grid")

    # grup: biri seçilince hepsi; tek parça taşınır; çöz
    sc.clearSelection()
    pics[0].setSelected(True)
    pics[1].setSelected(True)
    vp.setFocus()
    key(vp, Qt.Key.Key_G, "", CTRL)
    gid = I.group_of(pics[0])
    sc.clearSelection()
    pics[1].setSelected(True)
    pump()
    g_sel = pics[0].isSelected() and pics[1].isSelected() and not pics[2].isSelected()
    step("Ctrl+G grupla: biri seçilince grubun tamamı seçilir", bool(gid) and I.group_of(pics[1]) == gid and g_sel)
    d0 = pics[0].pos()
    key(vp, Qt.Key.Key_Right, "")
    key(vp, Qt.Key.Key_Right, "", SHIFT)
    moved_ok = abs(pics[0].pos().x() - d0.x() - 11) < 1e-6 and pics[0].pos().y() == d0.y()
    win.page.undo.undo()
    step("ok tuşu kaydırır (Shift ×10), art arda kaydırmalar tek geri al", moved_ok and pics[0].pos() == d0)
    key(vp, Qt.Key.Key_G, "", CTRL | SHIFT)
    step("Ctrl+Shift+G grubu çözer", I.group_of(pics[0]) is None and I.group_of(pics[1]) is None)

    # katman sırası
    sc.clearSelection()
    a_, b_ = pics[2], pics[3]
    b_.setPos(a_.pos() + QPointF(20, 20))   # üst üste binsinler
    low, high = sorted((a_, b_), key=lambda i: i.zValue())
    low.setSelected(True)
    key(vp, Qt.Key.Key_PageUp, "", CTRL)
    fwd = low.zValue() > high.zValue()
    key(vp, Qt.Key.Key_PageDown, "", CTRL)
    bwd = low.zValue() < high.zValue()
    key(vp, Qt.Key.Key_PageUp, "", CTRL | SHIFT)
    front = low.zValue() == max(it.zValue() for it in sc.content_items())
    key(vp, Qt.Key.Key_PageDown, "", CTRL | SHIFT)
    back = low.zValue() == min(it.zValue() for it in sc.content_items())
    state.set_tool("pen")
    drag(vp, [b.mapFromScene(QPointF(-500, -400)), b.mapFromScene(QPointF(-450, -380))])
    pen_top = max(sc.content_items(), key=lambda i: i.zValue())
    step("katman: öne / geri / en öne / en arkaya; sonra çizilen yine en üstte",
         fwd and bwd and front and back and isinstance(pen_top, I.StrokeItem))

    # kilit + gizle + kayıt
    sc.clearSelection()
    pics[4].setSelected(True)
    key(vp, Qt.Key.Key_L, "", CTRL)
    pics[4].setSelected(True)
    locked_ok = I.is_locked(pics[4]) and not pics[4].isSelected()
    stroke = pen_top
    stroke.setSelected(False)
    b.set_locked([stroke], True)
    state.set_tool("eraser")
    spt = b.mapFromScene(stroke.sceneBoundingRect().center())
    drag(vp, [spt, spt + QPoint(3, 1)])
    survived = stroke.scene() is sc
    b.set_locked([stroke], False)
    b.set_hidden([pics[5]], True)
    dd = I.to_dict(pics[4])
    dd2 = I.to_dict(pics[5])
    back4, back5 = I.from_dict(dd), I.from_dict(dd2)
    rimg_all = render_scene(sc)
    step("kilit: seçilmez, silgi dokunmaz; gizli resme girmez; kayıtta korunur",
         locked_ok and survived and not pics[5].isVisible() and I.is_locked(back4) and not back5.isVisible()
         and rimg_all is not None)
    b.set_hidden([pics[5]], False)
    b.set_locked([pics[4]], False)
    state.set_tool("select")

    # akıllı kılavuz: sürüklerken üst kenara yapışır
    sc.clearSelection()
    ta, tb_ = pics[6], pics[7]
    ta.setPos(QPointF(2000, 2000))      # diğerlerinden uzakta: başka kenara yapışmasın
    tb_.setPos(QPointF(2250, 2210))
    b.centerOn(QPointF(2150, 2100))
    pump()
    want = I.exact_rect(ta).top()
    rb = I.exact_rect(tb_)
    start = b.mapFromScene(rb.center())
    dy = (want - rb.top()) + 4      # hedefe 4 birim kala bırak: yapışmalı
    end = b.mapFromScene(rb.center() + QPointF(-30, dy))
    mouse(vp, PRESS, start, L, L)
    mouse(vp, MOVE, start + QPoint(5, 5), NB, L)
    mouse(vp, MOVE, end, NB, L)
    guides = bool(b._guides)
    mouse(vp, REL, end, L, NB)
    pump()
    step("akıllı kılavuz: sürüklerken üst kenara yapışır, kılavuz çizgisi çıkar",
         guides and abs(I.exact_rect(tb_).top() - want) < 0.01 and not b._guides)

    # katmanlar paneli
    win.set_panel(True)
    win.panel.set_tab(1)
    pump(10)
    lp = win.layers
    lp.refresh()
    rows_ok = lp.list.count() == len(sc.content_items())
    sc.clearSelection()
    lp.list.item(0).setSelected(True)
    pump()
    top_item = max(sc.content_items(), key=lambda i: i.zValue())
    sel_sync = top_item.isSelected()
    order = b.layer_order()
    b.set_layer_order(list(reversed(order)))
    rev_ok = b.layer_order() == list(reversed(order))
    win.page.undo.undo()
    step("katmanlar paneli: satırlar, seçim eşlemesi, sıralama (+geri al)",
         rows_ok and sel_sync and rev_ok and b.layer_order() == order)
    shot(win, "13_katmanlar")
    sc.clearSelection()
    pump()
    step("seçim çubuğu: seçim kalkınca gizlenir", not b.selbar.isVisible())
    g0 = prefs.get("grid", "dots")
    key(vp, Qt.Key.Key_R, "", CTRL)
    step("Ctrl+R ızgarayı değiştirir", prefs.get("grid", "dots") != g0)
    key(vp, Qt.Key.Key_R, "", CTRL)
    key(vp, Qt.Key.Key_R, "", CTRL)
    win.panel.set_tab(0)

    # ---- paket 3: döndür / çevir / kırp / saydamlık / dolgu / yazı biçimi
    # yazı / hücre düzenleme sahnenin etkin olmasını ister: pencere arka planda kalmışsa etkinleştir
    win.activateWindow()
    win.raise_()
    try:
        QApplication.setActiveWindow(win)
    except Exception:
        pass
    pump(10)
    win.set_panel(False)
    for it in list(sc.content_items()):
        sc.removeItem(it)
    img = QImage(200, 100, QImage.Format.Format_RGB32)
    img.fill(QColor("#4caf50"))
    for x in range(100):
        for y in range(100):
            img.setPixelColor(x, y, QColor("#e53935"))      # sol yarı kırmızı
    ri = b.insert_image(img, QPointF(0, 0))
    pump()
    c0 = I.exact_rect(ri).center()
    sc.clearSelection()
    ri.setSelected(True)
    b.rotate_selection(90)
    r90 = I.exact_rect(ri)
    rot_ok = (abs(r90.width() - 100 * ri.scale()) < 0.6 and abs(r90.height() - 200 * ri.scale()) < 0.6
              and abs(r90.center().x() - c0.x()) < 0.6 and abs(r90.center().y() - c0.y()) < 0.6)
    win.page.undo.undo()
    step("90° döndür: en/boy yer değiştirir, merkez sabit (+geri al)",
         rot_ok and I.geom(ri) == (0.0, False, False) and abs(I.exact_rect(ri).width() - 200 * ri.scale()) < 0.6)
    b.flip_selection("h")
    pm = render_scene(sc, rect=I.exact_rect(ri))
    left = pm.pixelColor(5, pm.height() // 2) if pm is not None else QColor()
    step("yatay çevir: sol yarı yeşil olur", I.geom(ri)[1] and left.green() > 120 and left.red() < 120)
    win.page.undo.undo()
    # tutamaçtan sürükleyerek döndür
    b.centerOn(c0)
    pump()
    rh = b._rot_handle()
    hp = b.mapFromScene(rh[1])
    cc = b.mapFromScene(rh[2])
    tgt = QPoint(cc.x() + 200, cc.y())                     # merkezin sağı → 90°
    mouse(vp, PRESS, hp, L, L)
    mouse(vp, MOVE, hp + QPoint(3, 2), NB, L)
    mouse(vp, MOVE, tgt + QPoint(0, 3), NB, L)             # 90°'ye yakın: dik açıya yapışmalı
    mouse(vp, REL, tgt + QPoint(0, 3), L, NB)
    pump()
    step("döndürme tutamacı: sürükleyince döner, dik açıya yapışır, tek geri al",
         rh is not None and abs(I.geom(ri)[0] - 90) < 0.01 and win.page.undo.undoText() == "rotate")
    win.page.undo.undo()
    # kırp: sağ yarıyı bırak
    b.start_crop(ri)
    crop_mode = b._crop is not None and not b.selbar.isVisible()
    b._crop["rect"] = QRectF(100, 0, 100, 100)
    key(vp, Qt.Key.Key_Return)
    pump()
    er = I.exact_rect(ri)
    crop_ok = (ri.pixmap().width() == 100 and ri.pixmap().height() == 100
               and abs(er.width() - 100 * ri.scale()) < 0.6)
    # içerik yerinde kalmalı: kırpılan görselin sol kenarı eski görselin ortasında
    full_left = c0.x() - 100 * ri.scale()
    content_ok = abs(er.left() - (full_left + 100 * ri.scale())) < 0.6
    step("kırp (çift tık / Enter): kalan parça yerinde durur, boyut doğru",
         crop_mode and crop_ok and content_ok and ri.pixmap().toImage().pixelColor(5, 5).green() > 120)
    d_ = I.to_dict(ri)
    win.page.undo.undo()
    step("kırpmayı geri al: görselin tamamı geri gelir", ri.pixmap().width() == 200)
    # Esc vazgeçer
    b.start_crop(ri)
    b._crop["rect"] = QRectF(0, 0, 50, 50)
    key(vp, Qt.Key.Key_Escape)
    step("kırpmada Esc: değişiklik yok", b._crop is None and ri.pixmap().width() == 200)
    # saydamlık + dolgu + yazı biçimi + kayıt
    sc.clearSelection()
    ri.setSelected(True)
    b.rotate_selection(30)
    b.set_opacity_items([ri], 0.5)
    shp = I.StrokeItem("rect", "#e53935", 4, [QPointF(400, 0), QPointF(600, 120)])
    sc.addItem(shp)
    sc.clearSelection()
    shp.setSelected(True)
    b.fill_selection("#64b5f6")
    inside_hit = shp.shape().contains(shp.mapFromScene(QPointF(500, 60)))
    tx = b.new_text(QPointF(0, 300), "Merhaba")
    b.finish_text()
    texts = [it for it in sc.content_items() if isinstance(it, I.TextItem)]
    tx = texts[0] if texts else None
    sc.clearSelection()
    if tx is not None:
        tx.setSelected(True)
    b.toggle_text("bold")
    b.text_align("center")
    s0 = I.text_style(tx)[0] if tx is not None else 0
    b.text_size(1.2)
    pump()
    info = b.selection_info()
    bar_ok = b.selbar.b_bold.isVisible() and b.selbar.b_bold.isChecked() and not b.selbar.b_crop.isVisible()
    style_ok = tx is not None and tx.bold and tx.align == "center" and abs(I.text_style(tx)[0] - s0 * 1.2) < 0.2
    rd = [I.from_dict(I.to_dict(x)) for x in (ri, shp, tx)]
    rt_ok = (abs(I.geom(rd[0])[0] - 30) < 0.01 and abs(rd[0].opacity() - 0.5) < 0.01
             and rd[0].pixmap().width() == 200 and rd[1].fill == "#64b5f6" and rd[2].bold and rd[2].align == "center"
             and abs(I.exact_rect(rd[0]).center().x() - I.exact_rect(ri).center().x()) < 0.6)
    cr = I.from_dict(d_)
    step("saydamlık, şekil dolgusu (içi tıklanır), kalın/ortala/büyüt, seçim çubuğu düğmeleri",
         style_ok and bar_ok and info["texts"] == 1 and inside_hit and shp.fill == "#64b5f6")
    step("kayıt: döndürme / saydamlık / dolgu / yazı biçimi / kırpma korunur",
         rt_ok and cr.pixmap().width() == 100)
    sc.clearSelection()
    ri.setSelected(True)
    pump()
    shot(win, "14_dondur")

    # ---- tablo: kenarlı / kenarsız, hücreye yazma, Tab, sütun genişliği, kayıt
    for it in list(sc.content_items()):
        sc.removeItem(it)
    state.set_tool("pen")
    n0 = win.page.undo.count()
    tb = b.insert_table(2, 2)
    pump()
    ins_ok = isinstance(sc.focusItem(), I.CellEditor) and tb.edit == (0, 0) and tb.border
    for i, w_ in enumerate(["Konu", "Kim", "Tasarım", "Ayşe"]):
        if i:
            key(b, Qt.Key.Key_Tab)
        for ch in w_:
            key(b, 0, ch)
    key(b, Qt.Key.Key_Tab)              # son hücrede Tab: yeni satır
    tab_row = tb.rows == 3 and tb.edit == (2, 0)
    key(b, Qt.Key.Key_Escape)
    pump()
    step("tablo: ekle, hücrelere yaz, Tab ile geç, son hücrede yeni satır",
         ins_ok and tb.cells[:2] == [["Konu", "Kim"], ["Tasarım", "Ayşe"]] and tab_row and b.editing_text() is None
         and win.page.undo.count() == n0 + 2)
    win.page.undo.undo()
    step("tablo yazısını geri al: hücreler boşalır", tb.cells == [["", ""], ["", ""]])
    win.page.undo.redo()
    # kalem aracındayken çift tık: o hücreye yazar, nokta bırakmaz
    b.centerOn(I.exact_rect(tb).center())
    pump()
    cp = b.mapFromScene(tb.mapToScene(tb.cell_rect(1, 1).center()))
    n1 = len(sc.content_items())
    mouse(vp, PRESS, cp, L, L)
    mouse(vp, REL, cp, L, NB)
    mouse(vp, QEvent.Type.MouseButtonDblClick, cp, L, L)
    mouse(vp, REL, cp, L, NB)
    pump()
    step("tabloda çift tık (kalemde de): o hücre düzenlenir, nokta kalmaz",
         tb.edit == (1, 1) and len(sc.content_items()) == n1)
    key(b, Qt.Key.Key_Escape)
    # seç aracında sütun çizgisinden genişlik
    state.set_tool("select")
    sc.clearSelection()
    pump()
    w0 = tb.colw[0]
    bp = b.mapFromScene(tb.mapToScene(QPointF(tb.colw[0], tb.rowh[0] / 2)))
    drag(vp, [bp, bp + QPoint(2, 0), bp + QPoint(60, 0)])
    zf = b.zoom()
    wide_ok = abs(tb.colw[0] - (w0 + 60 / zf)) < 2 / zf
    win.page.undo.undo()
    step("sütun çizgisini sürükle: genişlik değişir (+geri al)", wide_ok and tb.colw[0] == w0)
    # kenarsız, başlık, satır / sütun ekle-sil, kayıt
    b.set_table_border(tb, False)
    b.table_op(tb, lambda: tb.insert_col(1))
    b.table_op(tb, lambda: tb.delete_row(0))
    rt = I.from_dict(I.to_dict(tb))
    step("kenarsız tablo; sütun ekle, satır sil; kayıtta korunur",
         not tb.border and tb.cols == 3 and tb.rows == 2 and not rt.border and rt.cells == tb.cells
         and rt.colw == tb.colw and I.exact_rect(rt).width() == I.exact_rect(tb).width())
    win.page.undo.undo()
    win.page.undo.undo()
    win.page.undo.undo()
    step("tablo işlemlerini geri al: kenarlı 3×2'ye döner", tb.border and tb.cols == 2 and tb.rows == 3)
    sc.clearSelection()
    tb.setSelected(True)
    pump()
    step("seçim çubuğu: tabloda tablo / kenar / yazı boyutu düğmeleri",
         b.selbar.b_table.isVisible() and b.selbar.b_corner.isVisible() and b.selbar.b_bigger.isVisible()
         and not b.selbar.b_bold.isVisible())
    shot(win, "15_tablo")

    # ---- yan panel, kalınlık, klasörler
    step("uygulama açılınca notlar paneli açık (kapatılıp çıkılmış olsa da)", panel_at_start)
    from deltaapp.tools import COLORS, SIZES, DEFAULT_WIDTH
    step("ana renkler beyaz, siyah, mavi, kırmızı; ince kalem",
         COLORS[:4] == ["#ffffff", "#000000", "#3ea6ff", "#ff453a"] and min(SIZES) <= 1.5
         and DEFAULT_WIDTH <= 2.5)
    from deltaapp.widthmenu import build_width_menu
    from PyQt6.QtWidgets import QMenu
    w_before = state.width
    mm = QMenu(win)
    box = build_width_menu(mm)
    box.slider.setValue(13)            # 6,5 px
    w_set = state.width
    mm.deleteLater()
    pen_btn = win.area.toolbar.tool_btns["pen"]
    step("kaleme sağ tık: kalınlık kaydırıcısı (yarım piksel adım), sağ tık menüsü bağlı",
         abs(w_set - 6.5) < 1e-6 and pen_btn.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu)
    state.set_width(w_before)

    st = win.store
    win.set_panel(True)
    win.panel.set_tab(0)
    pg = win.page
    if not pg.saved_once:
        b.new_text(QPointF(0, 0), "klasör testi")
        b.finish_text()
        st.flush()
    fid = win.panel.new_folder()
    pump(5)
    editing = win.panel.list.state() == win.panel.list.State.EditingState
    st.list_changed.emit()                      # yazarken otomatik kayıt listeyi yenilemeye kalkar: ertelenmeli
    from PyQt6.QtWidgets import QLineEdit
    eds = [w_ for w_ in win.panel.list.viewport().findChildren(QLineEdit) if w_.isVisible()]
    if eds:
        eds[0].setText("Toplantılar")
        key(eds[0], Qt.Key.Key_Return)
    pump(5)
    fid = "Toplantılar" if st.folder("Toplantılar") else fid      # klasör = diskteki alt klasör (adıyla)
    win.panel.list.moved.emit(pg.id, fid)       # sürükle-bırak sonucu
    pump(5)
    rows = [(win.panel.list.item(i).data(Qt.ItemDataRole.UserRole + 1), win.panel.list.item(i).data(Qt.ItemDataRole.UserRole))
            for i in range(win.panel.list.count())]
    st.flush()
    from deltaapp.pages import NoteStore
    s3 = NoteStore()
    step("klasör: aç, adını yaz, notu sürükleyip bırak; panelde klasörün altında, yeniden açılışta korunur",
         editing and pg.folder == fid and rows[0] == ("folder", fid) and rows[1] == ("note", pg.id)
         and s3.get(pg.id).folder == fid and s3.folder(fid)["name"] == "Toplantılar"
         and os.path.dirname(pg.file) == os.path.join(st.root, "Toplantılar") and pg.file.endswith(".delta"))
    st.set_folder_open(fid, False)
    win.panel.set_current(None)
    pump()
    hidden = all(win.panel.list.item(i).data(Qt.ItemDataRole.UserRole) != pg.id for i in range(win.panel.list.count()))
    win.panel.set_current(pg.id)
    st.set_folder_open(fid, True)
    win.new_note(fid)
    newp = win.page
    in_folder = newp.folder == fid
    win.open_page(pg)
    shot(win, "16_klasor")
    st.delete_folder(fid)
    step("klasör kapanır, klasörde yeni not; klasör silinince notlar kalır",
         hidden and in_folder and pg.folder == "" and st.get(pg.id) is not None and not st.folders)

    # ---- .delta dosyaları: Resimler\\delta (testte geçici klasör), başlıkla ad, dışarıdan açma, eski notları taşıma
    import json as _json
    import shutil as _sh
    from deltaapp import pages as PG
    from deltaapp.config import NOTES_DIR
    win.open_page(pg)
    pump()
    with open(pg.file, encoding="utf-8") as f_:
        dd = _json.load(f_)
    old_file = pg.file
    win.store.rename(pg, "Proje: Sunum")
    step(".delta dosyası: Resimler\\delta içinde, çizimler içinde; başlık değişince dosya adı da değişir",
         dd.get("format") == "delta-note" and dd.get("id") == pg.id and dd.get("items")
         and os.path.basename(pg.file) == "Proje. Sunum.delta" and not os.path.exists(old_file)
         and os.path.dirname(pg.file) == st.root)
    ext_dir = os.path.join(TMP, "masaustu")
    os.makedirs(ext_dir, exist_ok=True)
    ext = os.path.join(ext_dir, "Arkadaştan gelen.delta")
    _sh.copy2(pg.file, ext)
    ep = win.open_file(ext)
    pump()
    b.new_text(QPointF(400, 400), "ek yazı")
    b.finish_text()
    st.flush()
    with open(ext, encoding="utf-8") as f_:
        n_items = len(_json.load(f_)["items"])
    step(".delta çift tık: dışarıdaki dosya açılır, kopya kimliği yenilenir, değişiklik o dosyaya yazılır",
         ep is not None and win.page is ep and ep.id != pg.id and ep.external
         and ep.file == ext and ep.display_title() == "Proje: Sunum" and n_items == len(dd["items"]) + 1)
    # eski sürümün notu (%LOCALAPPDATA%\\delta\\notes\\<id>.json) bir kez taşınır, eskisi yedek kalır
    legacy_id = "20250101-101010-abcd"
    with open(os.path.join(NOTES_DIR, legacy_id + ".json"), "w", encoding="utf-8") as f_:
        _json.dump({"version": 1, "items": dd["items"]}, f_)
    with open(os.path.join(NOTES_DIR, "index.json"), "w", encoding="utf-8") as f_:
        _json.dump({legacy_id: {"title": "Eski not", "created": 1735725010, "modified": 1735725010}}, f_)
    root2 = os.path.join(TMP, "notes2")
    s4 = PG.NoteStore(root2)
    lp = s4.get(legacy_id)
    step("eski notlar .delta'ya taşınır (her not bir kez), eski dosya yedek kalır",
         lp is not None and os.path.exists(os.path.join(root2, "Eski not.delta"))
         and os.path.exists(os.path.join(NOTES_DIR, legacy_id + ".json")) and legacy_id in prefs.get("migrated_ids", [])
         and PG.NoteStore(os.path.join(TMP, "notes3")).get(legacy_id) is None)

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
