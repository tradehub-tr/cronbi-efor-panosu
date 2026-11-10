"""Kilit, otomatik çalışma, sızıntı denetimi, şifre yenileme (KARARLAR.md numaraları parantezde)."""

import io
import json
import os
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest import mock

from pano import cli, sayfa, sifre, yayin
from tests.test_hesap import cekim, kayit

KIMLIK = {"PANO_KULLANICI": "yonetici", "PANO_SIFRE": "örnek-şifre (Efor Panosu)"}


class Kilit(unittest.TestCase):
    def test_kilitle_ac_ve_yanlis_sifre(self):
        a = sifre.anahtar("yonetici", "dogru", "sayfa")
        paket = sifre.json_kilitle({"x": "Örnek"}, a)
        self.assertEqual(sifre.json_ac(paket, a), {"x": "Örnek"})
        with self.assertRaises(sifre.SifreHatasi):
            sifre.json_ac(paket, sifre.anahtar("yonetici", "yanlis", "sayfa"))
        with self.assertRaises(sifre.SifreHatasi):
            sifre.json_ac(paket, sifre.anahtar("baska", "dogru", "sayfa"))

    def test_anahtar_her_yayinda_ayni_iv_her_kilitte_farkli(
        self,
    ):  # (33) oturum anahtarı güncellemeden sonra da açar
        a1, a2 = sifre.anahtar("y", "s", "sayfa"), sifre.anahtar("y", "s", "sayfa")
        self.assertEqual(a1, a2)
        self.assertNotEqual(
            sifre.json_kilitle({}, a1)["iv"], sifre.json_kilitle({}, a1)["iv"]
        )

    def test_sayfa_ve_arsiv_anahtari_ayri_tuzla(self):  # (35)
        self.assertNotEqual(
            sifre.anahtar("y", "s", "sayfa"), sifre.anahtar("y", "s", "arsiv")
        )

    def test_kullanici_adi_kenar_boslugu_ve_harf_bicimi_ayni_anahtari_verir(self):
        # Tarayıcı kullanıcı adını trim + NFC eder; gizli değişkende boşluk ya da NFD "ö" sayfayı kilitlemesin
        nfc = sifre.anahtar("yönetici", "Şifre-ığüçö", "sayfa")
        nfd = "yo\u0308netici"
        self.assertEqual(sifre.anahtar(f" {nfd}\n", "S\u0327ifre-ığüçö", "sayfa"), nfc)
        self.assertNotEqual(
            sifre.anahtar("yönetici", "Şifre-ığüçö ", "sayfa"), nfc
        )  # şifre kırpılmaz

    def test_bos_kimlik_reddedilir(self):
        with self.assertRaises(sifre.SifreHatasi):
            sifre.anahtar("", "s", "sayfa")


class EkGuncelleme(unittest.TestCase):  # (10) ayın son 2 günü
    def test_son_iki_gun(self):
        for iso, beklenen in (
            ("2026-11-28T09:00:00+00:00", False),
            ("2026-11-29T09:00:00+00:00", True),
            ("2026-11-30T14:30:00+00:00", True),
            ("2026-12-29T09:00:00+00:00", False),
            ("2026-12-30T09:00:00+00:00", True),
            ("2027-02-27T09:00:00+00:00", True),
            ("2028-02-28T09:00:00+00:00", True),
            ("2028-02-27T09:00:00+00:00", False),
        ):
            self.assertEqual(
                yayin.son_iki_gun(datetime.fromisoformat(iso)), beklenen, iso
            )


