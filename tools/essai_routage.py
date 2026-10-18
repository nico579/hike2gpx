"""Pour chaque franchissement d'une zone, deux points à 60 m de part et
d'autre le long de son chemin, puis le calcul de la page : itinéraire
hike2gpx et tracé standard (profil Randonnée de BRouter, sans les coupes).
Un tracé « traverse » quand il coupe l'une des coupes du franchissement.

    python tools/essai_routage.py 43.25 5.95 43.3999 6.0999 --statuts blocked

Il faut BRouter et la tuile de la zone dans HIKE2GPX_HOME (hike2gpx installer E5_N40).
"""
import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hike2gpx import franchissements as fr  # noqa: E402
from hike2gpx.__main__ import DOSSIERS  # noqa: E402
from hike2gpx.application import Application, sur_le_trace  # noqa: E402

ECART_M = 60.0


def le_long(voie, lat, lon, ecart):
    """Points à ±ecart mètres de (lat, lon) en suivant la voie, et la plus
    petite des deux longueurs disponibles de part et d'autre."""
    proj = fr.Projection(lat, lon)
    pts = [proj.xy(p["lat"], p["lon"]) for p in voie["geometry"]]
    cumul = [0.0]
    for a, b in zip(pts, pts[1:]):
        cumul.append(cumul[-1] + math.dist(a, b))
    k = min(range(len(pts) - 1), key=lambda m: fr._distance_segment((0, 0), pts[m], pts[m + 1]))
    s0 = cumul[k] + math.dist(pts[k], (0, 0))

    def point(s):
        s = max(0.0, min(cumul[-1], s))
        m = next(m for m in range(len(pts) - 1) if cumul[m] <= s <= cumul[m + 1])
        f = 0.0 if cumul[m + 1] == cumul[m] else (s - cumul[m]) / (cumul[m + 1] - cumul[m])
        return proj.geo(pts[m][0] + f * (pts[m + 1][0] - pts[m][0]), pts[m][1] + f * (pts[m + 1][1] - pts[m][1]))

    return point(s0 - ecart), point(s0 + ecart), min(s0, cumul[-1] - s0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for nom in ("sud", "ouest", "nord", "est"):
        parser.add_argument(nom, type=float)
    parser.add_argument("--statuts", default="blocked", help="blocked, uncertain ou les deux séparés par une virgule")
    parser.add_argument("--maximum", type=int, default=40)
    a = parser.parse_args()
    dossier = DOSSIERS.dossier_etat()
    statuts = set(a.statuts.split(","))
    elements = {}
    for i, j in fr.tuiles_zone(a.sud, a.ouest, a.nord, a.est):
        for e in fr.charger_tuile(i, j, dossier)["elements"]:
            elements[e["type"], e["id"]] = e
    liste = fr.franchissements_zone(a.sud, a.ouest, a.nord, a.est, dossier)
    print(f"{len(liste)} franchissements, dont {sum(f['statut'] == 'blocked' for f in liste)} bloquants")
    application = Application(dossier)
    bilan = {"cas": 0, "standard_traverse": 0, "hike2gpx_traverse": 0, "sans_itineraire": 0}
    try:
        for f in liste:
            voie = elements.get(("way", f["voies"][0]))
            if f["statut"] not in statuts or voie is None or bilan["cas"] >= a.maximum:
                continue
            depart, arrivee, marge = le_long(voie, f["lat"], f["lon"], ECART_M)
            if marge < 5:
                continue        # franchissement au bout de son chemin : pas de part et d'autre
            bilan["cas"] += 1
            ligne = f"{f['statut']:9s} {f['nature']:18s} {f['osm']:16s} {f['lat']:.6f},{f['lon']:.6f}"
            r = application.itineraire({"points": [list(depart), list(arrivee)], "comparer": True})
            if "erreur" in r:
                bilan["sans_itineraire"] += 1
                print(f"{ligne} | hike2gpx : {r['erreur']}")
                continue
            naif = r.get("naif")
            traverse_naif = bool(naif and sur_le_trace(naif["geometry"]["coordinates"], [f]))
            traverse = bool(sur_le_trace(r["itineraire"]["geometry"]["coordinates"], [f]))
            bilan["standard_traverse"] += traverse_naif
            bilan["hike2gpx_traverse"] += traverse
            print(f"{ligne} | standard {r.get('naif_longueur_m') or 0:6.0f} m, traverse={traverse_naif}"
                  f" | hike2gpx {r['longueur_m']:6.0f} m, traverse={traverse}, {r['duree_s']} s")
    finally:
        application.arreter()
    print("bilan :", bilan)
    return 0


if __name__ == "__main__":
    sys.exit(main())
