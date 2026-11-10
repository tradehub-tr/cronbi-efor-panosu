"""Hesap kuralları — örnek veri Plane work-items yanıtı biçiminde kurulur (KARARLAR.md numaraları parantezde)."""

import json
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest import mock

from pano import ayarlar, cli, hesap, plane
from pano.arsiv import Arsiv

DURUMLAR = {
    "s-done": {"ad": "Done", "grup": "completed"},
    "s-released": {"ad": "Released", "grup": "completed"},
    "s-prog": {"ad": "In Progress", "grup": "started"},
    "s-todo": {"ad": "Todo", "grup": "unstarted"},
    "s-sprint": {"ad": "Sprint Backlog", "grup": "backlog"},
    "s-ice": {"ad": "Icebox", "grup": "backlog"},
    "s-iptal": {"ad": "Cancelled", "grup": "cancelled"},
}
DISLANAN = "u-dislanan-ornek"
ayarlar.HARIC_UYELER.clear()
ayarlar.HARIC_UYELER[DISLANAN] = "örnek dışlanan hesap"
UYELER = {
    "u-ayse": {"ad": "ayse.kaya", "isim": "Ayşe Kaya"},
    "u-efe": {"ad": "efe.demir", "isim": "Efe Demir"},
    DISLANAN: {"ad": "ornek.dislanan", "isim": "Örnek"},
}


def kayit(
    no,
    *,
    durum="s-done",
    kim=("u-ayse",),
    etiket=(),
    bas=None,
    bit=None,
    done=None,
    ust=None,
    ad=None,
):
    return {
        "id": f"id-{no}",
        "sequence_id": no,
        "name": ad or f"Örnek görev {no} (Efor Panosu)",
        "state": durum,
        "assignees": list(kim),
        "labels": [e if e.startswith("lbl-") else {"name": e} for e in etiket],
        "start_date": bas,
        "target_date": bit,
        "completed_at": done,
        "parent": ust and f"id-{ust}",
    }


def cekim(*kayitlar, uyeler=None):
    return {
        "kayitlar": list(kayitlar),
        "durumlar": DURUMLAR,
        "etiketler": {"lbl-lg": "LG"},
        "uyeler": uyeler or UYELER,
        "cekim": "2026-11-10T14:00:00+00:00",
    }


def dokum(*kayitlar, ay="2026-11", arsiv=None, uyeler=None):
    c = cekim(*kayitlar, uyeler=uyeler)
    return hesap.ay_dokumu(hesap.gorevleri_kur(c), ay, arsiv, c["uyeler"])


def kodlar(d, kisi, liste):
    return [s["kod"] for s in d["kisiler"].get(kisi, {}).get(liste, [])]


def efor(d, kisi):
    return Decimal(d["kisiler"][kisi]["efor"])


