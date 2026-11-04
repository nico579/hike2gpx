"""Les profils BRouter de l'application Android (tools/profils_android.py).

Le téléphone calcule sur les RD5 des lots avec des profils versionnés dans
ses assets : s'ils dérivaient de ceux du PC (une correction de REMPLACEMENTS,
un nouveau fournisseur dans la clé hike2gpx), le même lot donnerait deux
itinéraires différents. Ce test le signale.
"""
import hashlib
import re
import xml.etree.ElementTree as ET
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


def test_l_application_parle_anglais_et_francais():
    # L'anglais par défaut (values), le français dans values-fr, comme
    # watch2notif : mêmes clés et mêmes arguments (%1$s, %2$d…) dans chaque
    # phrase, pour qu'aucune ne manque ni n'inverse ses valeurs dans une langue.
    res = ASSETS.parents[1] / "res"

    def phrases(dossier):
        racine = ET.parse(res / dossier / "strings.xml").getroot()
        return {s.get("name"): sorted(re.findall(r"%\d\$[.0-9]*[sdf]", s.text or ""))
                for s in racine.iter("string") if s.get("translatable") != "false"}

    anglais, francais = phrases("values"), phrases("values-fr")
    assert anglais.keys() == francais.keys(), anglais.keys() ^ francais.keys()
    assert {k: v for k, v in anglais.items() if francais[k] != v} == {}