@mock.patch.dict(os.environ, KIMLIK)
class Calisma(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.k = Path(self.t.name)
        Path(self.k, "c.json").write_text(
            json.dumps(cekim(kayit(1, etiket=["LG"], bit="2026-11-20"))),
            encoding="utf-8",
        )

    def tearDown(self):
        self.t.cleanup()

    def calistir(self, simdi, tetik=""):
        cikti = io.StringIO()
        with redirect_stdout(cikti):
            kod = yayin.main(
                [
                    "--kilitli-arsiv",
                    f"{self.k}/aylar",
                    "--site",
                    f"{self.k}/site",
                    "--cekim",
                    f"{self.k}/c.json",
                    "--simdi",
                    simdi,
                    "--tetik",
                    tetik,
                ]
            )
        return kod, cikti.getvalue()

    def test_ek_tetik_son_iki_gun_degilse_hicbir_sey_yapmaz(self):
        kod, cikti = self.calistir("2026-11-28T09:00:00+00:00", "0 9 1,27-31 * *")
        self.assertEqual((kod, Path(self.k, "site").exists()), (0, False))
        self.assertIn("ek güncelleme yapılmadı", cikti)

    def test_ayin_birinde_kesinlesme_dustuyse_ek_tetik_yeniden_dener(self):
        kod, _ = self.calistir("2026-12-01T09:00:00+00:00", "0 9 1,27-31 * *")
        self.assertEqual(kod, 0)
        self.assertTrue(Path(self.k, "aylar", "2026-11.json").exists())
        kod, cikti = self.calistir("2026-12-01T14:30:00+00:00", "30 14 1,27-31 * *")
        self.assertIn(
            "ek güncelleme yapılmadı", cikti
        )  # kesinleşti: ikinci deneme boş geçer

    def test_kesinlestirir_kilitler_ve_duz_veri_birakmaz(self):  # (4, 35)
        kod, cikti = self.calistir("2026-12-01T09:00:00+00:00")
        self.assertEqual(kod, 0)
        kasim = Path(self.k, "aylar", "2026-11.json")
        self.assertTrue(kasim.exists())
        self.assertEqual(
            yayin.sizinti_denetimi(Path(self.k, "site", "index.html"), kasim), []
        )
        dokum = sifre.json_ac(
            json.loads(kasim.read_text()),
            sifre.anahtar(KIMLIK["PANO_KULLANICI"], KIMLIK["PANO_SIFRE"], "arsiv"),
        )
        self.assertEqual(dokum["kisiler"]["u-ayse"]["efor"], "2.5")
        self.assertNotIn("ayse.kaya", cikti)  # günlük herkese açık: kişi adı yok
        self.assertNotIn("2.5", cikti)

    def test_kesinlesen_ay_yeniden_yazilmaz(self):
        self.calistir("2026-12-01T09:00:00+00:00")
        kasim = Path(self.k, "aylar", "2026-11.json")
        once = kasim.read_text()
        self.calistir("2026-12-02T09:00:00+00:00")
        self.assertEqual(kasim.read_text(), once)

    def test_yanlis_sifreyle_arsiv_acilmaz_dosya_yazilmaz(self):
        self.calistir("2026-12-01T09:00:00+00:00")
        site = Path(self.k, "site", "index.html")
        once = site.read_text()
        with mock.patch.dict(os.environ, {"PANO_SIFRE": "yanlis"}):
            kod, _ = self.calistir("2026-12-02T09:00:00+00:00")
        self.assertEqual((kod, site.read_text()), (6, once))

    def test_sizinti_denetimi_duz_sayfayi_yakalar(self):
        duz = Path(self.k, "duz.html")
        duz.write_text(sayfa.html_uret(sayfa.veri_kur({})), encoding="utf-8")
        self.assertEqual(yayin.sizinti_denetimi(duz), [str(duz)])

    def test_sifre_yenile_eski_aylari_yeni_sifreyle_acar(self):  # (35)
        self.calistir("2026-12-01T09:00:00+00:00")
        yeni = {
            "PANO_KULLANICI": "yonetici",
            "PANO_SIFRE": "yeni-şifre",
            "ESKI_PANO_KULLANICI": KIMLIK["PANO_KULLANICI"],
            "ESKI_PANO_SIFRE": KIMLIK["PANO_SIFRE"],
        }
        with mock.patch.dict(os.environ, yeni), redirect_stdout(io.StringIO()):
            self.assertEqual(
                yayin.main(["--kilitli-arsiv", f"{self.k}/aylar", "--sifre-yenile"]), 0
            )
            kod, _ = self.calistir("2026-12-02T09:00:00+00:00")
        self.assertEqual(kod, 0)

    def test_sifre_yenilemede_eski_sifre_yanlissa_hicbir_dosya_degismez(self):
        self.calistir("2026-12-01T09:00:00+00:00")
        kasim = Path(self.k, "aylar", "2026-11.json")
        once = kasim.read_text()
        with (
            mock.patch.dict(
                os.environ,
                {"ESKI_PANO_KULLANICI": "yonetici", "ESKI_PANO_SIFRE": "yanlis"},
            ),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(
                yayin.main(["--kilitli-arsiv", f"{self.k}/aylar", "--sifre-yenile"]), 6
            )
        self.assertEqual(kasim.read_text(), once)


class KilitliSayfa(unittest.TestCase):
    def test_kilitli_sayfada_duz_veri_ve_dis_kaynak_yok(self):
        a = sifre.anahtar("y", "s", "sayfa")
        html = sayfa.html_uret(sayfa.veri_kur({}), a)
        self.assertIn('"kilitli"', html)
        self.assertNotIn('"kurallar"', html)
        self.assertNotIn("fonts.googleapis", html)  # (34)
        self.assertIn("data:font/woff2;base64,", html)


class IsAkisi(unittest.TestCase):
    """İlk canlı çalışmada PANO_KISILER iş akışına verilmemişti; dışlama ve ad düzeltmesi sessizce düştü."""

    def test_kodun_okudugu_her_gizli_degisken_is_akisina_verilir(self):
        # pano.yayin ayarlar'ı içe aktarır; PANO_KISILER yoksa iki akış da durur (bağımsız inceleme F3, bulgu 1)
        for akis, adlar in (
            (
                "pano.yml",
                ("PLANE_API_KEY", "PANO_KULLANICI", "PANO_SIFRE", "PANO_KISILER"),
            ),
            (
                "sifre-yenile.yml",
                (
                    "ESKI_PANO_KULLANICI",
                    "ESKI_PANO_SIFRE",
                    "PANO_KULLANICI",
                    "PANO_SIFRE",
                    "PANO_KISILER",
                ),
            ),
        ):
            metin = Path(".github/workflows", akis).read_text(encoding="utf-8")
            for ad in adlar:
                self.assertIn(f"{ad}: ${{{{ secrets.{ad} }}}}", metin, akis)

    def test_ek_tetikler_takvimle_ayni_ayin_birini_ve_subat_27yi_kapsar(self):
        akis = Path(".github/workflows/pano.yml").read_text(encoding="utf-8")
        takvim = set(re.findall(r'cron: "([^"]+)"', akis)) - {"30 21 * * *"}
        self.assertEqual(takvim, yayin.EK_TETIKLER)
        for c in takvim:
            self.assertEqual(c.split()[2], "1,27-31")

    def test_veri_hatasi_herkese_acik_gunluge_gorev_kodu_yazmaz(self):
        with tempfile.TemporaryDirectory() as t:
            c = Path(t, "c.json")
            c.write_text(
                json.dumps(
                    cekim(kayit(10, durum="s-yok", etiket=["MD"], bit="2026-11-05"))
                ),
                encoding="utf-8",
            )
            hata = io.StringIO()
            with redirect_stderr(hata):
                kod = cli.main(
                    [
                        "--cekim",
                        str(c),
                        "--arsiv",
                        f"{t}/a",
                        "--cikti",
                        f"{t}/c",
                        "--sessiz",
                    ]
                )
        self.assertEqual(kod, 3)
        self.assertNotIn("MOGEM-", hata.getvalue())

    def test_githubda_kisi_ayari_yoksa_durur(self):
        from pano import ayarlar

        with (
            mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}, clear=True),
            mock.patch.object(ayarlar.Path, "exists", return_value=False),
            self.assertRaises(SystemExit),
        ):
            ayarlar._kisiler()


if __name__ == "__main__":
    unittest.main()