class AyBelirleme(unittest.TestCase):
    def test_bitis_tarihi_ayi_belirler_baslangic_belirlemez(self):  # (2)
        k = kayit(
            1,
            etiket=["MD"],
            bas="2026-10-28",
            bit="2026-11-03",
            done="2026-10-29T08:00:00Z",
        )
        self.assertEqual(kodlar(dokum(k), "u-ayse", "sayilan"), ["MOGEM-1"])
        self.assertEqual(dokum(k, ay="2026-10")["kisiler"], {})

    def test_bitis_yoksa_done_gunu_istanbul_saatiyle(
        self,
    ):  # (2) 31 Eki 21:30 UTC = 1 Kasım 00:30
        k = kayit(2, etiket=["SM"], done="2026-10-31T21:30:00Z")
        self.assertEqual(kodlar(dokum(k), "u-ayse", "sayilan"), ["MOGEM-2"])
        self.assertEqual(dokum(k, ay="2026-10")["kisiler"], {})

    def test_ay_siniri_23_59(self):
        k = kayit(
            3, etiket=["SM"], done="2026-11-30T20:59:00Z"
        )  # 30 Kasım 23:59 İstanbul
        self.assertEqual(kodlar(dokum(k), "u-ayse", "sayilan"), ["MOGEM-3"])

    def test_done_degil_sayilmaz_ama_gorunur(self):
        d = dokum(
            kayit(4, durum="s-prog", etiket=["LG"], bas="2026-11-25"),
            kayit(5, durum="s-ice", etiket=["LG"], bas="2026-11-25"),
            kayit(6, durum="s-sprint", etiket=["LG"], bit="2026-11-27"),
        )
        self.assertEqual(kodlar(d, "u-ayse", "acik"), ["MOGEM-4", "MOGEM-6"])
        self.assertEqual(efor(d, "u-ayse"), 0)

    def test_gecikmis_acik_is_sonraki_ayda_da_gorunur(self):
        k = kayit(7, durum="s-prog", etiket=["LG"], bas="2026-11-02", bit="2026-11-20")
        self.assertEqual(kodlar(dokum(k, ay="2026-12"), "u-ayse", "acik"), ["MOGEM-7"])

    def test_iptal_edilen_hic_gorunmez(self):
        self.assertEqual(
            dokum(kayit(8, durum="s-iptal", etiket=["LG"], bas="2026-11-02"))[
                "kisiler"
            ],
            {},
        )

    def test_yeni_tamamlandi_durumu_grubundan_tanınır(self):
        d = dokum(kayit(9, durum="s-released", etiket=["MD"], bit="2026-11-05"))
        self.assertEqual(kodlar(d, "u-ayse", "sayilan"), ["MOGEM-9"])

    def test_bilinmeyen_durum_sessizce_dusmez(self):
        with self.assertRaises(hesap.VeriHatasi):
            hesap.gorevleri_kur(
                cekim(kayit(10, durum="s-yok", etiket=["MD"], bit="2026-11-05"))
            )

    def test_baslangic_ayindan_onceki_is_sayilmaz(self):  # (5, 21) MOGEM-1201 deseni
        d = dokum(
            kayit(
                11,
                etiket=["XL"],
                bas="2026-10-19",
                bit="2026-10-19",
                done="2026-11-02T09:00:00Z",
            )
        )
        self.assertEqual(d["kisiler"], {})


