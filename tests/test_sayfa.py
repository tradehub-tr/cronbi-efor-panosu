"""Sayfa üretimi — ad gösterimi, veri gömme (kaçış), ay seçimi, süre tablosu (KARARLAR.md numaraları parantezde)."""

import json
import re
import tempfile
import unittest
from pathlib import Path

from pano import ayarlar, sayfa

DUZELTILEN = "u-cem-ornek"
ayarlar.AD_DUZELTME.clear()
ayarlar.AD_DUZELTME[DUZELTILEN] = "Cem Öztürk"
KOTU = '</script><script>alert(1)</script><img src=x onerror="alert(2)">'


def dokum(ay="2026-11", durum="canli", kisiler=None, uyarilar=()):
    return {
        "ay": ay,
        "durum": durum,
        "zaman": f"{ay}-26T14:00+03:00",
        "is_gunu": 21,
        "gunler": [],
        "kisiler": kisiler or {},
        "uyarilar": list(uyarilar),
    }


def kisi(ad, isim, efor="2.5", gorev_adi="Örnek görev (Efor Panosu)"):
    s = {
        "kod": "MOGEM-1",
        "ad": gorev_adi,
        "efor": efor,
        "boy": "LG",
        "etiket": None,
        "toplanti": False,
        "bagli_is": None,
        "bas": None,
        "bit": "2026-11-20",
        "done": None,
        "cizgi": [20, 20],
        "durum": "Done",
    }
    return {
        "id": ad,
        "ad": ad,
        "isim": isim,
        "efor": efor,
        "sayilan": [s],
        "gec": [],
        "bos": [],
        "acik": [],
    }


def gomulu(html):
    return json.loads(
        re.search(
            r'<script id="veri" type="application/json">(.*?)</script>', html, re.DOTALL
        ).group(1)
    )


class AdGosterimi(unittest.TestCase):  # (29)
    def test_turkce_buyuk_harf(self):
        for isim, beklenen in (
            ("Ayşe KAYA", "Ayşe Kaya"),
            ("deniz yıldırım", "Deniz Yıldırım"),
            ("Efe Demir", "Efe Demir"),
            ("İSMAİL ılgaz", "İsmail Ilgaz"),
        ):
            self.assertEqual(sayfa.gorunen_ad("u", isim, "x"), beklenen)

    def test_elle_duzeltme_ve_bos_isim(self):
        self.assertEqual(
            sayfa.gorunen_ad(DUZELTILEN, "Cem", "cem.ozturk"), "Cem Öztürk"
        )
        self.assertEqual(sayfa.gorunen_ad("u", "", "ayse.kaya"), "Ayse.kaya")

    def test_kisi_baglantisi_ascii(self):
        v = sayfa.veri_kur(
            {"2026-11": dokum(kisiler={"u1": kisi("şükrü.öz", "Şükrü Öz")})}
        )
        self.assertRegex(v["aylar"]["2026-11"]["kisiler"][0]["kisa"], r"^[a-z0-9-]+$")


class Baglanti(unittest.TestCase):  # inceleme F2-4, F2-7, F2-12
    def test_turkce_harf_korunur_cakisma_numaralanir(self):
        v = sayfa.veri_kur(
            {
                "2026-11": dokum(
                    kisiler={
                        "u1": kisi("ayse.kaya", "Ayşe Kaya"),
                        "u2": kisi("ayse_kaya", "Ayşe Kaya"),
                        "u3": kisi("şükrü.çağrı", "Şükrü Çağrı"),
                    }
                )
            }
        )
        self.assertEqual(
            sorted(k["kisa"] for k in v["aylar"]["2026-11"]["kisiler"]),
            ["ayse-kaya", "ayse-kaya-2", "sukru-cagri"],
        )

    def test_turkce_alfabe_sirasi(self):
        v = sayfa.veri_kur(
            {
                "2026-11": dokum(
                    kisiler={
                        "a": kisi("z", "Zeki Ak"),
                        "b": kisi("c", "Çağrı Er"),
                        "c": kisi("s", "Şükrü Öz"),
                        "d": kisi("cc", "Cem Ay"),
                    }
                )
            }
        )
        self.assertEqual(
            [k["gorunen"] for k in v["aylar"]["2026-11"]["kisiler"]],
            ["Cem Ay", "Çağrı Er", "Şükrü Öz", "Zeki Ak"],
        )

    def test_tireli_ad(self):
        self.assertEqual(
            sayfa.gorunen_ad("u", "ayşe-nur YILMAZ", "x"), "Ayşe-Nur Yılmaz"
        )


