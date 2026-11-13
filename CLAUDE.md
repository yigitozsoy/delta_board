# delta — Claude için proje notları

**delta**, gamma player'ın kardeşi: toplantıda bir şey anlatmak ve aklına geleni not almak için
**çizim tahtası + ekran alıntısı + ekrana çizim** aracı. Tema, renkler, başlık çubuğu, ikonlar gamma ile aynı
(`C:\Users\yigit\OneDrive\Desktop\gamma` — tasarım referansı orası; gamma'nın CLAUDE.md'sindeki çalışma tarzı
kuralları burada da geçerli: Türkçe, sade varsayılanlar, gri vurgu, mor yok, önce çalıştırıp doğrula).

- Python 3.14 · PyQt6 (Pillow isteğe bağlı) · yalnızca Windows 10/11
- Sürüm: `deltaapp/__init__.py` → `__version__`
- Repo: https://github.com/yigitozsoy/delta_board (herkese açık; sürümler Releases'ta, kurulum + zip).
  Commit kimliği yerel: `Yiğit Özsoy <yigitozsoy@users.noreply.github.com>`. Push / etiket / release öncesi onay al
  (kullanıcı "commit et githuba koy, sorma" dediyse doğrudan yap).
- Çalıştır: `python main.py` · tepside sessiz başlat: `python main.py --tray` · alıntı başlat: `--snip`
  (kurulum masaüstüne / Başlat'a "delta alıntı" kısayolu koyar, simgesi `assets/snip.ico`, `packaging/make_logo.py` üretir)
- Test: `python tests/smoke_test.py` (72 adım, gerçek 2 sn'lik ffmpeg kaydı ve gerçek OCR dahil; gerçek arayüz; `--shots KLASÖR` ekran görüntüsü alır)
  PowerShell'de Türkçe çıktı için `$env:PYTHONIOENCODING="utf-8"`.
- Lint: `python -m pyflakes deltaapp tests` temiz olmalı.
- Derleme: `powershell -ExecutionPolicy Bypass -File packaging\build.ps1` → `build\dist\delta\delta.exe` (PyInstaller,
  ffmpeg dahil) + `build\installer\delta-setup-X.exe` (Inno Setup 6, yönetici izni istemez) + taşınabilir zip.
  Paket denetimi: `delta.exe --selfcheck` (0 = tamam). Kurulum çalışan delta'yı `delta.exe --quit` ile kapatır;
  test kurulumunda `/NOQUIT=1` ver — ama delta o klasörden çalışıyorsa VERME: [InstallDelete] `_internal`'ı siler,
  kullanımdaki dosyalar yazılamaz, kurulu kopya "Failed to import encodings" hatasıyla açılmaz hale gelir. Notlar (%LOCALAPPDATA%\delta) kaldırmada silinmez.

## Klasör yapısı
```
main.py               kaynaktan başlatıcı
deltaapp/
  app.py              giriş: tek örnek (QLocalServer), sistem tepsisi, kısayolları bağlar, hata günlüğü
  window.py           ana pencere (çerçevesiz, Windows Snap — gamma ile aynı nativeEvent kodu)
  canvas.py           Board (QGraphicsView): araçlar, fare/klavye, silgi, geri al komutları, render_scene
  items.py            StrokeItem (kalem/fosforlu/şekiller), TextItem, ImageItem, LaserItem, DeltaScene, to/from_dict
  tools.py            ortak araç durumu (araç, renk, kalınlık) + araç tuşları (KEY varsayılan, prefs tool_keys)
  toolbar.py          yüzen araç çubuğu: alt/üst yatay, sol/sağ dikey (prefs toolbar_pos; sürükle-bırak, sağ tık)
  pages.py            notlar: Page (sahne + QUndoStack), NoteStore (otomatik kayıt), NotesPanel (sağ liste)
  capture.py          ekran alıntısı katmanı (ekran başına bir pencere, sahte görüntüyle test edilir; mode snip|record)
  winident.py         görev çubuğu kimliği: AppUserModel ID + pencereye ad/logo/yeniden açma komutu ("Python" yazmasın)
  ocr.py              yazı tanıma: Windows.Media.Ocr, PowerShell 5.1 + QProcess (stdin boş, iş _ACTIVE'de tutulur)
  export.py           PNG / JPEG / PDF kaydetme, tüm notlar tek PDF (QPdfWriter)
  updater.py          GitHub releases/latest denetimi (günde 1, prefs check_updates)
  pin.py              ekrana iğnelenen alıntı (PinWindow, her zaman üstte; PinManager)
  recorder.py         ekran videosu: ffmpeg gdigrab → MP4 (libx264), kırmızı çerçeve + durdur çubuğu
  annotate.py         ekrana çiz katmanı (saydam, her zaman üstte; "fareyi bırak" = WS_EX_TRANSPARENT)
  hotkeys.py          global kısayollar (RegisterHotKey + QAbstractNativeEventFilter, hwnd=NULL)
  dialogs.py          Seçenekler, Fare/klavye yardımı, Windows ile başlat (HKCU Run)
  theme.py icons.py widgets.py titlebar.py i18n.py config.py
  assets/             logo.png (beyaz Δ, arayüzde renklendirilir), logo.ico
```
Veriler: `%LOCALAPPDATA%\delta\` → `preferences.json`, `notes\<id>.json` + `<id>.png` + `index.json`,
`trash\` (silinen notlar), `error.log`. Alıntı / PNG: Resimler\delta. Video: Videolar\delta (`video_dir`).

## Tasarım kararları ve tuzaklar
- **"auto" renk**: ilk renk tema metin rengidir (koyuda beyaz, açıkta siyah); tema değişince çizimler de döner.
- **z sırası**: görsel < fosforlu < diğerleri (`items.Z_BASE` + `DeltaScene.zseq`). Yüklemede zseq geri hesaplanır.
- **Geri al**: AddCmd/RemoveCmd nesneyi sahneye *önceden* ekli/çıkarılmış alır, ilk redo atlanır.
- **Silgi** görsellere dokunmaz (alıntıyı yanlışlıkla silmesin); görsel sağ tık menüsünden / Delete ile silinir.
- **Çift tık**: ilk tıklamanın bıraktığı nokta geri alınır, sonra yazı kutusu açılır.
- **PyQt6 paintEvent'te hata = süreç çöker** (qFatal). `app._install_excepthook` bunu engeller ama testte
  excepthook yok — QPainter'a `QPoint` + float yarıçap verme (`QPointF` kullan).
- **Varsayılan kısayollar**: Win+Shift+X alıntı, Win+Shift+D ekrana çiz, Win+Shift+N hızlı not, Win+Shift+E video.
  Win+Shift+A ve Win+Shift+R bu bilgisayarda Windows tarafından alınmış (RegisterHotKey başarısız) — bu yüzden X ve E.
- **Video**: ffmpeg `imageio_ffmpeg` paketinden gelir; kayıt stdin'e "q" yazılarak durdurulur (dosya düzgün kapanır).
  Çerçeve ve çubuk `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` ile videoya girmez; H.264 çift boyut ister.
  Qt'de ekran kökeni yerel piksel, boyutlar ölçekli: fiziksel x = geo.x() + sel.x*dpr.
- **Klavye**: araçlar rakamlarda (1 kalem … 0 seç), Shift+1–7 renk (sanal tuş kodu, Türkçe düzenden bağımsız),
  atanmamış harfe basınca imlecin yerine yazı başlar (`Board.keyPressEvent` → `new_text`). Eski harf kısayolları
  (F, G, I, [ ]) Home / Ctrl+G / Ctrl+I / Ctrl+↑↓ oldu.
- **Not adı kutusu** kilitli (`titlebar.NoteTitle`): tek tıkla sürükleme pencereyi taşır, çift tık / F2 düzenler.
- Bash aracında heredoc içindeki `\` karakterleri bozulabiliyor: ters eğik çizgili düzenlemeleri Edit / Write
  ile ya da betiği dosyaya yazıp çalıştırarak yap.
- Test **gerçek tercihlere dokunmaz** (LOCALAPPDATA geçici klasör) ve kısayolları boşaltır; ekranı yakalamaz.
