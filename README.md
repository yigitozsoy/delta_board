# delta
## Çalıştırma
```
pip install -r requirements.txt
python main.py
```
Toplantıda bir şey anlatmak, aklına geleni hemen not almak için çizim tahtası + ekran alıntısı aracı.
gamma player ile aynı görünüm (AMOLED siyah, gri vurgu, 10 tema).

## Ne yapar
- **Sonsuz tuval**: kalem, fosforlu kalem, lazer işaretçi, silgi, çizgi / ok / dikdörtgen / elips, yazı, görsel
- **Notlar**: her not otomatik kaydedilir, sağdaki listeden geçilir, ilk yazı başlık olur
- **Ekran alıntısı** (Win+Shift+X): alanı seç → panoya kopyalanır; "delta'da çiz" ile üstüne çiz
- **Ekrana çiz** (Win+Shift+D): paylaşılan ekranın üstüne çiz / lazerle göster; "fareyi bırak" ile çizimler kalır
- **İğnele** (alıntı çubuğu / Ctrl+T / F3): alıntı ekranda üstte kalır; sürükle taşı, tekerlek büyüt, çift tık kapat
- **Ekran videosu** (Win+Shift+E): alanı seç → "Kaydı başlat"; aynı kısayol ya da "Kaydı durdur" bitirir, MP4 Videolar\delta'ya gider
- **Hızlı not** (Win+Shift+N): delta öne gelir, boş not açılır, imleç yazmaya hazır
- **Hızlı yazı**: tahtada bir harfe bas, imlecin olduğu yere hemen yazı başlar
- **Metni kopyala (OCR)**: alıntıdaki / görseldeki yazıyı okuyup panoya kopyalar (Windows'un kendi tanıması, Türkçe)
- **Kaydet**: PNG, JPEG ya da PDF; tüm notları tek PDF yapabilirsin
- **Özelleştirme**: araç tuşları değiştirilebilir; araç çubuğu alta, üste ya da dikey olarak sola / sağa alınabilir
- **Güncelleme**: yeni sürüm çıkınca haber verir (Seçenekler'den kapatılabilir)

## Klavye (tahta)
| | |
|---|---|
| 1 · 2 | Kalem · fosforlu |
| 3 · 4 · 5 · 6 | Ok · çizgi · dikdörtgen · elips |
| 7 · 8 · 9 · 0 | Yazı · lazer · silgi · seç |
| Harfler | İmlecin yerine hemen yazı |
| Shift+1 – 7 | Renkler |
| Ctrl+↑ / ↓ · Ctrl+I · Home | Kalınlık · görsel ekle · hepsini sığdır |

Araç tuşları Seçenekler › Tahta kısayolları'ndan değiştirilebilir.

## Fare
| | |
|---|---|
| Sol sürükle | Çiz |
| Sağ basılı sürükle | Sil |
| Sağ kısa tık | Hızlı menü |
| Orta sürükle / Boşluk+sol | Kaydır |
| Tekerlek · Alt+tekerlek | Yakınlaştır · kalınlık |
| Shift+sol · Ctrl+sol | Düz çizgi · seç / taşı |
| Çift tık | Yazı yaz |
| Yan tuşlar | Geri al / yinele |

Tüm kontroller uygulamada **F1**.

## Lisans

Geliştirici: **Yiğit Özsoy** · [GPL-3.0](LICENSE). delta; [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) (GPL),
[FFmpeg](https://ffmpeg.org/) (GPL derlemesi, imageio-ffmpeg üzerinden, ekran videosu için) ve isteğe bağlı Pillow kullanır.