class Sure(unittest.TestCase):
    def test_boy_tablosu(self):  # (3)
        etk = {"XS": "0.375", "SM": "0.8125", "MD": "1.5", "LG": "2.5", "XL": "3.5"}
        for i, (boy, gun) in enumerate(etk.items()):
            self.assertEqual(
                efor(dokum(kayit(20 + i, etiket=[boy], bit="2026-11-05")), "u-ayse"),
                Decimal(gun),
                boy,
            )

    def test_etiket_harf_ve_bosluk_farki(self):
        d = dokum(
            kayit(26, etiket=["lg "], bit="2026-11-05"),
            kayit(27, etiket=["Toplantı", "t1"], bit="2026-11-06"),
        )
        self.assertEqual(efor(d, "u-ayse"), Decimal("3.5"))
        self.assertTrue(d["kisiler"]["u-ayse"]["sayilan"][1]["toplanti"])

    def test_etiket_kimlik_olarak_gelirse_cozulur(self):
        self.assertEqual(
            efor(dokum(kayit(28, etiket=["lbl-lg"], bit="2026-11-05")), "u-ayse"),
            Decimal("2.5"),
        )
        with self.assertRaises(hesap.VeriHatasi):
            hesap.gorevleri_kur(
                cekim(kayit(29, etiket=["lbl-silinmis"], bit="2026-11-05"))
            )

    def test_cok_atanan_herkese_tam_boy(self):  # (1)
        d = dokum(kayit(30, kim=("u-ayse", "u-efe"), etiket=["XS"], bit="2026-11-05"))
        self.assertEqual(efor(d, "u-ayse"), efor(d, "u-efe"))
        self.assertEqual(efor(d, "u-efe"), Decimal("0.375"))

    def test_gun_etiketi_toplanti(self):  # (20, 22)
        d = dokum(
            kayit(31, etiket=["toplantı", "T2"], done="2026-11-06T15:00:00Z"),
            kayit(32, etiket=["T1"], bit="2026-11-09"),
        )
        self.assertEqual(efor(d, "u-ayse"), 3)
        self.assertTrue(all(s["toplanti"] for s in d["kisiler"]["u-ayse"]["sayilan"]))

    def test_gun_etiketi_boydan_once_gelir(self):
        self.assertEqual(
            efor(
                dokum(kayit(33, etiket=["toplantı", "SM", "T1"], bit="2026-11-09")),
                "u-ayse",
            ),
            1,
        )

    def test_boylu_toplanti_boyla_sayilir_boysuz_bos(self):  # (16)
        d = dokum(
            kayit(34, etiket=["toplantı", "MD"], bit="2026-11-09"),
            kayit(35, etiket=["toplantı"], bit="2026-11-10"),
        )
        self.assertEqual(kodlar(d, "u-ayse", "sayilan"), ["MOGEM-34"])
        self.assertEqual(kodlar(d, "u-ayse", "bos"), ["MOGEM-35"])
        self.assertEqual(efor(d, "u-ayse"), Decimal("1.5"))

    def test_xxl_ve_boysuz_toplama_girmez(self):  # (23)
        d = dokum(
            kayit(36, etiket=["XXL"], bit="2026-11-09"), kayit(37, bit="2026-11-09")
        )
        self.assertEqual(kodlar(d, "u-ayse", "bos"), ["MOGEM-36", "MOGEM-37"])
        self.assertEqual(efor(d, "u-ayse"), 0)
        self.assertEqual(d["kisiler"]["u-ayse"]["bos"][0]["boy"], "XXL")

    def test_birden_cok_boy_uyari_verir(self):
        d = dokum(kayit(38, etiket=["SM", "LG"], bit="2026-11-09"))
        self.assertEqual([u["kod"] for u in d["uyarilar"]], ["MOGEM-38"])

    def test_ust_gorev_cift_sayilmaz(self):
        d = dokum(
            kayit(40, etiket=["LG"], bit="2026-11-09"),
            kayit(41, etiket=["MD"], bit="2026-11-09", ust=40),
        )
        self.assertEqual(kodlar(d, "u-ayse", "bos"), ["MOGEM-40"])
        self.assertEqual(efor(d, "u-ayse"), Decimal("1.5"))

    def test_iptal_ya_da_rafta_alt_gorev_ust_goreve_dokunmaz(self):
        d = dokum(
            kayit(42, etiket=["LG"], bit="2026-11-09"),
            kayit(43, durum="s-iptal", ust=42),
            kayit(44, durum="s-ice", ust=42),
        )
        self.assertEqual(efor(d, "u-ayse"), Decimal("2.5"))

    def test_bagli_is_en_ust_gorev(self):  # (22)
        d = dokum(
            kayit(45, ad="CMS + SEO", durum="s-prog"),
            kayit(46, ust=45, durum="s-prog"),
            kayit(47, etiket=["SM"], bit="2026-11-04", ust=46),
        )
        self.assertEqual(d["kisiler"]["u-ayse"]["sayilan"][0]["bagli_is"], "CMS + SEO")


