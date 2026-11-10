"""Kesinleşmiş ayların saklandığı yer. Kesinleşen ay bir daha yazılmaz.

F1: düz JSON, yerel klasörde (git dışı). F3'te aynı arayüz şifreli saklamaya geçer (repo herkese açık).
"""

import json
import os
from pathlib import Path


class Arsiv:
    def __init__(self, klasor):
        self.klasor = Path(klasor)

    def oku(self):
        if not self.klasor.exists():
            return {}
        return {
            p.stem: json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(self.klasor.glob("????-??.json"))
        }

    def yaz(self, dokum):
        hedef = self.klasor / f"{dokum['ay']}.json"
        if hedef.exists():
            raise FileExistsError(
                f"{dokum['ay']} zaten kesinleşmiş; kesinleşen ay değiştirilmez"
            )
        self.klasor.mkdir(parents=True, exist_ok=True)
        # Yarıda kesilen yazma bozuk bir kesin ay bırakmasın: önce geçici dosya, sonra tek adımda taşı.
        gecici = hedef.with_suffix(".json.yaziliyor")
        gecici.write_text(
            json.dumps(dokum, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        os.replace(gecici, hedef)
        return hedef
