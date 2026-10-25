#!/usr/bin/env python3
"""Essai réel du téléchargement RD5q, assemblage et routage local BRouter."""
from __future__ import annotations

import argparse
import hashlib
import tempfile
import time
from pathlib import Path

from hike2gpx.application import Application, zone_autour
from hike2gpx.cloud import Client
from nico579_commons import atomique


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("serveur", help="Adresse HTTP locale ou HTTPS du serveur de données")
    parser.add_argument("installation", type=Path, help="Dossier contenant BRouter 1.7.10")
    parser.add_argument("rd5_reference", type=Path)
    args = parser.parse_args()
    points = [[43.300367, 6.249497], [43.300835, 6.250661]]
    zone = zone_autour(points)
    with tempfile.TemporaryDirectory(prefix="hike2gpx-rd5q-") as tmp:
        dossier = Path(tmp)
        prefs = dossier / "preferences.json"
        atomique.ecrire_json(prefs, {"serveur_url": args.serveur})
        paquet, local = Client(prefs).paquet(
            {"source": "ign", "officiel": True, "strict": True}, dossier, zone)
        assert paquet["format"] == 2 and len(paquet["segments"]) == 2
        rd5 = local / paquet["assemblage"]["rd5"]
        assert hashlib.sha256(rd5.read_bytes()).digest() == hashlib.sha256(
            args.rd5_reference.read_bytes()).digest()
        application = Application(args.installation)
        resultat = application._itineraire_paquet(points, zone, paquet, local, time.monotonic())
        assert "erreur" not in resultat, resultat
        print(f"RD5q OK : {len(paquet['segments'])} fragments, {rd5.stat().st_size} octets assemblés, "
              f"itinéraire local de {resultat['longueur_m']:.0f} m")


if __name__ == "__main__":
    main()
