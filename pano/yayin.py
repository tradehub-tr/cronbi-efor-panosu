"""Otomatik çalışma (GitHub Actions): kilitli arşivi aç → Plane'i çek, kesinleştir → yeni ayı kilitle → kilitli sayfa.

  python -m pano.yayin --kilitli-arsiv arsiv-dali --site site [--tetik "<cron>"]
  python -m pano.yayin --kilitli-arsiv arsiv-dali --sifre-yenile

Ortam: PLANE_API_KEY, PANO_KULLANICI, PANO_SIFRE, PANO_KISILER; şifre yenilemede ayrıca ESKI_PANO_KULLANICI, ESKI_PANO_SIFRE.
Günlük herkese açıktır (repo herkese açık): kişi adı, görev, gün sayısı yazılmaz.
Çıkış kodu 0 dışındaysa sayfa ve arşiv yazılmaz; yayındaki son sayfa kalır.
"""

import argparse
import json
import os
import re
import sys
import tempfile
from calendar import monthrange
from pathlib import Path

from . import ayarlar, cli, hesap, sayfa, sifre

# Ayın son 2 günü 12:00 ve 17:30 (İstanbul) ek güncelleme; GitHub takviminde "son 2 gün" yok, 27–31 çalışır
# (Şubat 27 artık olmayan yılda son iki günden biri) ve gün burada denetlenir (karar 10). Ayın 1'inde de
# çalışır: 00:30 kesinleşmesi düştüyse aynı gün yeniden dener. Gece 00:30 çalışması her gün tam çalışır.
EK_TETIKLER = {"0 9 1,27-31 * *", "30 14 1,27-31 * *"}
# Yayınlanan sayfada ya da kilitli arşivde bunlardan biri görünürse veri düz kalmış demektir.
DUZ_VERI_IZI = ('"kisiler"', '"efor"', '"sayilan"', "MOGEM-")
PAKET_ALANLARI = {"v", "tur", "iv", "veri"}


def son_iki_gun(simdi):
    yerel = simdi.astimezone(ayarlar.SAAT_DILIMI)
    return yerel.day >= monthrange(yerel.year, yerel.month)[1] - 1


def _kimlik(on_ek=""):
    return os.environ.get(f"{on_ek}PANO_KULLANICI"), os.environ.get(
        f"{on_ek}PANO_SIFRE"
    )


def _kilitli_mi(metin, html):
    """Sayfanın veri bloğu yalnız {"kilitli": paket}; arşiv dosyası yalnız paket alanları taşımalı."""
    if html:
        m = re.search(
            r'<script id="veri" type="application/json">(.*?)</script>',
            metin,
            re.DOTALL,
        )
        if not m:
            return False
        nesne = json.loads(m.group(1))
        if set(nesne) != {"kilitli"}:
            return False
        nesne = nesne["kilitli"]
    else:
        nesne = json.loads(metin)
    return set(nesne) == PAKET_ALANLARI


def sizinti_denetimi(*dosyalar):
    """Kilitlenmemiş ya da düz veri izi taşıyan dosyaların listesi (boş liste = temiz)."""
    kirli = []
    for p in map(Path, dosyalar):
        metin = p.read_text(encoding="utf-8")
        if not _kilitli_mi(metin, p.suffix == ".html") or any(
            iz in metin for iz in DUZ_VERI_IZI
        ):
            kirli.append(str(p))
    return kirli


def sifre_yenile(kilitli):
    eski = sifre.anahtar(*_kimlik("ESKI_"), "arsiv")
    yeni = sifre.anahtar(*_kimlik(), "arsiv")
    dosyalar = sorted(Path(kilitli).glob("????-??.json"))
    acik = {
        p: sifre.json_ac(json.loads(p.read_text(encoding="utf-8")), eski)
        for p in dosyalar
    }  # önce hepsi açılır
    for p, dokum in acik.items():
        p.write_text(json.dumps(sifre.json_kilitle(dokum, yeni)), encoding="utf-8")
    print(f"Arşiv yeni şifreyle kilitlendi · {len(dosyalar)} ay")
    return 0


def calis(a):
    simdi = cli._simdi(a.simdi)
    geciken = hesap.kesinlesecek_aylar(
        simdi, {p.stem for p in Path(a.kilitli_arsiv).glob("????-??.json")}
    )
    if a.tetik in EK_TETIKLER and not son_iki_gun(simdi) and not geciken:
        print(
            "Bugün ayın son iki günü değil, kesinleşmesi geciken ay yok; ek güncelleme yapılmadı."
        )
        return 0
    sayfa_anahtari = sifre.anahtar(*_kimlik(), "sayfa")
    arsiv_anahtari = sifre.anahtar(*_kimlik(), "arsiv")
    kilitli = Path(a.kilitli_arsiv)
    kilitli.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as t:
        duz, canli = Path(t, "arsiv"), Path(t, "canli")
        duz.mkdir()
        for p in sorted(kilitli.glob("????-??.json")):
            dokum = sifre.json_ac(
                json.loads(p.read_text(encoding="utf-8")), arsiv_anahtari
            )
            (duz / p.name).write_text(
                json.dumps(dokum, ensure_ascii=False), encoding="utf-8"
            )
        arg = ["--arsiv", str(duz), "--cikti", str(canli), "--sessiz"]
        arg += ["--cekim", a.cekim] if a.cekim else []
        arg += ["--simdi", a.simdi] if a.simdi else []
        kod = cli.main(arg)
        if kod:
            return kod
        yeni = []
        for p in sorted(duz.glob("????-??.json")):
            hedef = kilitli / p.name
            if not hedef.exists():  # kesinleşmiş ay bir daha yazılmaz
                dokum = json.loads(p.read_text(encoding="utf-8"))
                hedef.write_text(
                    json.dumps(sifre.json_kilitle(dokum, arsiv_anahtari)),
                    encoding="utf-8",
                )
                yeni.append(p.stem)
        site, aylar = sayfa.uret(duz, canli, a.site, sayfa_anahtari)
    sizan = sizinti_denetimi(site, *kilitli.glob("????-??.json"))
    if sizan:
        site.unlink()
        print(
            f"Düz veri izi bulundu, yayın durduruldu: {', '.join(sizan)}",
            file=sys.stderr,
        )
        return 5
    print(
        f"Güncellendi · yayında {len(aylar)} ay · yeni kesinleşen: {', '.join(yeni) or 'yok'}"
    )
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--kilitli-arsiv",
        required=True,
        help="kilitli ay dosyalarının klasörü (arşiv dalı)",
    )
    ap.add_argument("--site", default="site")
    ap.add_argument(
        "--tetik",
        default="",
        help="GitHub'ın çalışmayı başlatan takvim satırı (github.event.schedule)",
    )
    ap.add_argument("--cekim", help="test: Plane yerine kayıtlı çekim")
    ap.add_argument("--simdi", help="test: ISO zaman")
    ap.add_argument(
        "--sifre-yenile",
        action="store_true",
        help="arşivi ESKI_* kimliğinden yeni kimliğe taşı",
    )
    a = ap.parse_args(argv)
    try:
        return sifre_yenile(a.kilitli_arsiv) if a.sifre_yenile else calis(a)
    except sifre.SifreHatasi as e:
        print(f"Kilit açılamadı: {e}. Hiçbir dosya yazılmadı.", file=sys.stderr)
        return 6


if __name__ == "__main__":
    sys.exit(main())
