"""Essai de la phase 2 (18 octobre 2026) : fabriquer des tuiles BRouter à
partir d'OSM, avec ou sans un chemin de la BD TOPO absent d'OSM, puis
comparer les itinéraires sur trois jeux de tuiles.

    python tools/essai_phase2.py

Résultat de l'essai, à l'est de Garéoult : entre les deux bouts d'un chemin
IGN de 254 m, 1 028 m sur les tuiles standard comme sur nos tuiles OSM seul,
255 m sur nos tuiles OSM + IGN ; témoin de 2,5 km sans chemin IGN : 4 223 m
(brouter.de) contre 4 158 m (nos tuiles, sans pseudo-tags ni relief).

Ce que l'essai a appris sur le créateur de tuiles de BRouter 1.7.10 :
- il est dans brouter-1.7.10-all.jar (btools.mapcreator) mais lit le PBF
  avec les deux jars de lib/ de l'archive, et seulement le PBF ;
- all.brf et softaccess.brf ne sont pas dans l'archive : ils viennent du
  dépôt (misc/profiles2, tag v1.7.10) ;
- -DavoidMapPolling=true, sinon le lecteur attend 10 s par tour que le
  fichier grossisse (6 s au lieu de 4 min ici) ;
- avec -DuseDenseMaps=true, les identifiants ajoutés doivent rester denses
  (juste au-dessus de ceux de l'extrait) : 10**12 a épuisé la mémoire.
"""
import json
import math
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import osmium

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hike2gpx import bdtopo, brouter, franchissements as fr  # noqa: E402
from hike2gpx.__main__ import DOSSIERS  # noqa: E402

DOSSIER = DOSSIERS.dossier_etat()
BASE = DOSSIER / "essai-phase2"
INSTALLATION = brouter.Installation(DOSSIER)
PROFILS = BASE / "profils-creation"
DEPOT_PROFILS = f"https://raw.githubusercontent.com/abrensch/brouter/v{brouter.VERSION}/misc/profiles2/"
BBOX = (43.315, 6.045, 43.335, 6.075)
DEPART_IGN, ARRIVEE_IGN = (43.323424, 6.060909), (43.325603, 6.060044)   # le chemin BD TOPO de l'essai
PAIRES = {"chemin IGN": [DEPART_IGN, ARRIVEE_IGN],
          "témoin 2,5 km": [(43.3175, 6.0480), (43.3325, 6.0720)]}


def profils_creation() -> None:
    PROFILS.mkdir(parents=True, exist_ok=True)
    for nom in ("all.brf", "softaccess.brf"):
        if not (PROFILS / nom).is_file():
            with urllib.request.urlopen(DEPOT_PROFILS + nom, timeout=60) as r:
                (PROFILS / nom).write_bytes(r.read())
    for nom in ("trekking.brf", "lookups.dat"):
        shutil.copy2(INSTALLATION.profils / nom, PROFILS / nom)


def exporter_osm(cible: Path) -> None:
    if cible.exists():
        return
    s, w, n, e = BBOX
    requete = (f'[out:xml][timeout:180];(way["highway"]({s},{w},{n},{e});way["barrier"]({s},{w},{n},{e}););'
               '(._;>;);out body;')
    demande = urllib.request.Request(fr.ENDPOINT, data=urllib.parse.urlencode({"data": requete}).encode(),
                                     headers={"User-Agent": "hike2gpx-essai"})
    with urllib.request.urlopen(demande, timeout=300) as r:
        cible.write_bytes(r.read())


def lire(chemin: Path):
    noeuds, voies = {}, []
    for o in osmium.FileProcessor(str(chemin)):
        if o.is_node():
            noeuds[o.id] = [o.location.lat, o.location.lon, dict(o.tags)]
        elif o.is_way():
            voies.append([o.id, [n.ref for n in o.nodes], dict(o.tags)])
    return noeuds, voies


def raccorder(lat, lon, noeuds, voies, proj, compteur):
    """Nœud commun entre le chemin IGN et la voie OSM la plus proche : un
    sommet existant à moins d'un mètre, sinon un nœud inséré dans la voie."""
    p = proj.xy(lat, lon)
    meilleur = None
    for voie in voies:
        if "highway" not in voie[2]:
            continue
        ids = voie[1]
        for k in range(len(ids) - 1):
            a, b = proj.xy(*noeuds[ids[k]][:2]), proj.xy(*noeuds[ids[k + 1]][:2])
            d = fr._distance_segment(p, a, b)
            if meilleur is None or d < meilleur[0]:
                meilleur = (d, voie, k, a, b)
    d, voie, k, a, b = meilleur
    v = (b[0] - a[0], b[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * v[0] + (p[1] - a[1]) * v[1]) / (v[0] ** 2 + v[1] ** 2 or 1)))
    q = (a[0] + t * v[0], a[1] + t * v[1])
    if math.dist(q, a) < 1:
        return voie[1][k], d
    if math.dist(q, b) < 1:
        return voie[1][k + 1], d
    nid = next(compteur)
    noeuds[nid] = [*proj.geo(*q), {}]
    voie[1].insert(k + 1, nid)
    return nid, d


