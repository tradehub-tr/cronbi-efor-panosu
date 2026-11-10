"""Efor hesabı — Plane kayıtlarından kişi × ay dökümü. Saf fonksiyonlar; ağ ve dosya yok.

Kurallar (görev klasörü KARARLAR.md):
  • kime: atanan herkese tam süre (1), dışlanan hesaplar hariç (14); kişi Plane üye kimliğiyle tutulur
  • hangi ay: Done değilse yok → bitiş tarihinin ayı → yoksa Done'a çekildiği günün ayı, İstanbul saatiyle (2)
  • ne kadar: gün etiketi (T1–T4) → boy etiketi (XS–XL) → yoksa süre boş, toplama girmez (3, 16, 20, 23)
  • geç kapanan: kesinleşmiş bir aya ait olup orada sayılmamış iş, açık olan aya sayılır (12, 15)
  • tek ödeme: kesinleşmiş bir ayda sayılmış iş donar; kimseye bir daha sayılmaz (4, 26)
"""

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from . import ayarlar

_BOY = {b.upper() for b in ayarlar.BOY_ETIKETLERI}
_GUN = {k.upper(): v for k, v in ayarlar.GUN_ETIKETI.items()}
_TOPLANTI = {t.casefold() for t in ayarlar.TOPLANTI_ETIKETLERI}


class VeriHatasi(Exception):
    """Plane çekimi beklenmeyen biçimde; sessizce yanlış hesaplamak yerine durulur."""


@dataclass
class Gorev:
    kod: str
    ad: str
    durum: str
    grup: str
    atananlar: list
    etiketler: list
    bas: date | None
    bit: date | None
    done: date | None
    bagli_is: str | None = None
    ust_gorev: bool = False
    # üst görev, alt görevlerinin hiçbirinde atanmamış birine ait
    ust_farkli: bool = False
    boy: str | None = field(init=False)
    gun_etiketi: str | None = field(init=False)
    efor: Decimal | None = field(init=False)
    toplanti: bool = field(init=False)
    uyari: str | None = field(init=False, default=None)

    def __post_init__(self):
        boylar = [e.upper() for e in self.etiketler if e.upper() in _BOY]
        gunler = [e.upper() for e in self.etiketler if e.upper() in _GUN]
        if len(boylar) > 1 or len(gunler) > 1:
            self.uyari = "Birden çok boy ya da gün etiketi var; ilki kullanıldı"
        self.boy = boylar[0] if boylar else None
        self.gun_etiketi = gunler[0] if gunler else None
        gun = _GUN.get(self.gun_etiketi)
        self.toplanti = gun is not None or any(
            e.casefold() in _TOPLANTI for e in self.etiketler
        )
        # Alt görevleri ayrıca sayılan üst görev çift sayılmasın diye süresiz kalır (ORTAK.md §4 kuralı).
        if self.ust_gorev:
            self.efor = None
        else:
            # Gün etiketi kararlaştırılmış süredir; görevde boy da varsa ondan önce gelir.
            self.efor = gun if gun is not None else ayarlar.BOY_GUN.get(self.boy)

    @property
    def tamam(self):
        return self.grup == "completed"

    @property
    def acik(self):
        return self.grup in ayarlar.ACIK_GRUPLAR or self.durum in ayarlar.ACIK_ADLAR

    @property
    def ay(self):
        if not self.tamam:
            return None
        gun = self.bit or self.done
        return f"{gun:%Y-%m}" if gun else None


def _tarih(deger):
    return date.fromisoformat(deger[:10]) if deger else None


def _done_gunu(deger):
    """Plane completed_at UTC tutar; gün İstanbul saatine göre belirlenir (31 Eki 22:30 UTC = 1 Kasım)."""
    if not deger:
        return None
    return datetime.fromisoformat(deger).astimezone(ayarlar.SAAT_DILIMI).date()


def _etiket_adlari(r, etiketler):
    out = []
    for e in r.get("labels") or []:
        ad = e.get("name") if isinstance(e, dict) else etiketler.get(e)
        if ad is None:
            raise VeriHatasi(f"MOGEM-{r['sequence_id']}: çözülemeyen etiket {e!r}")
        out.append(ad.strip())
    return out