class Kisiler(unittest.TestCase):
    def test_dislanan_hesaplar_gorunmez(self):  # (14)
        d = dokum(
            kayit(50, kim=(DISLANAN, "u-ayse"), etiket=["LG"], bit="2026-11-04"),
            kayit(51, kim=(DISLANAN,), etiket=["LG"], bit="2026-11-04"),
        )
        self.assertEqual(list(d["kisiler"]), ["u-ayse"])

    def test_dislama_ad_degisse_de_surer(self):
        uyeler = UYELER | {DISLANAN: {"ad": "ornek", "isim": "Örnek D."}}
        self.assertEqual(
            dokum(
                kayit(52, kim=(DISLANAN,), etiket=["LG"], bit="2026-11-04"),
                uyeler=uyeler,
            )["kisiler"],
            {},
        )

    def test_uyede_olmayan_atanan_kaybolmaz_uyari_verir(self):
        d = dokum(kayit(53, kim=("u-ayrilan",), etiket=["LG"], bit="2026-11-04"))
        self.assertEqual(
            (efor(d, "u-ayrilan"), d["kisiler"]["u-ayrilan"]["isim"]),
            (Decimal("2.5"), "Tanınmayan üye"),
        )
        self.assertEqual([u["kod"] for u in d["uyarilar"]], ["MOGEM-53"])

    def test_atanansiz_done_uyari_verir(self):
        d = dokum(kayit(54, kim=(), etiket=["LG"], bit="2026-11-04"))
        self.assertEqual(
            (d["kisiler"], [u["kod"] for u in d["uyarilar"]]), ({}, ["MOGEM-54"])
        )

    def test_gorev_adi_degistirilmeden_tasinir(self):  # kaçış F2'de sayfada yapılır
        ad = '<img src=x onerror="alert(1)"> Örnek (Efor Panosu)'
        self.assertEqual(
            dokum(kayit(55, ad=ad, etiket=["XS"], bit="2026-11-04"))["kisiler"][
                "u-ayse"
            ]["sayilan"][0]["ad"],
            ad,
        )


class TekOdeme(unittest.TestCase):
    def setUp(self):
        self.klasor = tempfile.TemporaryDirectory()
        self.arsiv = Arsiv(self.klasor.name)

    def tearDown(self):
        self.klasor.cleanup()

    def kesinlestir(self, *kayitlar, ay="2026-11", uyeler=None):
        self.arsiv.yaz(
            dokum(*kayitlar, ay=ay, arsiv=self.arsiv.oku(), uyeler=uyeler)
            | {"durum": "kesin"}
        )

    def aralik(self, *kayitlar, uyeler=None):
        return dokum(*kayitlar, ay="2026-12", arsiv=self.arsiv.oku(), uyeler=uyeler)

    def test_kapanmis_ayin_isi_sonraki_ayda_gec(self):  # (12)
        self.kesinlestir()
        d = self.aralik(
            kayit(
                60,
                etiket=["LG"],
                bas="2026-11-26",
                bit="2026-11-30",
                done="2026-12-03T09:00:00Z",
            )
        )
        self.assertEqual(
            (kodlar(d, "u-ayse", "gec"), efor(d, "u-ayse")),
            (["MOGEM-60"], Decimal("2.5")),
        )

    def test_kesinlesen_ayda_sayilan_tekrar_sayilmaz(self):
        k = kayit(61, etiket=["LG"], bit="2026-11-20")
        self.kesinlestir(k)
        self.assertEqual(self.aralik(k)["kisiler"], {})

    def test_odenen_isin_bitisi_tasinirsa_tekrar_sayilmaz(self):  # inceleme S1
        self.kesinlestir(kayit(62, etiket=["LG"], bit="2026-11-20"))
        self.assertEqual(
            self.aralik(kayit(62, etiket=["LG"], bit="2026-12-02"))["kisiler"], {}
        )

    def test_odenen_is_yeniden_acilip_kapanirsa_tekrar_sayilmaz(self):  # inceleme S2
        self.kesinlestir(kayit(63, etiket=["LG"], done="2026-11-10T09:00:00Z"))
        self.assertEqual(
            self.aralik(kayit(63, etiket=["LG"], done="2026-12-04T09:00:00Z"))[
                "kisiler"
            ],
            {},
        )

    def test_ad_degisikligi_yeniden_odeme_yaptirmaz(self):  # inceleme S3
        k = kayit(64, etiket=["LG"], bit="2026-11-20")
        self.kesinlestir(k)
        yeni = UYELER | {"u-ayse": {"ad": "ayse", "isim": "Ayşe"}}
        self.assertEqual(self.aralik(k, uyeler=yeni)["kisiler"], {})

    def test_sonradan_gelen_gun_etiketi_gec_sayilir(self):  # (15)
        self.kesinlestir(kayit(65, etiket=["toplantı"], bit="2026-11-16"))
        d = self.aralik(kayit(65, etiket=["toplantı", "T1"], bit="2026-11-16"))
        self.assertEqual(
            (kodlar(d, "u-ayse", "gec"), efor(d, "u-ayse")), (["MOGEM-65"], 1)
        )

    def test_suresiz_gec_is_bir_kez_gorunur(self):  # inceleme S5
        self.kesinlestir()
        k = kayit(66, bit="2026-11-27", done="2026-12-02T09:00:00Z")
        d = self.aralik(k)
        self.assertEqual(
            (kodlar(d, "u-ayse", "gec"), efor(d, "u-ayse")), (["MOGEM-66"], 0)
        )
        self.arsiv.yaz(d | {"durum": "kesin"})
        self.assertEqual(dokum(k, ay="2027-01", arsiv=self.arsiv.oku())["kisiler"], {})

    def test_kesinlesmemis_ayin_isi_gec_olmaz(self):
        self.assertEqual(
            self.aralik(kayit(67, etiket=["LG"], bit="2026-11-20"))["kisiler"], {}
        )

    def test_kesinlesen_ay_ustune_yazilmaz_ve_iz_birakmaz(self):
        self.kesinlestir()
        with self.assertRaises(FileExistsError):
            self.kesinlestir()
        self.assertEqual(
            sorted(p.name for p in Path(self.klasor.name).iterdir()), ["2026-11.json"]
        )


