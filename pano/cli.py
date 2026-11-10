"""Komut satırı: Plane'i çeker, eksik ayları kesinleştirir, açık ayın dökümünü yazar.

  python3 -m pano.cli                       # şimdiye göre: kesinleşecekleri kesinleştir + açık ayı üret
  python3 -m pano.cli --ay 2026-11          # yalnız o (açık) ayın canlı dökümü
  python3 -m pano.cli --cekim ham.json      # Plane yerine kayıtlı çekim (test, regresyon)

Çıkış kodu: 0 tamam · 2 Plane'e ulaşılamadı · 3 veri beklenmeyen biçimde · 4 geçersiz istek.
0 dışındaki her durumda hiçbir dosya yazılmaz: yayındaki son sayfa kalır.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from . import ayarlar, hesap, plane
from .arsiv import Arsiv


def _ozet(dokum, sessiz=False):
    if sessiz:  # GitHub Actions günlüğü herkese açık: kişi adı ve gün yazılmaz
        return f"{dokum['ay']} · {dokum['durum']} · {len(dokum['kisiler'])} kişi · {len(dokum['uyarilar'])} uyarı"
    satirlar = [f"{dokum['ay']} · {dokum['durum']} · iş günü {dokum['is_gunu']}"]
    for k in dokum["kisiler"].values():
        satirlar.append(
            f"  {k['isim']:<20} {Decimal(k['efor']):>5} gün · sayılan {len(k['sayilan'])}"
            f" · geç {len(k['gec'])} · süresiz {len(k['bos'])} · Done değil {len(k['acik'])}"
        )
    satirlar += [f"  ! {u['kod']} {u['neden']}" for u in dokum["uyarilar"]]
    return "\n".join(satirlar)


def _simdi(deger):
    if not deger:
        return datetime.now(UTC)
    t = datetime.fromisoformat(deger)
    return (
        t if t.tzinfo else t.replace(tzinfo=ayarlar.SAAT_DILIMI)
    )  # saat dilimsiz değer İstanbul saatidir


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--ay", help="YYYY-MM; verilirse yalnız o açık ayın canlı dökümü üretilir"
    )
    ap.add_argument(
        "--cekim", help="Plane yerine okunacak çekim dosyası (plane.cek çıktısı)"
    )
    ap.add_argument("--arsiv", default="veri/arsiv", help="kesinleşmiş aylar klasörü")
    ap.add_argument(
        "--cikti", default="veri/canli", help="açık ay dökümünün yazılacağı klasör"
    )
    ap.add_argument(
        "--simdi", help="ISO zaman (test); saat dilimi yoksa İstanbul; varsayılan şimdi"
    )
    ap.add_argument(
        "--anahtar-dosyasi",
        help="yerel: PLANE_API_KEY satırı olan dosya (GitHub'da ortam değişkeni)",
    )
    ap.add_argument(
        "--cekim-kaydet",
        help="Plane çekimini bu dosyaya da yaz (git dışı veri/ altına)",
    )
    ap.add_argument(
        "--sessiz", action="store_true", help="günlüğe kişi adı ve gün yazma (yayın)"
    )
    a = ap.parse_args(argv)

    arsiv = Arsiv(a.arsiv)
    kayitli = arsiv.oku()
    if a.ay and (a.ay < ayarlar.BASLANGIC_AYI or a.ay in kayitli):
        neden = (
            "panonun başlangıç ayından önce"
            if a.ay < ayarlar.BASLANGIC_AYI
            else "kesinleşmiş"
        )
        print(f"{a.ay} {neden}; canlı döküm üretilmez.", file=sys.stderr)
        return 4

    try:
        if a.cekim:
            cekim = json.loads(Path(a.cekim).read_text(encoding="utf-8"))
        else:
            cekim = plane.cek(
                plane.anahtar_dosyadan(a.anahtar_dosyasi) if a.anahtar_dosyasi else None
            )
        gorevler = hesap.gorevleri_kur(cekim)
    except plane.PlaneHatasi as e:
        print(f"Plane'e ulaşılamadı: {e}. Hiçbir dosya yazılmadı.", file=sys.stderr)
        return 2
    except hesap.VeriHatasi as e:
        print(
            f"Plane verisi beklenmeyen biçimde: {e}. Hiçbir dosya yazılmadı.",
            file=sys.stderr,
        )
        return 3
    if a.cekim_kaydet and not a.cekim:
        Path(a.cekim_kaydet).write_text(
            json.dumps(cekim, ensure_ascii=False), encoding="utf-8"
        )

    uyeler = cekim["uyeler"]
    simdi = _simdi(a.simdi)
    zaman = simdi.astimezone(ayarlar.SAAT_DILIMI).isoformat(timespec="minutes")
    canli = Path(a.cikti)

    if a.ay:
        acik = [a.ay]
    else:
        for ay in hesap.kesinlesecek_aylar(simdi, kayitli):
            dokum = hesap.ay_dokumu(gorevler, ay, kayitli, uyeler) | {
                "durum": "kesin",
                "zaman": zaman,
                "planlanan": hesap.kesinlesme_ani(ay).isoformat(timespec="minutes"),
            }
            arsiv.yaz(dokum)
            kayitli[ay] = dokum
            (canli / f"{ay}.json").unlink(
                missing_ok=True
            )  # kesinleşen ayın canlı kopyası kalmaz
            print(_ozet(dokum, a.sessiz))
        yerel = f"{simdi.astimezone(ayarlar.SAAT_DILIMI):%Y-%m}"
        acik = (
            [yerel] if yerel >= ayarlar.BASLANGIC_AYI and yerel not in kayitli else []
        )

    canli.mkdir(parents=True, exist_ok=True)
    for ay in acik:
        dokum = hesap.ay_dokumu(gorevler, ay, kayitli, uyeler) | {
            "durum": "canli",
            "zaman": zaman,
            "cekim": cekim.get("cekim"),
        }
        (canli / f"{ay}.json").write_text(
            json.dumps(dokum, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(_ozet(dokum, a.sessiz))
    return 0


if __name__ == "__main__":
    sys.exit(main())
