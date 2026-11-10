"""Kilit: kullanıcı adı + şifreden PBKDF2-SHA256 (600 000 tur) ile anahtar, AES-256-GCM ile şifreleme.

Tarayıcıdaki WebCrypto aynı yöntemi kullanır (sablon.html → coz()); biri değişirse öteki de değişir.
Tuz kullanıcı adından ve kilidin amacından ("sayfa" / "arsiv") türetilir: anahtar her yayında aynı kalır,
böylece tarayıcının oturum boyunca sakladığı anahtar gece güncellemesinden sonra da açar (karar 33).
Arşiv sayfa şifresiyle kilitlenir ama ayrı tuzla (karar 35).
"""

import base64
import hashlib
import json
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

TUR = 600_000
SURUM = 1


class SifreHatasi(Exception):
    """Kullanıcı adı ya da şifre yanlış, veya kilitli veri bozulmuş."""


def _b64(b):
    return base64.b64encode(b).decode()


def tuz(kullanici, amac):
    return hashlib.sha256(
        f"cronbi-efor-panosu\x00{amac}\x00{kullanici}".encode()
    ).digest()[:16]


def anahtar(kullanici, sifre, amac):
    if not kullanici or not sifre:
        raise SifreHatasi("kullanıcı adı ve şifre boş olamaz")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=tuz(kullanici, amac), iterations=TUR
    )
    return kdf.derive(f"{kullanici}\x00{sifre}".encode())


def kilitle(veri, anahtar_):
    """bytes → kilitli paket (JSON'a yazılabilir sözlük). Her kilitlemede yeni rastgele IV."""
    iv = os.urandom(12)
    return {
        "v": SURUM,
        "tur": TUR,
        "iv": _b64(iv),
        "veri": _b64(AESGCM(anahtar_).encrypt(iv, veri, None)),
    }


def ac(paket, anahtar_):
    if paket.get("v") != SURUM or paket.get("tur") != TUR:
        raise SifreHatasi(f"bilinmeyen kilit biçimi: v{paket.get('v')}")
    try:
        return AESGCM(anahtar_).decrypt(
            base64.b64decode(paket["iv"]), base64.b64decode(paket["veri"]), None
        )
    except InvalidTag:
        raise SifreHatasi("kullanıcı adı ya da şifre yanlış") from None


def json_kilitle(nesne, anahtar_):
    return kilitle(json.dumps(nesne, ensure_ascii=False).encode("utf-8"), anahtar_)


def json_ac(paket, anahtar_):
    return json.loads(ac(paket, anahtar_).decode("utf-8"))