class Donma(
    unittest.TestCase
):  # (26) kesinleşmiş ayda sayılan iş sonradan eklenene sayılmaz
    def test_sonradan_eklenen_kisiye_sayilmaz(self):
        with tempfile.TemporaryDirectory() as t:
            arsiv = Arsiv(t)
            arsiv.yaz(
                dokum(kayit(90, etiket=["LG"], bit="2026-11-20")) | {"durum": "kesin"}
            )
            d = dokum(
                kayit(90, kim=("u-ayse", "u-efe"), etiket=["LG"], bit="2026-11-20"),
                ay="2026-12",
                arsiv=arsiv.oku(),
            )
            self.assertEqual(d["kisiler"], {})

    def test_suresizken_eklenen_kisi_sure_gelince_sayilir(self):
        with tempfile.TemporaryDirectory() as t:
            arsiv = Arsiv(t)
            arsiv.yaz(
                dokum(kayit(91, etiket=["toplantı"], bit="2026-11-16"))
                | {"durum": "kesin"}
            )
            d = dokum(
                kayit(
                    91,
                    kim=("u-ayse", "u-efe"),
                    etiket=["toplantı", "T1"],
                    bit="2026-11-16",
                ),
                ay="2026-12",
                arsiv=arsiv.oku(),
            )
            self.assertEqual((efor(d, "u-ayse"), efor(d, "u-efe")), (1, 1))


class UstGorevUyarisi(unittest.TestCase):  # (27)
    def test_farkli_kisideki_ust_gorev_uyari_verir(self):
        d = dokum(
            kayit(92, kim=("u-ayse",), etiket=["LG"], bit="2026-11-09"),
            kayit(93, kim=("u-efe",), etiket=["XS"], bit="2026-11-09", ust=92),
        )
        self.assertEqual([u["kod"] for u in d["uyarilar"]], ["MOGEM-92"])

    def test_ayni_kisideki_ust_gorev_uyari_vermez(self):
        d = dokum(
            kayit(94, etiket=["LG"], bit="2026-11-09"),
            kayit(95, etiket=["XS"], bit="2026-11-09", ust=94),
        )
        self.assertEqual(d["uyarilar"], [])


