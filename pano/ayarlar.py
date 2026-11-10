"""Pano kuralları ve sabitleri — kararların tek yeri.

Kararların kaydı görev klasöründe (KARARLAR.md); burada yalnız uygulanan değerler durur.
Bir değer değişirse önce karar yazılır, sonra burası güncellenir.
"""

import json
import os
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

SAAT_DILIMI = ZoneInfo("Europe/Istanbul")

# Panonun başladığı ay; öncesine ait görev hiçbir aya sayılmaz (karar 5, 21).
BASLANGIC_AYI = "2026-11"

# Plane
PLANE_VARSAYILAN_ADRES = "https://plane.turksab.com"
WORKSPACE = "mogem"
PROJE = "bec934dc-feec-48e5-8402-4d1f41cb197a"

# Durum Plane'in durum grubundan okunur (completed / cancelled / started / unstarted / backlog);
# yeni bir durum açılırsa grubu sayesinde kendiliğinden doğru yere düşer.
# Done olmadığı hâlde dökümde "sayılmadı" diye görünenler: başlamış ve planlanmış işler.
# Sprint Backlog Plane'de backlog grubunda ama sprinte alınmış iştir; Icebox/Product Backlog görünmez.
ACIK_GRUPLAR = {"started", "unstarted"}
ACIK_ADLAR = {"Sprint Backlog"}

# Boy etiketi → gün (SP tablosu, karar 3; 1 gün = 8 saat). XXL bilerek yok: süre boş kalır (karar 23).
BOY_GUN = {
    "XS": Decimal(3) / 8,
    "SM": Decimal("6.5") / 8,
    "MD": Decimal("1.5"),
    "LG": Decimal("2.5"),
    "XL": Decimal("3.5"),
}
BOY_ETIKETLERI = ("XS", "SM", "MD", "LG", "XL", "XXL")

# Toplantı gün etiketleri (karar 20). Yeni T etiketi açılırsa buraya satır eklenir.
GUN_ETIKETI = {
    "T1": Decimal(1),
    "T2": Decimal(2),
    "T3": Decimal(3),
    "T4": Decimal(4),
}

# Bu etiketlerden biri ya da bir gün etiketi taşıyan görev "Toplantı" sınıfındadır (karar 22).
TOPLANTI_ETIKETLERI = {"toplantı", "çalıştay", "çaşıştay"}


# Kişiye ait ayarlar repoda durmaz (repo herkese açık): GitHub'da PANO_KISILER gizli değişkeni,
# yerelde git dışı kisiler.json. Biçim: {"haric": {üye kimliği: not}, "ad": {üye kimliği: "Ad Soyad"}}
#  · haric — panoda görünmeyen hesaplar; kimlikle tutulur, görünen ad değişse de dışlama sürer (karar 14, 25)
#  · ad — Plane'de eksik ya da yanlış ad için elle düzeltme; ötekiler Türkçe büyük harf kuralıyla türetilir (karar 29)
def _kisiler():
    ham = os.environ.get("PANO_KISILER")
    yerel = Path(__file__).resolve().parents[1] / "kisiler.json"
    if not ham and yerel.exists():
        ham = yerel.read_text(encoding="utf-8")
    return json.loads(ham) if ham else {"haric": {}, "ad": {}}


_KISILER = _kisiler()
HARIC_UYELER = _KISILER.get("haric", {})
AD_DUZELTME = _KISILER.get("ad", {})