def gorevleri_kur(cekim):
    """Plane çekimini (plane.cek çıktısı) Gorev listesine çevirir."""
    kayitlar, durumlar = cekim["kayitlar"], cekim["durumlar"]
    etiketler = cekim.get("etiketler") or {}
    kimlik = {r["id"]: r for r in kayitlar}

    def grup(r):
        if r["state"] not in durumlar:
            raise VeriHatasi(f"MOGEM-{r['sequence_id']}: bilinmeyen durum {r['state']}")
        return durumlar[r["state"]]["grup"]

    # İptal edilen ya da rafa kaldırılan alt görev üst görevin süresini düşürmez.
    cocuk_atananlar = {}
    for r in kayitlar:
        if r.get("parent") and grup(r) not in ("cancelled", "backlog"):
            cocuk_atananlar.setdefault(r["parent"], set()).update(
                r.get("assignees") or []
            )

    def kok_ad(r):
        adim = 0
        while r.get("parent") in kimlik and adim < 20:
            r, adim = kimlik[r["parent"]], adim + 1
        return r["name"] if adim else None

    return [
        Gorev(
            kod=f"MOGEM-{r['sequence_id']}",
            ad=r["name"],
            grup=grup(r),
            durum=durumlar[r["state"]]["ad"],
            atananlar=list(r.get("assignees") or []),
            etiketler=_etiket_adlari(r, etiketler),
            bas=_tarih(r.get("start_date")),
            bit=_tarih(r.get("target_date")),
            done=_done_gunu(r.get("completed_at")),
            bagli_is=kok_ad(r),
            ust_gorev=r["id"] in cocuk_atananlar,
            ust_farkli=r["id"] in cocuk_atananlar
            and not set(r.get("assignees") or []) & cocuk_atananlar[r["id"]],
        )
        for r in kayitlar
    ]


def takvim(ay):
    """Ayın bütün günleri (takvimden; tatil istisnası yok, hafta sonu işaretli — karar 8)."""
    yil, a = map(int, ay.split("-"))
    gunler = [date(yil, a, g) for g in range(1, monthrange(yil, a)[1] + 1)]
    return {
        "gunler": [
            {"gun": g.isoformat(), "hafta_sonu": g.weekday() >= 5} for g in gunler
        ],
        "is_gunu": sum(g.weekday() < 5 for g in gunler),
    }


def cizgi(g, ay):
    """Takvim çubuğu: başlangıç → (bitiş ya da Done günü); ayın içine kırpılır. Ay dışındaysa None."""
    son = g.bit or g.done or g.bas
    bas = g.bas or son
    if not son:
        return None
    bas = min(bas, son)
    yil, a = map(int, ay.split("-"))
    ilk, sonG = date(yil, a, 1), date(yil, a, monthrange(yil, a)[1])
    if son < ilk or bas > sonG:
        return None
    return [max(bas, ilk).day, min(son, sonG).day]


def _ayi(t):
    return f"{t:%Y-%m}" if t else None


def _acikta_gorunur(g, ay):
    """Done olmayan iş: başlangıcı ya da bitişi bu ayda, ya da bitişi panonun önceki bir ayında geçmiş."""
    bit_ay = _ayi(g.bit)
    return ay in (_ayi(g.bas), bit_ay) or bool(
        bit_ay and ayarlar.BASLANGIC_AYI <= bit_ay < ay
    )


def _arsivde_gorundu(arsiv, kisi, kod):
    """Bu iş kesinleşmiş bir ayın dökümünde bu kişiye (süresiz de olsa) zaten göründü mü."""
    for dokum in arsiv.values():
        k = dokum["kisiler"].get(kisi)
        if k and any(s["kod"] == kod for s in k["sayilan"] + k["gec"] + k["bos"]):
            return True
    return False


def _birine_sayildi(arsiv, kod):
    """Kesinleşmiş bir ayda herhangi birine süresiyle sayıldıysa iş donmuştur (karar 26)."""
    return any(
        s["kod"] == kod and s["efor"] is not None
        for dokum in arsiv.values()
        for k in dokum["kisiler"].values()
        for s in k["sayilan"] + k["gec"]
    )


def _satir(g, ay):
    return {
        "kod": g.kod,
        "ad": g.ad,
        "durum": g.durum,
        "boy": g.boy,
        "etiket": g.gun_etiketi,
        "ust": g.ust_gorev,
        "efor": None if g.efor is None else str(g.efor),
        "toplanti": g.toplanti,
        "bagli_is": g.bagli_is,
        "bas": g.bas and g.bas.isoformat(),
        "bit": g.bit and g.bit.isoformat(),
        "done": g.done and g.done.isoformat(),
        "cizgi": cizgi(g, ay),
    }


