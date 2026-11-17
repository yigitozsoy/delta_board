# delta
## Çalıştırma
```
pip install -r requirements.txt
python main.py
```
Toplantıda bir şey anlatmak, aklına geleni hemen not almak için çizim tahtası + ekran alıntısı aracı.
gamma player ile aynı görünüm (AMOLED siyah, gri vurgu, 10 tema).

## Ne yapar
- **Sonsuz tuval**: kalem, fosforlu kalem, lazer işaretçi, silgi, çizgi / ok / dikdörtgen / elips, yazı, görsel, tablo
- **Notlar**: her not otomatik kaydedilir, sağdaki listeden geçilir (uygulama açılınca liste açık gelir),
  ilk yazı başlık olur; notları **klasörlere** ayır (klasör düğmesi, sürükle-bırak ya da sağ tık › Klasöre taşı)
- **.delta dosyaları**: her not `Resimler\delta` içinde başlığıyla bir `.delta` dosyasıdır (.psd gibi: çizimler,
  yazılar, görseller, katmanlar içinde); klasörler gerçek alt klasörlerdir. `.delta`'ya çift tıklayınca delta'da
  düzenlenebilir açılır — başka yerdeki bir dosya da açılır, değişiklikler o dosyaya kaydedilir. OneDrive ile eşitlenir.
  Eski sürümün notları ilk açılışta bir kez taşınır (eskiler yedek olarak kalır)
- **Ekran alıntısı** (Win+Shift+X): alanı seç → panoya kopyalanır; "delta'da çiz" ile alıntı yapıştırılmış gelir
  (kendi boyutunda, kalem hazır — boyutlandırmaya gerek yok, tekerlekle yakınlaş); Ctrl+C çizimli alıntıyı kopyalar
- **Ekrana çiz** (Win+Shift+D): paylaşılan ekranın üstüne çiz / lazerle göster; "fareyi bırak" ile çizimler kalır
- **İğnele** (alıntı çubuğu / Ctrl+T / F3): alıntı ekranda üstte kalır; sürükle taşı, tekerlek büyüt, çift tık kapat
- **Ekran videosu** (Win+Shift+E): alanı seç → "Kaydı başlat"; aynı kısayol ya da "Kaydı durdur" bitirir, MP4 Videolar\delta'ya gider
- **Hızlı not** (Win+Shift+N): delta öne gelir, boş not açılır, imleç yazmaya hazır
- **Hızlı yazı**: tahtada bir harfe bas, imlecin olduğu yere hemen yazı başlar
- **Metni kopyala (OCR)**: alıntıdaki / görseldeki yazıyı okuyup panoya kopyalar (Windows'un kendi tanıması, Türkçe)
- **Kaydet**: PNG, JPEG ya da PDF; tüm notları tek PDF yapabilirsin
- **Düzenle**: birden çok şey seçince üstte seçim çubuğu çıkar — hizala, eşit aralıkla dağıt, yan yana / alt alta /
  ızgaraya / çembere diz (örneğin 10 fotoğrafı tek tıkla), görselleri aynı boya getir, grupla, kilitle
- **Akıllı kılavuzlar**: sürüklerken başka bir nesnenin kenarına / ortasına hizalanınca çizgi çıkar ve yapışır (Alt: kapalı)
- **Döndür / kırp / biçim**: seçili nesnenin üstündeki yuvarlak tutamaçla döndür (Shift: 15°), yatay / dikey çevir;
  görsele çift tıkla kırp; saydamlık; dikdörtgen / elipse dolgu rengi; yazıda kalın, italik, altı çizili, büyüt / küçült, hizala
- **Tablo**: araç çubuğundaki tablo düğmesi ya da sağ tık › Tablo ekle; boyutu fareyle seç, kenarlı ya da kenarsız
  (dış çizgisiz). Hücreye çift tıkla yaz, Tab sonraki hücreye geçer (son hücrede yeni satır açar); sütun çizgisini
  sürükleyerek genişlet; sağ tıkla satır / sütun ekle-sil, başlık satırı
- **Katmanlar**: sağ panelde Notlar | Katmanlar; nesneler küçük resimleriyle, sürükleyerek sırala, gizle, kilitle;
  öne getir / geri gönder
- **Özelleştirme**: araç tuşları değiştirilebilir; araç çubuğu alta, üste ya da dikey olarak sola / sağa alınabilir
- **Güncelleme**: yeni sürüm çıkınca haber verir (Seçenekler'den kapatılabilir)

## Klavye (tahta)
| | |
|---|---|
| 1 · 2 | Kalem · fosforlu |
| 3 · 4 · 5 · 6 | Ok · çizgi · dikdörtgen · elips |
| 7 · 8 · 9 · 0 | Yazı · lazer · silgi · seç |
| Harfler | İmlecin yerine hemen yazı |
| Shift+1 – 7 | Beyaz · siyah · mavi · kırmızı · yeşil · sarı · turuncu |
| Ctrl+↑ / ↓ · Ctrl+I · Home | Kalınlık · görsel ekle · hepsini sığdır |
| ← ↑ → ↓ (Shift: ×10) | Seçileni kaydır |
| Ctrl+G · Ctrl+Shift+G · Ctrl+L | Grupla · grubu çöz · kilitle |
| Ctrl+PgUp / PgDown (Shift: en öne / en arkaya) | Katman sırası |
| Ctrl+Shift+K · Ctrl+R | Katmanlar paneli · noktalı / kareli / düz arka plan |

Araç tuşları Seçenekler › Tahta kısayolları'ndan değiştirilebilir.

## Fare
| | |
|---|---|
| Sol sürükle | Çiz |
| Sağ basılı sürükle | Sil |
| Sağ kısa tık | Hızlı menü |
| Orta sürükle / Boşluk+sol | Kaydır |
| Tekerlek · Alt+tekerlek | Yakınlaştır · kalınlık |
| Kalem düğmesine sağ tık | Kalınlık kaydırıcısı (tahtada sağ kısa tıkta da) |
| Shift+sol · Ctrl+sol | Düz çizgi · seç / taşı |
| Çift tık | Yazı yaz (seç aracında görsele: kırp · tabloda: hücreye yaz) |
| Yan tuşlar | Geri al / yinele |

Tüm kontroller uygulamada **F1**.

## Lisans

Geliştirici: **Yiğit Özsoy** · [GPL-3.0](LICENSE). delta; [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) (GPL),
[FFmpeg](https://ffmpeg.org/) (GPL derlemesi, imageio-ffmpeg üzerinden, ekran videosu için) ve isteğe bağlı Pillow kullanır.
