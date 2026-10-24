"""Validation de la planification Linux, sans lancer de service système."""
import json
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
