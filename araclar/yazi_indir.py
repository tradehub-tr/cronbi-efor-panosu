"""Sayfanın yazı tiplerini Google Fonts'tan bir kez indirip pano/yazi/ altına koyar (karar 34).

  python3 araclar/yazi_indir.py

Yalnız latin ve latin-ext (Türkçe ğ ş ı İ) alt kümeleri alınır. Yazı tipleri SIL Open Font License
ile dağıtılır; her ailenin lisans metni yanına yazılır. Sayfa üretilirken dosyalar sayfaya gömülür,
ziyaretçi tarayıcısı Google'a hiç istek göndermez.
"""

import hashlib
import re
import urllib.request
from pathlib import Path

HEDEF = Path(__file__).resolve().parents[1] / "pano" / "yazi"
CSS = (
    "https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..800"
    "&family=Source+Sans+3:wght@400;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap"
)
LISANS = {
    "Archivo": "https://raw.githubusercontent.com/google/fonts/main/ofl/archivo/OFL.txt",
    "Source Sans 3": "https://raw.githubusercontent.com/google/fonts/main/ofl/sourcesans3/OFL.txt",
    "IBM Plex Mono": "https://raw.githubusercontent.com/google/fonts/main/ofl/ibmplexmono/OFL.txt",
}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


def _al(url):
    with urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60
    ) as y:
        return y.read()


def main():
    HEDEF.mkdir(parents=True, exist_ok=True)
    css = _al(CSS).decode("utf-8")
    kurallar, dosyalar, adlar = [], {}, {}
    for alt, blok in re.findall(
        r"/\* ([\w-]+) \*/\s*@font-face \{(.*?)\}", css, re.DOTALL
    ):
        if alt not in ("latin", "latin-ext"):
            continue
        aile = re.search(r"font-family: '([^']+)'", blok).group(1)
        url = re.search(r"url\((\S+?)\)", blok).group(1)
        ad = f"{aile.lower().replace(' ', '-')}-{alt}-{hashlib.sha1(url.encode()).hexdigest()[:8]}.woff2"
        if url in dosyalar:
            # Değişken yazı tipinde aynı dosya birden çok kalınlığa veriliyor: tek kurala, kalınlık aralığıyla.
            i, eski = dosyalar[url]
            kalinlik = sorted(
                {*eski, *re.search(r"font-weight: ([\d ]+);", blok).group(1).split()},
                key=int,
            )
            dosyalar[url] = (i, kalinlik)
            kurallar[i] = re.sub(
                r"font-weight: [\d ]+;",
                f"font-weight: {kalinlik[0]} {kalinlik[-1]};",
                kurallar[i],
            )
            continue
        dosyalar[url] = (
            len(kurallar),
            re.search(r"font-weight: ([\d ]+);", blok).group(1).split(),
        )
        kurallar.append(
            "@font-face {" + blok.replace(f"url({url})", f"url({ad})") + "}"
        )
        adlar[url] = ad
    for url, ad in adlar.items():
        (HEDEF / ad).write_bytes(_al(url))
    (HEDEF / "yazi.css").write_text("\n".join(kurallar) + "\n", encoding="utf-8")
    for aile, url in LISANS.items():
        (HEDEF / f"OFL-{aile.replace(' ', '')}.txt").write_bytes(_al(url))
    print(
        f"{len(adlar)} yazı tipi dosyası, {len(kurallar)} kural, {len(LISANS)} lisans → {HEDEF}"
    )


if __name__ == "__main__":
    main()