class VeriGomme(unittest.TestCase):
    def test_kod_iceren_metin_betik_blogunu_kapatamaz(self):
        d = dokum(
            kisiler={"u1": kisi("ayse.kaya", KOTU, gorev_adi=KOTU)},
            uyarilar=[{"kod": "MOGEM-9", "ad": KOTU, "neden": KOTU}],
        )
        html = sayfa.html_uret(sayfa.veri_kur({"2026-11": d}))
        govde = html[html.index('<script id="veri"') :]
        self.assertEqual(
            govde.count("</script>"), 2
        )  # yalnız veri bloğunun ve betiğin kendi kapanışı
        self.assertNotIn("<img src=x", html)
        v = gomulu(html)
        self.assertEqual(v["aylar"]["2026-11"]["kisiler"][0]["sayilan"][0]["ad"], KOTU)


class Guvenlik(unittest.TestCase):  # inceleme F2-14
    def test_icerik_politikasi_betigin_ozetini_tasir(self):
        import base64
        import hashlib

        html = sayfa.html_uret(sayfa.veri_kur({"2026-11": dokum()}))
        betik = re.search(r"<script>(.*?)</script>", html, re.DOTALL).group(1)
        ozet = base64.b64encode(hashlib.sha256(betik.encode()).digest()).decode()
        self.assertIn(f"script-src 'sha256-{ozet}'", html)
        self.assertIn("default-src 'none'", html)
        self.assertIn('<meta name="referrer" content="no-referrer">', html)
        self.assertNotIn("__CSP__", html)


class AySecimi(unittest.TestCase):
    def test_baslangic_oncesi_ay_yok_kisiler_sirali(self):
        v = sayfa.veri_kur(
            {
                "2026-10": dokum("2026-10"),
                "2026-11": dokum(
                    kisiler={
                        "b": kisi("deniz.y", "deniz yıldırım"),
                        "a": kisi("ayse.kaya", "Ayşe KAYA"),
                    }
                ),
            }
        )
        self.assertEqual(list(v["aylar"]), ["2026-11"])
        self.assertEqual(
            [k["gorunen"] for k in v["aylar"]["2026-11"]["kisiler"]],
            ["Ayşe Kaya", "Deniz Yıldırım"],
        )

    def test_dosya_adi_ile_ay_uyusmazsa_durur(self):
        with tempfile.TemporaryDirectory() as t:
            Path(t, "2026-12.json").write_text(
                json.dumps(dokum("2026-11")), encoding="utf-8"
            )
            with self.assertRaises(ValueError):
                sayfa.uret(t, f"{t}/yok", f"{t}/site")

    def test_arsivdeki_ay_canli_kopyayi_ezer(self):
        with tempfile.TemporaryDirectory() as t:
            for klasor, durum in (("arsiv", "kesin"), ("canli", "canli")):
                Path(t, klasor).mkdir()
                Path(t, klasor, "2026-11.json").write_text(
                    json.dumps(dokum(durum=durum)), encoding="utf-8"
                )
            Path(t, "canli", "2026-12.json").write_text(
                json.dumps(dokum("2026-12")), encoding="utf-8"
            )
            hedef, aylar = sayfa.uret(f"{t}/arsiv", f"{t}/canli", f"{t}/site")
            v = gomulu(hedef.read_text(encoding="utf-8"))
        self.assertEqual(
            (aylar, v["aylar"]["2026-11"]["durum"]), (["2026-11", "2026-12"], "kesin")
        )


class SureTablosu(unittest.TestCase):  # (3, 20, 31)
    def test_boy_ve_gun_etiketleri(self):
        t = {r["etiket"]: (r["sure"], r["gun"]) for r in sayfa._sure_tablosu()}
        self.assertEqual(t["XS"], ("3 saat", "0,375"))
        self.assertEqual(t["SM"], ("6,5 saat", "0,8125"))
        self.assertEqual(t["LG"], ("2,5 gün", "2,5"))
        self.assertEqual(t["T2"], ("2 gün", "2"))
        self.assertEqual(
            list(t), ["XS", "SM", "MD", "LG", "XL", "T1", "T2", "T3", "T4"]
        )


if __name__ == "__main__":
    unittest.main()
