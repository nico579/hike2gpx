"""Validation de la planification Linux, sans lancer de service système."""
import json
import os
from pathlib import Path

import pytest

from deploy.linux import refresh


def test_zones_exemple_respectent_les_providers():
    chemin = Path(__file__).resolve().parents[1] / "deploy/linux/zones.example.json"
    zones = refresh.zones_valides(json.loads(chemin.read_text(encoding="utf-8")))
    assert {z["source"] for z in zones} == {"ign", "atkis", "zabaged", "swisstlm3d", "bdot10k_ds"}


@pytest.mark.parametrize("changement", [
    {"pays": "de"},
    {"zone": [43.0, 5.0, 45.0, 7.0]},
    {"modes": ["inconnu"]},
    {"renouvellement_jours": 0},
])
def test_zone_invalide_refusee(changement):
    zone = {"id": "fr-test", "pays": "fr", "source": "ign",
            "zone": [43.42, 5.98, 43.49, 6.08],
            "renouvellement_jours": 30, "modes": ["strict"]}
    zone.update(changement)
    with pytest.raises(ValueError):
        refresh.zones_valides({"zones": [zone]})


def test_nettoyage_garde_le_paquet_courant_et_le_delai_de_transfert(tmp_path):
    zone = {"id": "fr-test", "source": "ign", "zone": [43.3, 6.0, 43.35, 6.05],
            "modes": ["strict"]}
    racine = tmp_path / "paquets"
    racine.mkdir()
    for numero, age, source in ((1, 172800, "ign"), (2, 3600, "ign"),
                                (3, 0, "ign"), (4, 172800, "atkis")):
        dossier = racine / f"{numero:032x}"
        dossier.mkdir()
        (dossier / "public.json").write_text(json.dumps({"pret": True, "source": source,
            "zone": zone["zone"], "strict": True}), encoding="utf-8")
        os.utime(dossier, (200000 - age, 200000 - age))
    assert refresh.nettoyer_paquets(tmp_path, [zone], maintenant=200000) == 1
    assert not (racine / f"{1:032x}").exists()
    assert all((racine / f"{n:032x}").exists() for n in (2, 3, 4))
