"""Plane'den salt-okuma çekim. Hiçbir uca yazmaz.

Anahtar PLANE_API_KEY ortam değişkeninden okunur (GitHub'da gizli değişken, yerelde kökteki .env.pano).
Anahtar hiçbir çıktıya, hata mesajına ya da dosyaya yazılmaz.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

from . import ayarlar

ALANLAR = (
    "id,sequence_id,name,state,assignees,labels,start_date,target_date,"
    "completed_at,created_at,updated_at,parent"
)


class PlaneHatasi(Exception):
    """Plane'e ulaşılamadı ya da beklenmeyen yanıt döndü. Mesajda anahtar yoktur."""


def _istek(adres, anahtar, yol, parametre=None, deneme=3):
    url = f"{adres}/api/v1/workspaces/{ayarlar.WORKSPACE}/{yol}"
    if parametre:
        url += "?" + urllib.parse.urlencode(parametre)
    req = urllib.request.Request(
        url, headers={"X-API-Key": anahtar, "Accept": "application/json"}
    )
    son = None
    for i in range(deneme):
        try:
            with urllib.request.urlopen(req, timeout=60) as yanit:
                return json.loads(yanit.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # 429 hız sınırı ve 5xx beklenip yeniden denenir; diğer 4xx kalıcıdır.
            if e.code < 500 and e.code != 429:
                raise PlaneHatasi(f"{yol} → HTTP {e.code}") from None
            son = f"{yol} → HTTP {e.code}"
        except ValueError:
            # 200 dönen ama JSON olmayan yanıt (vekil sunucunun hata sayfası gibi)
            son = f"{yol} → JSON olmayan yanıt"
        except OSError as e:  # URLError, bağlantı kopması, zaman aşımı
            son = f"{yol} → bağlantı hatası ({type(e).__name__})"
        time.sleep(2 * (i + 1))
    raise PlaneHatasi(son)


def _liste(d):
    return d if isinstance(d, list) else d.get("results", [])


def anahtar_dosyadan(yol):
    """Yerel geliştirme: 'PLANE_API_KEY=…' satırı olan dosyadan okur. Kabukta `source` edilmez —
    değer bozuksa kabuk onu komut sanıp hata mesajında yazdırır (ölçüldü 10 Kas 2026)."""
    with open(yol, encoding="utf-8") as f:
        for satir in f:
            if satir.startswith("PLANE_API_KEY="):
                return satir.split("=", 1)[1].strip()
    raise PlaneHatasi(f"{yol} içinde PLANE_API_KEY satırı yok")


def cek(anahtar=None, adres=None):
    """Projedeki tüm iş öğelerini, üyeleri, durumları ve etiketleri döndürür.

    Dönüş: {"kayitlar": [...], "uyeler": {id: {ad, isim}}, "durumlar": {id: {ad, grup}},
            "etiketler": {id: ad}, "cekim": ISO zaman}
    Arşivlenmiş iş öğeleri listede yoktur: Plane arşiv ucu bu sürümde 404 dönüyor (ölçüldü 10 Kas 2026).
    """
    anahtar = anahtar or os.environ.get("PLANE_API_KEY")
    if not anahtar:
        raise PlaneHatasi("PLANE_API_KEY tanımlı değil")
    adres = (
        adres or os.environ.get("PLANE_BASE_URL") or ayarlar.PLANE_VARSAYILAN_ADRES
    ).rstrip("/")
    if not adres.startswith("https://"):
        raise PlaneHatasi("Plane adresi https olmalı (anahtar şifresiz gönderilmez)")

    uyeler = {
        m["id"]: {
            "ad": m.get("display_name") or m["id"],
            "isim": " ".join(
                x for x in (m.get("first_name"), m.get("last_name")) if x
            ).strip(),
        }
        for m in _liste(_istek(adres, anahtar, "members/"))
    }
    proje = f"projects/{ayarlar.PROJE}"
    durumlar = {
        s["id"]: {"ad": s["name"], "grup": s["group"]}
        for s in _liste(_istek(adres, anahtar, f"{proje}/states/", {"per_page": 100}))
    }
    etiketler = {
        e["id"]: e["name"]
        for e in _liste(_istek(adres, anahtar, f"{proje}/labels/", {"per_page": 100}))
    }

    kayitlar, imlec, beklenen = [], "100:0:0", None
    while True:
        d = _istek(
            adres,
            anahtar,
            f"{proje}/work-items/",
            {"per_page": 100, "cursor": imlec, "expand": "labels", "fields": ALANLAR},
        )
        beklenen = d.get("total_count", beklenen)
        kayitlar.extend(d.get("results", []))
        if not d.get("next_page_results"):
            break
        if not d.get("next_cursor"):
            raise PlaneHatasi("work-items → sonraki sayfa imleci yok")
        imlec = d["next_cursor"]
    if beklenen is not None and len(kayitlar) != beklenen:
        raise PlaneHatasi(
            f"work-items → {beklenen} kayıt bekleniyordu, {len(kayitlar)} geldi"
        )

    return {
        "kayitlar": kayitlar,
        "uyeler": uyeler,
        "durumlar": durumlar,
        "etiketler": etiketler,
        "cekim": datetime.now(UTC).isoformat(timespec="seconds"),
    }
