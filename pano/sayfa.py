"""Kesinleşmiş ve canlı dökümlerden panonun HTML sayfasını üretir.

  python3 -m pano.sayfa --arsiv veri/arsiv --canli veri/canli --cikti site

Veri sayfaya JSON olarak gömülür, sayfa tarayıcıda çizer. --kilit ile veri şifreli gömülür;
tarayıcı doğru kullanıcı adı ve şifreyle açar (pano/sifre.py). Yazı tipleri sayfanın içindedir.
"""

import argparse
import base64
import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from . import ayarlar, sifre

SABLON = Path(__file__).with_name("sablon.html")
YAZI = Path(__file__).with_name("yazi")


def _kucuk(s):
    return s.replace("I", "ı").replace("İ", "i").lower()


def _buyuk_harf(s):
    return {"i": "İ", "ı": "I"}.get(s[0], s[0].upper()) + s[1:] if s else s


def gorunen_ad(uid, isim, ad):
    """Plane'deki ad Türkçe kurala göre düzeltilir: "deniz yıldırım" → "Deniz Yıldırım" (karar 29).

    Tireli adın her parçası büyük harfle başlar. Türkçe kural yabancı adda I'yı ı yapar
    ("DAVID" → "Davıd"); böyle bir ad ayarlar.AD_DUZELTME'ye elle yazılır.
    """
    if uid in ayarlar.AD_DUZELTME:
        return ayarlar.AD_DUZELTME[uid]
    return " ".join(
        "-".join(_buyuk_harf(_kucuk(p)) for p in w.split("-"))
        for w in (isim or ad).split()
    )


_ASCII = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
_ALFABE = "abcçdefgğhıijklmnoöprsştuüvyz"


def _kisa(ad):
    """Adres çubuğundaki kişi bağlantısı (#ayse-kaya): Türkçe harf ASCII'ye çevrilir; harf, rakam, tire."""
    return re.sub(r"[^a-z0-9]+", "-", ad.translate(_ASCII).lower()).strip("-") or "kisi"


def _sira(ad):
    """Türkçe alfabe sırası (ç c'den, ş s'den sonra); alfabede olmayan karakter sona."""
    return [
        (_ALFABE.index(c), "") if c in _ALFABE else (len(_ALFABE), c)
        for c in _kucuk(ad)
    ]


def _sure_tablosu():
    satirlar = []
    for boy, gun in ayarlar.BOY_GUN.items():
        saat = gun * 8
        sure = (
            f"{saat.normalize():f} saat"
            if boy in ("XS", "SM")
            else f"{gun.normalize():f} gün"
        )
        satirlar.append(
            {
                "etiket": boy,
                "sure": sure.replace(".", ","),
                "gun": f"{gun.normalize():f}".replace(".", ","),
            }
        )
    for etiket, gun in ayarlar.GUN_ETIKETI.items():
        satirlar.append(
            {
                "etiket": etiket,
                "sure": f"{gun.normalize():f} gün",
                "gun": f"{gun.normalize():f}",
            }
        )
    return satirlar


def veri_kur(aylar, uretim=None):
    """{ay: döküm} → sayfaya gömülecek veri. Kişiler görünen ada göre sıralı listeye çevrilir."""
    out = {}
    for ay, dokum in sorted(aylar.items()):
        if ay < ayarlar.BASLANGIC_AYI:
            continue
        kisiler = [
            k | {"gorunen": gorunen_ad(uid, k["isim"], k["ad"]), "kisa": _kisa(k["ad"])}
            for uid, k in dokum["kisiler"].items()
        ]
        kisiler.sort(key=lambda k: _sira(k["gorunen"]))
        gorulen = {}
        for k in kisiler:
            n = gorulen[k["kisa"]] = gorulen.get(k["kisa"], 0) + 1
            if n > 1:
                k["kisa"] = f"{k['kisa']}-{n}"
        out[ay] = dokum | {"kisiler": kisiler}
    return {
        "aylar": out,
        "kurallar": {"sure": _sure_tablosu()},
        "uretim": uretim or datetime.now(UTC).isoformat(timespec="minutes"),
    }


def _csp(sablon):
    betik = re.search(r"<script>(.*?)</script>", sablon, re.DOTALL).group(1)
    ozet = base64.b64encode(hashlib.sha256(betik.encode("utf-8")).digest()).decode()
    return (
        f"default-src 'none'; script-src 'sha256-{ozet}'; style-src 'unsafe-inline'; "
        "font-src data:; img-src data: blob:; base-uri 'none'; form-action 'none'"
    )


def _yazi_css():
    """pano/yazi/yazi.css içindeki dosya adları gömülü veri adresine çevrilir (karar 34)."""
    css = YAZI.joinpath("yazi.css").read_text(encoding="utf-8")
    return re.sub(
        r"url\(([\w.-]+\.woff2)\)",
        lambda m: (
            "url(data:font/woff2;base64,"
            + base64.b64encode(YAZI.joinpath(m.group(1)).read_bytes()).decode()
            + ")"
        ),
        css,
    )


def html_uret(veri, anahtar=None):
    """anahtar verilirse veri kilitlenir: sayfada yalnız giriş ekranı ve okunamaz bir paket kalır."""
    sablon = SABLON.read_text(encoding="utf-8")
    gomulecek = {"kilitli": sifre.json_kilitle(veri, anahtar)} if anahtar else veri
    # JSON içindeki her "<" kaçışlı yazılır (\u003c): görev adındaki "</script>" betik bloğunu kapatamaz.
    gomulu = json.dumps(gomulecek, ensure_ascii=False).replace("<", "\\u003c")
    return (
        sablon.replace("__CSP__", _csp(sablon))
        .replace("__YAZI__", _yazi_css())
        .replace("__VERI__", gomulu)
    )


def _oku(klasor):
    k = Path(klasor)
    out = {}
    for p in sorted(k.glob("????-??.json")) if k.exists() else []:
        dokum = json.loads(p.read_text(encoding="utf-8"))
        if dokum.get("ay") != p.stem:
            raise ValueError(
                f"{p}: dosya adı ile dökümdeki ay ({dokum.get('ay')}) farklı"
            )
        out[p.stem] = dokum
    return out


def uret(arsiv, canli, cikti, anahtar=None):
    """Arşivdeki ay kesindir; aynı ayın canlı kopyası varsa yok sayılır."""
    aylar = _oku(canli) | _oku(arsiv)
    hedef = Path(cikti) / "index.html"
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(html_uret(veri_kur(aylar), anahtar), encoding="utf-8")
    return hedef, sorted(aylar)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--arsiv", default="veri/arsiv")
    ap.add_argument("--canli", default="veri/canli")
    ap.add_argument("--cikti", default="site")
    ap.add_argument(
        "--kilit", action="store_true", help="PANO_KULLANICI / PANO_SIFRE ile kilitle"
    )
    a = ap.parse_args(argv)
    anahtar = (
        sifre.anahtar(
            os.environ.get("PANO_KULLANICI"), os.environ.get("PANO_SIFRE"), "sayfa"
        )
        if a.kilit
        else None
    )
    hedef, aylar = uret(a.arsiv, a.canli, a.cikti, anahtar)
    print(f"{hedef} yazıldı · aylar: {', '.join(aylar) or 'yok'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