class Takvim(unittest.TestCase):
    def test_gun_ve_is_gunu_sayilari(self):  # (8) tatil istisnası yok
        for ay, gun, is_gunu in (
            ("2026-11", 30, 21),
            ("2026-12", 31, 23),
            ("2027-02", 28, 20),
            ("2028-02", 29, 21),
        ):
            t = hesap.takvim(ay)
            self.assertEqual((len(t["gunler"]), t["is_gunu"]), (gun, is_gunu), ay)
        self.assertTrue(
            hesap.takvim("2026-11")["gunler"][0]["hafta_sonu"]
        )  # 1 Kasım 2026 pazar

    def test_cizgi(self):
        g = hesap.gorevleri_kur(
            cekim(
                kayit(
                    70, bas="2026-11-02", bit="2026-11-03", done="2026-10-29T08:00:00Z"
                ),
                kayit(
                    71, bas="2026-11-25", bit="2026-11-20"
                ),  # başlangıç bitişten sonra
                kayit(72, bas="2026-10-28", bit="2026-12-02"),  # ay taşıyor
                kayit(73, done="2026-11-07T10:00:00Z"),  # yalnız Done günü
                kayit(74, bit="2026-10-02"),  # ay dışı
            )
        )
        self.assertEqual(
            [hesap.cizgi(x, "2026-11") for x in g],
            [[2, 3], [20, 20], [1, 30], [7, 7], None],
        )


class Kesinlesme(unittest.TestCase):
    def aylar(self, iso, arsiv=()):
        return hesap.kesinlesecek_aylar(
            datetime.fromisoformat(iso), {a: {} for a in arsiv}
        )

    def test_ayin_biri_00_30(self):  # (4) İstanbul saati, 00:30:00 dahil
        self.assertEqual(self.aylar("2026-11-30T21:29:59+00:00"), [])
        self.assertEqual(self.aylar("2026-11-30T21:30:00+00:00"), ["2026-11"])

    def test_yil_donumu(self):
        self.assertEqual(
            self.aylar("2026-12-31T21:10:00+00:00", ["2026-11"]), []
        )  # 1 Oca 00:10
        self.assertEqual(
            self.aylar("2026-12-31T21:40:00+00:00", ["2026-11"]), ["2026-12"]
        )  # 1 Oca 00:40

    def test_atlanan_calisma_telafi_edilir(self):  # S9
        self.assertEqual(
            self.aylar("2027-01-05T09:00:00+00:00"), ["2026-11", "2026-12"]
        )