def ecrire(chemin: Path, noeuds, voies) -> None:
    chemin.unlink(missing_ok=True)
    with osmium.SimpleWriter(str(chemin)) as w:
        for nid in sorted(noeuds):
            lat, lon, tags = noeuds[nid]
            w.add_node(osmium.osm.mutable.Node(id=nid, location=osmium.osm.Location(lon, lat), tags=tags, version=1))
        for wid, ids, tags in sorted(voies, key=lambda v: v[0]):
            w.add_way(osmium.osm.mutable.Way(id=wid, nodes=ids, tags=tags, version=1))


def fabriquer(pbf: Path, dossier: Path) -> Path:
    shutil.rmtree(dossier, ignore_errors=True)
    tmp = dossier / "tmp"
    for d in ("nodetiles", "waytiles", "waytiles55", "nodes55", "unodes55", "segments", "srtm1", "srtm3"):
        (tmp / d).mkdir(parents=True)
    programme = INSTALLATION.programme
    cp = ";".join(str(p) for p in [INSTALLATION.jar, *sorted((programme / "lib").glob("*.jar"))])
    java = [brouter.java(), "-Xmx1g", "-DuseDenseMaps=true", "-DavoidMapPolling=true", "-cp", cp]
    etapes = [
        ["btools.mapcreator.OsmFastCutter", str(PROFILS / "lookups.dat"), "nodetiles", "waytiles", "nodes55",
         "waytiles55", "bordernids.dat", "relations.dat", "restrictions.dat", str(PROFILS / "all.brf"),
         str(PROFILS / "trekking.brf"), str(PROFILS / "softaccess.brf"), str(pbf)],
        ["btools.mapcreator.PosUnifier", "nodes55", "unodes55", "bordernids.dat", "bordernodes.dat", "srtm1", "srtm3"],
        ["btools.mapcreator.WayLinker", "unodes55", "waytiles55", "bordernodes.dat", "restrictions.dat",
         str(PROFILS / "lookups.dat"), str(PROFILS / "all.brf"), "segments", "rd5"],
    ]
    for etape in etapes:
        r = subprocess.run(java + (["-DskipEncodingCheck=true"] if etape[0].endswith("WayLinker") else []) + etape,
                           cwd=tmp, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode:
            raise SystemExit(f"{etape[0]} : code {r.returncode}\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
    return tmp / "segments"


def itineraires(segments: Path) -> dict:
    inst = brouter.Installation(DOSSIER)
    inst.segments = segments
    serveur = brouter.Serveur(inst)
    serveur.demarrer()
    try:
        resultat = {}
        for nom, points in PAIRES.items():
            try:
                resultat[nom] = round(float(brouter.calculer(serveur.port, points)["properties"]["track-length"]))
            except brouter.ErreurBRouter as exc:
                resultat[nom] = str(exc)
        return resultat
    finally:
        serveur.arreter()


def main() -> int:
    profils_creation()
    xml = BASE / "zone.osm"
    exporter_osm(xml)
    noeuds, voies = lire(xml)
    ecrire(BASE / "zone-osm.osm.pbf", noeuds, voies)

    def proche(p, q):
        return abs(p[0] - q[0]) < 1e-6 and abs(p[1] - q[1]) < 1e-6

    troncon = next(t for i, j in fr.tuiles_zone(*DEPART_IGN, *DEPART_IGN)
                   for t in bdtopo.charger_tuile(i, j, DOSSIER)
                   if proche(t["pts"][0], DEPART_IGN) and proche(t["pts"][-1], ARRIVEE_IGN))
    proj = fr.Projection(*DEPART_IGN)
    compteur = iter(range(max(noeuds) + 1, max(noeuds) + 10 ** 6))
    debut, d0 = raccorder(*troncon["pts"][0], noeuds, voies, proj, compteur)
    fin, d1 = raccorder(*troncon["pts"][-1], noeuds, voies, proj, compteur)
    interieur = []
    for lat, lon in troncon["pts"][1:-1]:
        interieur.append(next(compteur))
        noeuds[interieur[-1]] = [lat, lon, {}]
    voies.append([max(v[0] for v in voies) + 1, [debut, *interieur, fin],
                  {"highway": "path", "source": "IGN BD TOPO"}])
    print(f"chemin IGN {troncon['id']} ({troncon['nature']}), raccordé à {d0:.1f} m et {d1:.1f} m du réseau OSM")
    ecrire(BASE / "zone-osm-ign.osm.pbf", noeuds, voies)

    jeux = {"standard (brouter.de)": INSTALLATION.segments,
            "OSM seul (maison)": fabriquer(BASE / "zone-osm.osm.pbf", BASE / "tuiles-osm"),
            "OSM + IGN (maison)": fabriquer(BASE / "zone-osm-ign.osm.pbf", BASE / "tuiles-osm-ign")}
    for nom, segments in jeux.items():
        print(f"{nom:24s}", json.dumps(itineraires(segments), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
