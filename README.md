# CronBI · Ekip puantajı

Plane'deki görevlerden her çalışanın aylık efor dökümünü üretir ve şifreli bir GitHub Pages sayfası olarak yayınlar.
Yönetici her ayın 1'i sabahı tek adresten, kullanıcı adı ve şifreyle girip geçen ayın kesinleşmiş dökümünü görür.

## Nasıl çalışır

- **Her gece 00:30** (İstanbul) Plane'den görevler okunur, sayfa yeniden üretilir. Ayın **son 2 günü** 12:00 ve 17:30'da da güncellenir.
- **Ayın 1'i 00:30'da** geçen ay kesinleşir; kesinleşen ay bir daha değişmez.
- Bir görev atandığı herkese tam süresiyle sayılır. Ay: Done değilse sayılmaz → bitiş tarihinin ayı → bitiş yoksa Done'a çekildiği gün.
- Süre boy etiketinden (XS 3 saat · SM 6,5 saat · MD 1,5 gün · LG 2,5 gün · XL 3,5 gün) ya da toplantı gün etiketinden (T1–T4) gelir; ikisi de yoksa görev listede görünür, toplama girmez.

## Güvenlik

- Repo herkese açıktır ama **veri yoktur**: sayfa ve kesinleşmiş aylar (`arsiv` dalı) kullanıcı adı + şifreden türetilen anahtarla
  (PBKDF2-SHA256, 600 000 tur · AES-256-GCM) şifrelenir. Yayından önce sızıntı denetimi düz veri bulursa yayın durur.
- Sayfa yalnız kendi betiğini çalıştırır (içerik güvenlik politikası); yazı tipleri sayfanın içindedir, dışarıya istek gitmez.
- Çalışma günlükleri herkese açık olduğu için betik kişi adı ve gün sayısı yazdırmaz.
- Plane yalnız okunur.

## Gizli değişkenler (Settings → Secrets and variables → Actions)

| Ad | İçerik |
|---|---|
| `PLANE_API_KEY` | Plane API anahtarı |
| `PANO_KULLANICI`, `PANO_SIFRE` | Sayfanın kullanıcı adı ve şifresi (arşiv de bununla kilitlenir) |
| `PANO_KISILER` | Panoda görünmeyecek hesaplar ve elle ad düzeltmeleri (JSON); verilmemişse çalışma durur |

**Şifre değiştirmek:** eski kimliği geçici olarak `ESKI_PANO_KULLANICI` / `ESKI_PANO_SIFRE` olarak girin, yenisini
`PANO_KULLANICI` / `PANO_SIFRE` olarak güncelleyin, Actions'ta "Şifre yenile" iş akışını çalıştırın, ardından "Ekip puantajı"nı elle
çalıştırın (yoksa sayfa ilk geceye kadar eski şifreyle açılır), sonra `ESKI_*` değişkenlerini silin.

## Yerelde

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -t .
.venv/bin/python -m pano.cli --anahtar-dosyasi <PLANE_API_KEY satırı olan dosya> --ay 2026-11
.venv/bin/python -m pano.sayfa        # site/index.html (kilitsiz, yalnız yerel bakış için)
```

Yazı tipleri (Archivo, Source Sans 3, IBM Plex Mono) SIL Open Font License ile dağıtılır; lisanslar `pano/yazi/` altında.
