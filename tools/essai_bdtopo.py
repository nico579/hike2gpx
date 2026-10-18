"""Natures des couches linéaires de la BD TOPO de l'IGN sur une zone, par son
service WFS public : la BD TOPO connaît-elle les clôtures ?

    python tools/essai_bdtopo.py 43.30 6.00 43.35 6.05
"""
import argparse
import collections
import json
import sys
import urllib.parse
import urllib.request

COUCHES = ("BDTOPO_V3:construction_lineaire", "BDTOPO_V3:haie")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for nom in ("sud", "ouest", "nord", "est"):
        parser.add_argument(nom, type=float)
    parser.add_argument("--couche", action="append", help="couche WFS (par défaut : " + ", ".join(COUCHES) + ")")
    a = parser.parse_args()
    for couche in a.couche or COUCHES:
        parametres = {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": couche,
                      "BBOX": f"{a.sud},{a.ouest},{a.nord},{a.est},urn:ogc:def:crs:EPSG::4326",
                      "OUTPUTFORMAT": "application/json", "COUNT": "10000"}
        demande = urllib.request.Request("https://data.geopf.fr/wfs/ows?" + urllib.parse.urlencode(parametres),
                                         headers={"User-Agent": "hike2gpx-essai"})
        with urllib.request.urlopen(demande, timeout=120) as reponse:
            entites = json.load(reponse).get("features", [])
        natures = collections.Counter(str(f["properties"].get("nature")) for f in entites)
        print(f"{couche} : {len(entites)} entités ;", ", ".join(f"{n} {nature}" for nature, n in natures.most_common()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
