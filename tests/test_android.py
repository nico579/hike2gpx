"""Les profils BRouter de l'application Android (tools/profils_android.py).

Le téléphone calcule sur les RD5 des lots avec des profils versionnés dans
ses assets : s'ils dérivaient de ceux du PC (une correction de REMPLACEMENTS,
un nouveau fournisseur dans la clé hike2gpx), le même lot donnerait deux
itinéraires différents. Ce test le signale.
"""
import hashlib
from pathlib import Path

from hike2gpx import brouter
from tools import profils_android

ASSETS = Path(__file__).resolve().parents[1] / "android" / "app" / "src" / "main" / "assets" / "brouter"
REFERENCE = Path(__file__).with_name("donnees") / "hiking-mountain-1.7.10.brf"
# lookups.dat de BRouter 1.7.10 (misc/profiles2), fins de ligne LF.
LOOKUPS_SHA256 = "bf8fc3b2c052b7204e9c5a8d78e4d6ab6b125d3236a943f34583b838c477f419"


def test_profils_android_a_jour():
    lookups = (ASSETS / "osm" / "lookups.dat").read_bytes()
    assert hashlib.sha256(lookups).hexdigest() == LOOKUPS_SHA256
    attendus = profils_android.profils(lookups.decode("utf-8"), REFERENCE.read_text(encoding="utf-8"))
    for relatif, texte in attendus.items():
        assert (ASSETS / relatif).read_bytes().decode("utf-8") == texte, \
            f"{relatif} a dérivé : relancer python tools/profils_android.py"


def test_profil_enrichi_connait_les_chemins_officiels():
    profil = (ASSETS / "enrichi" / f"{brouter.PROFIL}.brf").read_text(encoding="utf-8")
    assert "assign chemins_officiels = 1" in profil
    assert brouter.CLE_IGN in (ASSETS / "enrichi" / "lookups.dat").read_text(encoding="utf-8")
