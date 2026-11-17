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
- Test: `python tests/smoke_test.py` (113 adım, gerçek 2 sn'lik ffmpeg kaydı ve gerçek OCR dahil; gerçek arayüz; `--shots KLASÖR` ekran görüntüsü alır)
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
  canvas.py           Board (QGraphicsView): araçlar, fare/klavye, silgi, geri al komutları, render_scene,
                      hizala/diz/grupla/kilit/katman sırası, akıllı kılavuz (drawForeground), seçim çubuğu yerleşimi
  arrange.py          saf geometri: hizala, eşit dağıt, yan yana/alt alta/ızgara/çember, akıllı kılavuz payı
  selbar.py           seçim çubuğu (seçimin üstünde; Board.avoid'e binmez): bağlama göre kırp / dolgu / yazı biçimi, döndür, saydamlık
  layers.py           Katmanlar paneli (NotesPanel'in ikinci sekmesi): küçük resim, sürükle-sırala, gizle, kilitle
  items.py            StrokeItem (kalem/fosforlu/şekiller), TextItem, ImageItem, TableItem (+CellEditor), LaserItem,
                      DeltaScene, to/from_dict; içerik türleri tek yerde: `items.CONTENT`
  widthmenu.py        kalınlık kaydırıcısı (kalem / fosforlu / şekil düğmesine sağ tık, tahtanın hızlı menüsü)
  tablepick.py        tablo ekleme seçicisi (kenarlı / kenarsız + boyut ızgarası, menüde QWidgetAction)
  tools.py            ortak araç durumu (araç, renk, kalınlık) + araç tuşları (KEY varsayılan, prefs tool_keys)
  toolbar.py          yüzen araç çubuğu: alt/üst yatay, sol/sağ dikey (prefs toolbar_pos; sürükle-bırak, sağ tık)
  pages.py            notlar: Page (sahne + QUndoStack), NoteStore (otomatik kayıt, klasörler), NotesPanel (sağ liste:
                      klasör satırları + içindeki notlar, NotesList sürükle-bırak ile klasöre taşır)
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
Notlar: `Resimler\delta\[Klasör\]Başlık.delta` (`config.notes_root`, prefs `notes_dir`). .delta = JSON
{"format": "delta-note", "version": 2, "id", "meta", "items"}; dosya adı başlıktan (`pages.safe_name`, ":" → "."),
başlık değişince dosya yeniden adlandırılır (dışarıdan açılan dosyalar hariç: `Page.external`, prefs `external_notes`).
Klasör = tek düzey alt klasör (kimliği = adı; açık/kapalı prefs `folder_open`). Çift tık: kurulum `.delta` →
`delta.exe "%1"` kaydeder; çalışan delta'ya "open:<yol>" iletilir (`MainWindow.open_file`).
`%LOCALAPPDATA%\delta\` → `preferences.json`, `thumbs\<id>.png`, `notes_cache.json` (yol → boyut/tarih/özet:
açılışta her dosyayı okumamak için), `trash\` (silinen notlar), `error.log`, `notes\` (1.2'nin eski notları:
her not bir kez .delta'ya taşınır — `NoteStore.migrate_legacy`, prefs `migrated_ids` — silinmez).
Alıntı / PNG: Resimler\delta. Video: Videolar\delta (`video_dir`).

## Tasarım kararları ve tuzaklar
- **Renkler (1.3)**: COLORS = beyaz, siyah, mavi, kırmızı, yeşil, sarı, turuncu (Shift+1–7). Varsayılan kalem
  rengi temaya göre beyaz / siyah (`tools.default_color`). Eski notlardaki "auto" renk yine temaya göre çizilir.
  Kalınlıklar ince: SIZES 1,5 / 2,5 / 5 (varsayılan 2,5); yazı boyutu `text_px` = 19 + 1,75 × kalınlık.
- **Yan panel** uygulama açılınca hep açık (`sidebar_visible` yalnızca oturum içinde).
- **Alıntı → delta** (`MainWindow.receive_image`): görsel gerçek boyutunda (1/dpr), seçili değil, görünüm
  `Board.fit_to` ile ona sığar, çizim aracı değilse kalem seçilir. Hiçbir şey seçili değilken notta tek görsel varsa
  Ctrl+C onu üstündeki çizimlerle, kendi boyutunda kopyalar.
- **Kapanışta çökme (0xC0000409)**: seçili bir şey varken çıkınca sahneler silinirken gelen selectionChanged
  yarı silinmiş Board'a ulaşıyordu → `DeltaApp.quit` önce `Board.detach()` çağırır (sinyalleri bırakır).
- **Test** not klasörünü (`notes_dir`) ve alıntı klasörünü geçici klasöre alır; gerçek Resimler\delta'ya yazmaz.
  Yazı / hücre düzenleme sahnenin etkin olmasını ister: testte pencere `QApplication.setActiveWindow` ile etkinleşir.
- **Klasör listesi**: liste tıklama / düzenleme işleyicisi içinden `refresh` çağırma (öğe silinir → çökme);
  `QTimer.singleShot(0, …)` ile ertele. Sürükle-bırakta drop eylemi CopyAction yapılır ki Qt kaynak satırı silmesin.
- **z sırası**: görsel < fosforlu < diğerleri (`items.Z_BASE` + `DeltaScene.zseq`). Yüklemede zseq geri hesaplanır.
- **Grup / kilit / gizli**: nesnede `group_id` / `locked` / görünürlük (`items.set_group/set_locked/set_hidden`),
  kayıtta "g" / "lk" / "hd". Öznitelik adı `group` OLAMAZ: QGraphicsItem.group() yöntemiyle çakışır (her şey "grupta" sanılır).
  Gruptan biri seçilince `Board._on_scene_selection` tamamını seçer; kilitli nesne fare almaz (lastik bant üstünden geçer).
- **Katman sırası**: "en öne" = `DeltaScene.front_z()` (0 katmanında zseq) → sonra çizilen yine üstte kalır;
  bir adım / panelden sıralama mevcut z değerlerini yeniden dağıtır (görsel < fosforlu < diğerleri kuralı bozulmaz).
- **Döndür / çevir (1.3)**: `transform()` içinde, yerel merkez `gc` etrafında (öznitelikler rot / fh / fv; kayıtta
  "r" / "gc" / "fh" / "fv"). Ölçek eskisi gibi sol üst kökenli → boyutlandır / diz / kopyala kodu değişmedi.
  `items.set_geom` görsel merkezi sabit tutar; `geo_state` / `set_geo_state` birebir geri yükler (GeoCmd).
  Döndürülmüş görselin köşeden boyutlandırması `Board._resize_to` içindeki genel yoldan (karşı köşe sabit).
- **Kırp**: ImageItem.full (özgün) + crop (QRect, kayıtta "cr"); `set_crop_keep` içeriği sahnede yerinde tutar.
  Kırpma modu `Board._crop`; çizimi drawForeground'da, sayfa değişince uygulanır. Saydamlık "op", dolgu "f",
  yazı "b" / "it" / "u" / "al" (ortala / sağa yaslada metin genişliği sabitlenir: `TextItem.apply_layout`).
- **Tablo**: TableItem hücre yazılarını kendisi çizer; düzenlerken hücrenin üstüne çocuk `CellEditor` konur
  (Board.editing_text onu da sayar). Tab'ı QGraphicsScene odak zincirine kaptırmamak için `Board.event` yakalar.
  Bir düzenleme oturumu (Tab'la eklenen satır dahil) tek TableCmd (önceki / sonraki `state()`); yapı işlemleri
  `Board.table_op`. Kayıt: "cells", "cw", "nb" (kenarsız), "nh" (başlıksız). Silgi tabloya dokunmaz (görsel gibi).
- **QGraphicsItem.setBrush** `Qt.BrushStyle` almaz → `QBrush(Qt.BrushStyle.NoBrush)`.
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
- **Klavye (1.3)**: ızgara Ctrl+R (Ctrl+G artık grupla), Ctrl+Shift+G çöz, Ctrl+L kilitle, Ctrl+PgUp/PgDown katman,
  oklar seçileni kaydırır (art arda kaydırmalar `TransformCmd.merge_key` ile tek geri al), Ctrl+Shift+K katmanlar.
- **Klavye**: araçlar rakamlarda (1 kalem … 0 seç), Shift+1–7 renk (sanal tuş kodu, Türkçe düzenden bağımsız),
  atanmamış harfe basınca imlecin yerine yazı başlar (`Board.keyPressEvent` → `new_text`). Eski harf kısayolları
  (F, G, I, [ ]) Home / Ctrl+G / Ctrl+I / Ctrl+↑↓ oldu.
- **Not adı kutusu** kilitli (`titlebar.NoteTitle`): tek tıkla sürükleme pencereyi taşır, çift tık / F2 düzenler.
- Bash aracında heredoc içindeki `\` karakterleri bozulabiliyor: ters eğik çizgili düzenlemeleri Edit / Write
  ile ya da betiği dosyaya yazıp çalıştırarak yap.
- Test **gerçek tercihlere dokunmaz** (LOCALAPPDATA geçici klasör) ve kısayolları boşaltır; ekranı yakalamaz.
