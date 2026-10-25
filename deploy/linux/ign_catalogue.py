#!/usr/bin/env python3
"""Liste les archives BD TOPO GeoPackage récentes, région par région."""
from __future__ import annotations

import argparse
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

API = "https://data.geopf.fr/telechargement/resource/BDTOPO"
ATOM = "{http://www.w3.org/2005/Atom}"
GPF = "{https://data.geopf.fr/annexes/ressources/xsd/gpf_dl.xsd}"
REGIONS = ("R11", "R24", "R27", "R28", "R32", "R44", "R52", "R53", "R75", "R76", "R84", "R93", "R94")


def lire(url: str) -> ET.Element:
    demande = urllib.request.Request(url, headers={"User-Agent": "hike2gpx/0.3.2"})
    with urllib.request.urlopen(demande, timeout=30) as reponse:
        return ET.fromstring(reponse.read())


def derniere_edition(zone: str, charger=lire) -> dict:
    if zone not in REGIONS:
        raise ValueError(f"Région IGN inconnue : {zone}")
    url = API + "?" + urllib.parse.urlencode({"lang": "fre", "zone": zone, "format": "GPKG",
                                              "limit": 50, "sortEntriesBy": "editionDate",
                                              "sortEntriesOrder": "desc"})
    dossiers = charger(url).findall(ATOM + "entry")
    editions = []
    for entree in dossiers:
        titre = entree.findtext(ATOM + "title", "")
        if re.fullmatch(rf"BDTOPO_[\d-]+_TOUSTHEMES_GPKG_LAMB93_{zone}_\d{{4}}-\d{{2}}-\d{{2}}", titre):
            editions.append(titre)
    if not editions:
        raise ValueError(f"Aucune édition BD TOPO GeoPackage trouvée pour {zone}")
    nom = max(editions, key=lambda titre: titre[-10:])
    fichiers = []
    for entree in charger(f"{API}/{nom}?limit=50").findall(ATOM + "entry"):
        lien = next((l for l in entree.findall(ATOM + "link")
                     if l.get("rel") in ("section", "alternate")), None)
        if lien is None:
            continue
        adresse = lien.get("href", "")
        if not adresse.startswith(f"https://data.geopf.fr/telechargement/download/BDTOPO/{nom}/") \
                or not re.fullmatch(re.escape(nom) + r"\.7z(?:\.\d{3})?", adresse.rsplit("/", 1)[-1]):
            continue
        taille = int(lien.get(GPF + "length", "0"))
        md5 = (entree.findtext(ATOM + "content") or "").strip().lower()
        if taille <= 0 or not re.fullmatch(r"[0-9a-f]{32}", md5):
            raise ValueError(f"Taille ou MD5 invalide pour {adresse}")
        fichiers.append({"url": adresse, "octets": taille, "md5": md5})
    if not fichiers:
        raise ValueError(f"Aucune archive BD TOPO trouvée pour {nom}")
    fichiers.sort(key=lambda fichier: fichier["url"])
    return {"zone": zone, "edition": nom, "fichiers": fichiers,
            "octets": sum(fichier["octets"] for fichier in fichiers)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zone", choices=REGIONS)
    args = parser.parse_args(argv)
    total = 0
    for zone in (args.zone,) if args.zone else REGIONS:
        paquet = derniere_edition(zone)
        total += paquet["octets"]
        print(f"{zone} : {paquet['edition']} — {paquet['octets'] / 1024**3:.2f} Gio, "
              f"{len(paquet['fichiers'])} archive(s)", flush=True)
    if not args.zone:
        print(f"Total des archives régionales : {total / 1024**3:.2f} Gio", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