class KomutSatiri(unittest.TestCase):
    def calistir(self, t, *ek, kayitlar=()):
        Path(t, "c.json").write_text(json.dumps(cekim(*kayitlar)), encoding="utf-8")
        return cli.main(
            [
                "--cekim",
                f"{t}/c.json",
                "--arsiv",
                f"{t}/arsiv",
                "--cikti",
                f"{t}/canli",
                *ek,
            ]
        )

    def test_plane_dusukse_dosya_yazilmaz(self):  # S9
        with (
            tempfile.TemporaryDirectory() as t,
            mock.patch.object(plane, "cek", side_effect=plane.PlaneHatasi("HTTP 502")),
        ):
            kod = cli.main(
                [
                    "--arsiv",
                    f"{t}/arsiv",
                    "--cikti",
                    f"{t}/canli",
                    "--simdi",
                    "2026-12-01T09:00:00+00:00",
                ]
            )
            self.assertEqual((kod, list(Path(t).iterdir())), (2, []))

    def test_kesinlestirir_canli_kopyayi_siler_acik_ayi_uretir(self):
        with tempfile.TemporaryDirectory() as t:
            k = [kayit(80, etiket=["LG"], bit="2026-11-20")]
            self.assertEqual(
                self.calistir(t, "--simdi", "2026-11-25T10:00", kayitlar=k), 0
            )
            self.assertTrue(Path(t, "canli", "2026-11.json").exists())
            self.assertEqual(
                self.calistir(t, "--simdi", "2026-12-01T09:00:00+00:00", kayitlar=k), 0
            )
            kasim = json.loads(
                Path(t, "arsiv", "2026-11.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                (kasim["durum"], kasim["kisiler"]["u-ayse"]["efor"]), ("kesin", "2.5")
            )
            self.assertEqual(kasim["planlanan"], "2026-12-01T00:30+03:00")
            self.assertFalse(Path(t, "canli", "2026-11.json").exists())
            self.assertTrue(Path(t, "canli", "2026-12.json").exists())

    def test_saat_dilimsiz_simdi_istanbul_saatidir(self):
        with tempfile.TemporaryDirectory() as t:
            self.calistir(
                t, "--simdi", "2026-12-01T00:20"
            )  # İstanbul 00:20: Kasım henüz kesinleşmez
            self.assertFalse(Path(t, "arsiv", "2026-11.json").exists())

    def test_baslangictan_onceki_ya_da_kesin_ay_icin_canli_uretilmez(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(self.calistir(t, "--ay", "2026-10"), 4)
            self.calistir(t, "--simdi", "2026-12-01T09:00:00+00:00")
            self.assertEqual(self.calistir(t, "--ay", "2026-11"), 4)


class PlaneCekim(unittest.TestCase):
    def sahte(self, sayfalar, toplam):
        def _istek(adres, anahtar, yol, parametre=None):
            if yol == "members/":
                return list(
                    UYELER
                    and [
                        {
                            "id": "u-ayse",
                            "display_name": "ayse.kaya",
                            "first_name": "Ayşe",
                        }
                    ]
                )
            if yol.endswith("states/"):
                return {
                    "results": [{"id": "s-done", "name": "Done", "group": "completed"}]
                }
            if yol.endswith("labels/"):
                return {"results": [{"id": "lbl-lg", "name": "LG"}]}
            i = int(parametre["cursor"].split(":")[1])
            son = i == len(sayfalar) - 1
            return {
                "results": sayfalar[i],
                "total_count": toplam,
                "next_page_results": not son,
                "next_cursor": None if son else f"100:{i + 1}:0",
            }

        return _istek

    def test_sayfalama_ve_toplam(self):
        with mock.patch.object(
            plane, "_istek", self.sahte([[kayit(1)], [kayit(2)]], 2)
        ):
            c = plane.cek("anahtar")
        self.assertEqual(
            (len(c["kayitlar"]), c["etiketler"], c["durumlar"]["s-done"]["grup"]),
            (2, {"lbl-lg": "LG"}, "completed"),
        )

    def test_eksik_sayfa_fark_edilir(self):
        with (
            mock.patch.object(plane, "_istek", self.sahte([[kayit(1)]], 5)),
            self.assertRaises(plane.PlaneHatasi),
        ):
            plane.cek("anahtar")

    def test_https_zorunlu(self):
        with self.assertRaises(plane.PlaneHatasi):
            plane.cek("anahtar", adres="http://plane.example.com")

    def test_json_olmayan_yanit_yeniden_denenir_sonra_hata(self):
        sahte_yanit = mock.MagicMock()
        sahte_yanit.__enter__.return_value.read.return_value = (
            b"<html>vekil hata</html>"
        )
        with (
            mock.patch("urllib.request.urlopen", return_value=sahte_yanit) as u,
            mock.patch("time.sleep"),
            self.assertRaises(plane.PlaneHatasi) as h,
        ):
            plane._istek("https://x", "gizli-anahtar", "members/")
        self.assertEqual(u.call_count, 3)
        self.assertNotIn("gizli-anahtar", str(h.exception))


if __name__ == "__main__":
    unittest.main()