def ay_dokumu(gorevler, ay, arsiv=None, uyeler=None):
    """Açık (kesinleşmemiş) bir ayın kişi bazında dökümü.

    arsiv: {ay: kesinleşmiş döküm} — geç kapanan ve tek ödeme buradan bulunur.
    uyeler: plane.cek çıktısındaki {id: {ad, isim}}; listede olmayan atanan "tanınmayan üye" olur.
    """
    arsiv, uyeler = arsiv or {}, uyeler or {}
    kisiler, uyarilar = {}, []

    def kisi(uid):
        u = uyeler.get(uid) or {"ad": uid, "isim": "Tanınmayan üye"}
        return kisiler.setdefault(
            uid,
            {
                "id": uid,
                "ad": u["ad"],
                "isim": u["isim"] or u["ad"],
                "sayilan": [],
                "gec": [],
                "bos": [],
                "acik": [],
            },
        )

    def uyar(g, neden):
        uyarilar.append({"kod": g.kod, "ad": g.ad, "neden": neden})

    for g in gorevler:
        if g.grup == "cancelled":
            continue
        gay = g.ay
        hedefler = [u for u in g.atananlar if u not in ayarlar.HARIC_UYELER]
        if g.tamam and gay == ay and not g.atananlar:
            uyar(g, "Done ama kimseye atanmamış; kimseye sayılmadı")
        if g.tamam and gay is None and _ayi(g.bas) == ay:
            uyar(g, "Done ama bitiş tarihi ve Done günü yok; hiçbir aya sayılmadı")
        if g.uyari and gay == ay:
            uyar(g, g.uyari)
        if g.ust_farkli and g.tamam and gay == ay:
            uyar(
                g,
                "Üst görev, alt görevlerinden farklı kişide; üst görevin süresi sayılmadı",
            )
        # Kesinleşmiş ayda ödenmiş iş donar: tarihi taşınsa, yeniden açılsa ya da sonradan
        # başkası atansa da kimseye bir daha sayılmaz (karar 4, 26).
        dondu = _birine_sayildi(arsiv, g.kod)
        for u in hedefler:
            if u not in uyeler and gay == ay:
                uyar(g, f"Atanan kişi Plane üye listesinde yok ({u})")
            if dondu:
                continue
            if gay == ay:
                kisi(u)["sayilan" if g.efor is not None else "bos"].append(
                    _satir(g, ay)
                )
            elif gay and ayarlar.BASLANGIC_AYI <= gay < ay and gay in arsiv:
                # Süresiz geç iş bir kez görünür; sonradan süre kazanırsa o zaman sayılır.
                if g.efor is not None or not _arsivde_gorundu(arsiv, u, g.kod):
                    kisi(u)["gec"].append(_satir(g, ay))
            elif g.acik and _acikta_gorunur(g, ay):
                kisi(u)["acik"].append(_satir(g, ay))

    for k in kisiler.values():
        for liste in ("sayilan", "gec", "bos", "acik"):
            k[liste].sort(
                key=lambda s: (s["bas"] or s["bit"] or s["done"] or "", s["kod"])
            )
        k["efor"] = str(
            sum(
                (Decimal(s["efor"]) for s in k["sayilan"] + k["gec"] if s["efor"]),
                Decimal(0),
            )
        )
    return {
        "ay": ay,
        **takvim(ay),
        "kisiler": dict(
            sorted(kisiler.items(), key=lambda kv: kv[1]["isim"].casefold())
        ),
        "uyarilar": uyarilar,
    }


def kesinlesme_ani(ay):
    """Ayın kesinleşeceği an: sonraki ayın 1'i 00:30, İstanbul (karar 4)."""
    yil, a = map(int, ay.split("-"))
    yil, a = (yil + 1, 1) if a == 12 else (yil, a + 1)
    return datetime(yil, a, 1, 0, 30, tzinfo=ayarlar.SAAT_DILIMI)


def kesinlesecek_aylar(simdi, arsiv):
    """Kesinleşme anı geçmiş ama arşivde olmayan aylar, eskiden yeniye.

    Bir çalışma atlanırsa sonraki çalışma eksik ayı da kesinleştirir.
    """
    out = []
    y, m = map(int, ayarlar.BASLANGIC_AYI.split("-"))
    while kesinlesme_ani(ay := f"{y:04d}-{m:02d}") <= simdi:
        if ay not in arsiv:
            out.append(ay)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out
