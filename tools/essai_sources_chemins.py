"""Part des chemins officiels absente d'OSM, mesurée avec la règle de fusion de hike2gpx.

Pour chaque massif : on classe la tuile de 0,05° du massif et ses voisines par
longueur de la source officielle, on garde la plus dense, on y lit OSM (marge
d'1 km) et on compte les morceaux couverts à moins de 50 % par OSM à 12 m,
comme fusion.ajouter_ign(). Résultats et analyse : RAPPORT_SOURCES_CHEMINS_BROUTER.md.

    python tools/essai_sources_chemins.py            toutes les zones
    python tools/essai_sources_chemins.py US Var     un pays, ou les zones dont le nom contient « Var »

Les lectures (BD TOPO, USGS, swisstopo, PDOK, Overpass) sont gardées dans le
dossier temporaire du système : une nouvelle mesure ne les redemande pas.
"""
import json
import math
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hike2gpx import __version__, fusion     # noqa: E402
from hike2gpx.providers import bdtopo  # noqa: E402
from hike2gpx import franchissements as fr           # noqa: E402

CACHE = Path(tempfile.gettempdir()) / "hike2gpx-essai-sources"
CACHE.mkdir(exist_ok=True)
UA = {"User-Agent": f"hike2gpx/{__version__} (essai_sources_chemins)"}
MARGE = 0.01
M = fr.M_PAR_DEGRE

ZONES = [
    ("FR", "Vosges, Hohneck", 48.04, 7.02),
    ("FR", "Chartreuse", 45.37, 5.79),
    ("FR", "Ariège, Couserans", 42.87, 1.20),
    ("FR", "Var, massif des Maures", 43.25, 6.35),
    ("FR", "Var, Sainte-Baume", 43.33, 5.75),
    ("FR", "Var, Estérel", 43.47, 6.82),
    ("FR", "Var, gorges du Verdon", 43.74, 6.33),
    ("US", "Great Smoky Mountains", 35.65, -83.50),
    ("US", "Zion", 37.22, -112.97),
    ("US", "White Mountains (NH)", 44.16, -71.36),
    ("US", "Gila National Forest", 33.20, -108.25),
    ("CH", "Zermatt", 46.01, 7.74),
    ("CH", "Emmental, Napf", 47.00, 7.94),
    ("CH", "Jura, Franches-Montagnes", 47.23, 7.02),
    ("CH", "Tessin, Vallemaggia", 46.30, 8.62),
    ("CH", "Grisons, Surselva", 46.77, 9.08),
    ("CH", "Tessin, Val Bavona", 46.38, 8.49),
    ("CH", "Tessin, Val Onsernone", 46.20, 8.58),
    ("CH", "Uri, Schächental", 46.88, 8.76),
    ("NL", "Veluwe", 52.07, 5.85),
    ("DE", "Bavière, Allgäu", 47.55, 10.25),
    ("DE", "Bavière, Berchtesgaden", 47.62, 12.98),
    ("DE", "Bavière, forêt bavaroise", 48.91, 13.31),
    ("DE", "Bavière, forêt franconienne", 50.32, 11.49),
    ("DE-TH", "Rosa, Thuringe", 50.717, 10.250),
    ("CA", "Banff", 51.18, -115.57),
    ("CA", "Yoho", 51.40, -116.50),
    ("NZ", "Tongariro", -39.20, 175.50),
    ("NZ", "Kepler", -45.42, 167.65),
    ("NZ", "Routeburn", -44.72, 168.15),
    ("CZ", "Šumava", 49.06, 13.50),
    ("CZ", "Krkonoše", 50.72, 15.72),
    ("CZ", "České Švýcarsko", 50.87, 14.36),
    ("CZ", "Moravský kras", 49.37, 16.73),
    ("PL-DS", "Karkonosze, versant polonais", 50.80, 15.62),
    ("PL-DS", "Góry Stołowe", 50.45, 16.25),
    ("PL-DS", "Góry Sowie", 50.65, 16.48),
]
VOISINES = {"FR": [(a, b) for a in (-1, 0, 1) for b in (-1, 0, 1)],
            "US": [(a, b) for a in (-1, 0, 1) for b in (-1, 0, 1)],
            "CH": [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)],
            "NL": [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)],
            "DE": [(a, b) for a in (-1, 0, 1) for b in (-1, 0, 1)],
            "DE-TH": [(a, b) for a in (-1, 0, 1) for b in (-1, 0, 1)],
            "CA": [(a, b) for a in (-1, 0, 1) for b in (-1, 0, 1)],
            "NZ": [(a, b) for a in (-1, 0, 1) for b in (-1, 0, 1)],
            "CZ": [(a, b) for a in (-1, 0, 1) for b in (-1, 0, 1)],
            "PL-DS": [(a, b) for a in (-1, 0, 1) for b in (-1, 0, 1)]}
CHEMINS_FR = {"Sentier", "Chemin", "Escalier"}


def lire_json(url, tentatives=4):
    for k in range(tentatives):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return json.load(r)
        except Exception as exc:                                    # noqa: BLE001
            if k == tentatives - 1:
                raise
            print("  nouvel essai :", exc, file=sys.stderr)
            time.sleep(5 * (k + 1))


def en_cache(cle, lire):
    chemin = CACHE / f"{cle}.json"
    if chemin.exists():
        return json.loads(chemin.read_text(encoding="utf-8"))
    valeur = lire()
    chemin.write_text(json.dumps(valeur), encoding="utf-8")
    return valeur


def longueur_km(pts):
    total = 0.0
    for (a1, o1), (a2, o2) in zip(pts, pts[1:]):
        k = math.cos(math.radians((a1 + a2) / 2))
        total += math.hypot((o2 - o1) * k * M, (a2 - a1) * M)
    return total / 1000


def decouper(pts, s, w, n, e):
    """Morceaux de la ligne dont les sommets sont dans le rectangle."""
    morceaux, courant = [], []
    for lat, lon in pts:
        if s <= lat <= n and w <= lon <= e:
            courant.append((lat, lon))
        else:
            if len(courant) >= 2:
                morceaux.append(courant)
            courant = []
    if len(courant) >= 2:
        morceaux.append(courant)
    return morceaux


# ------------------------------------------------------------------ sources : [(pts, classe)]

def source_fr(s, w, n, e, i, j):
    troncons = en_cache(f"fr_{i}_{j}", lambda: bdtopo.lire_tuile(i, j))
    return [(t["pts"], t.get("nature")) for t in troncons
            if t.get("nature") not in fusion.NATURES_EXCLUES and len(t.get("pts") or []) >= 2]


def source_us(s, w, n, e, i, j):
    def lire():
        lignes, decalage = [], 0
        while True:
            q = {"geometry": f"{w},{s},{e},{n}", "geometryType": "esriGeometryEnvelope", "inSR": 4326,
                 "outSR": 4326, "spatialRel": "esriSpatialRelIntersects", "where": "trailtype='Terra Trail'",
                 "outFields": "hikerpedestrian", "returnGeometry": "true", "resultOffset": decalage,
                 "resultRecordCount": 2000, "f": "json"}
            d = lire_json("https://partnerships.nationalmap.gov/arcgis/rest/services/USGSTrails/MapServer/0/query?"
                          + urllib.parse.urlencode(q))
            for f in d.get("features", []):
                for chemin in (f.get("geometry") or {}).get("paths", []):
                    lignes.append([[[p[1], p[0]] for p in chemin], (f.get("attributes") or {}).get("hikerpedestrian")])
            if not d.get("exceededTransferLimit"):
                return lignes
            decalage += 2000
    return [(pts, c) for pts, c in en_cache(f"us_{i}_{j}", lire)]


def source_ch(s, w, n, e, i, j):
    def lire():
        vus, lignes, decalage = set(), [], 0
        while True:
            # Le service choisit les géométries selon l'échelle : sans ces
            # paramètres, certains chemins détaillés manquent au résultat.
            q = {"geometry": f"{w},{s},{e},{n}", "geometryType": "esriGeometryEnvelope", "sr": 4326,
                 "layers": "all:ch.swisstopo.swisstlm3d-strassen", "tolerance": 0, "returnGeometry": "true",
                 "geometryFormat": "geojson", "limit": 200, "offset": decalage,
                 "mapExtent": f"{w},{s},{e},{n}", "imageDisplay": "1024,1024,96"}
            d = lire_json("https://api3.geo.admin.ch/rest/services/api/MapServer/identify?" + urllib.parse.urlencode(q))
            nouveaux = 0
            for f in d.get("results", []):
                if f["id"] in vus:
                    continue
                vus.add(f["id"])
                nouveaux += 1
                classe = (f.get("properties") or f.get("attributes") or {}).get("objektart")
                for ligne in fr_lignes(f.get("geometry")):
                    lignes.append([ligne, classe])
            if not nouveaux:
                return lignes
            decalage += 200
    return [(pts, c) for pts, c in en_cache(f"ch_v2_{i}_{j}", lire)]


def source_nl(s, w, n, e, i, j):
    def lire():
        lignes = []
        url = ("https://api.pdok.nl/brt/top10nl/ogc/v1/collections/wegdeel_hartlijn/items?"
               + urllib.parse.urlencode({"f": "json", "limit": 1000, "bbox": f"{w},{s},{e},{n}"}))
        while url:
            d = lire_json(url)
            for f in d.get("features", []):
                for ligne in fr_lignes(f.get("geometry")):
                    lignes.append([ligne, (f.get("properties") or {}).get("hoofdverkeersgebruik")])
            url = next((l["href"] for l in d.get("links", []) if l.get("rel") == "next"), None)
        return lignes
    return [(pts, c) for pts, c in en_cache(f"nl_{i}_{j}", lire)]


def source_de(s, w, n, e, i, j):
    """Chemins et voies agricoles du Basis-DLM bavarois, par emprise WFS.

    Le BBOX KVP du service échoue sur le préfixe de ``adv:position`` ; un
    filtre FES explicite avec le namespace adv fonctionne. Les coordonnées
    GML demandées en EPSG:4326 sont dans l'ordre latitude, longitude.
    """
    def lire():
        lignes = []
        filtre = ("<fes:Filter xmlns:fes='http://www.opengis.net/fes/2.0' "
                  "xmlns:gml='http://www.opengis.net/gml/3.2' "
                  "xmlns:adv='http://www.adv-online.de/namespaces/adv/gid/7.1'>"
                  "<fes:BBOX><fes:ValueReference>adv:position</fes:ValueReference>"
                  "<gml:Envelope srsName='urn:ogc:def:crs:EPSG::4326'>"
                  f"<gml:lowerCorner>{s} {w}</gml:lowerCorner>"
                  f"<gml:upperCorner>{n} {e}</gml:upperCorner>"
                  "</gml:Envelope></fes:BBOX></fes:Filter>")
        for nom, classe in (("AX_WegPfadSteig", "Weg/Pfad/Steig"),
                            ("AX_Fahrwegachse", "Wirtschaftsweg")):
            for depart in range(0, 20_000, 1000):
                q = {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
                     "TYPENAMES": f"adv:{nom}", "SRSNAME": "EPSG:4326",
                     "FILTER": filtre, "COUNT": 1000, "STARTINDEX": depart}
                url = "https://geoservices.bayern.de/wfs/v1/ogc_atkis_basisdlm.cgi?" + urllib.parse.urlencode(q)
                with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                    racine = ET.fromstring(r.read())
                if racine.tag.endswith("ExceptionReport"):
                    raise RuntimeError("WFS bavarois : " + " ".join(racine.itertext()))
                membres = racine.findall("{http://www.opengis.net/wfs/2.0}member")
                for membre in membres:
                    for pos in membre.findall(".//{http://www.opengis.net/gml/3.2}posList"):
                        valeurs = [float(v) for v in pos.text.split()]
                        pts = [[valeurs[k], valeurs[k + 1]] for k in range(0, len(valeurs), 2)]
                        if len(pts) >= 2:
                            lignes.append([pts, classe])
                if len(membres) < 1000:
                    break
            else:
                raise RuntimeError("WFS bavarois : plus de 20 000 tronçons dans une tuile")
        return lignes
    return [(pts, c) for pts, c in en_cache(f"de_by_{i}_{j}", lire)]


def source_de_th(s, w, n, e, i, j):
    """Weg/Pfad/Steig et Fahrwegachse du Basis-DLM de Thuringe par emprise."""
    def lire():
        lignes = []
        filtre = ("<fes:Filter xmlns:fes='http://www.opengis.net/fes/2.0' "
                  "xmlns:gml='http://www.opengis.net/gml/3.2' "
                  "xmlns:dlm='http://www.adv-online.de/namespaces/adv/gid/7.1/dlm'>"
                  "<fes:BBOX><fes:ValueReference>dlm:geom</fes:ValueReference>"
                  "<gml:Envelope srsName='EPSG:4326'>"
                  f"<gml:lowerCorner>{w} {s}</gml:lowerCorner>"
                  f"<gml:upperCorner>{e} {n}</gml:upperCorner>"
                  "</gml:Envelope></fes:BBOX></fes:Filter>")
        for nom, classe in (("AX_WEGPFADSTEIG", "Weg/Pfad/Steig"),
                            ("AX_FAHRWEGACHSE", "Wirtschaftsweg")):
            for depart in range(0, 20_000, 1000):
                q = {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
                     "TYPENAMES": f"dlm:{nom}", "SRSNAME": "EPSG:4326",
                     "FILTER": filtre, "COUNT": 1000, "STARTINDEX": depart}
                url = "https://www.geoproxy.geoportal-th.de/geoproxy/services/adv_atkis_wfs?" + urllib.parse.urlencode(q)
                with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                    racine = ET.fromstring(r.read())
                if racine.tag.endswith("ExceptionReport"):
                    raise RuntimeError("WFS de Thuringe : " + " ".join(racine.itertext()))
                membres = racine.findall("{http://www.opengis.net/wfs/2.0}member")
                for membre in membres:
                    for pos in membre.findall(".//{http://www.opengis.net/gml/3.2}posList"):
                        valeurs = [float(v) for v in pos.text.split()]
                        pts = [[valeurs[k + 1], valeurs[k]] for k in range(0, len(valeurs), 2)]
                        if len(pts) >= 2:
                            lignes.append([pts, classe])
                if len(membres) < 1000:
                    break
            else:
                raise RuntimeError("WFS de Thuringe : plus de 20 000 tronçons dans une tuile")
        return lignes
    return [(pts, c) for pts, c in en_cache(f"de_th_{i}_{j}", lire)]


def _arcgis_trails(url, s, w, n, e, *, geojson, condition="1=1"):
    """Tronçons d'un service ArcGIS officiel, paginés et bornés par emprise."""
    lignes = []
    for depart in range(0, 100_000, 2000):
        q = {"where": condition, "geometry": f"{w},{s},{e},{n}",
             "geometryType": "esriGeometryEnvelope", "inSR": 4326,
             "spatialRel": "esriSpatialRelIntersects", "outSR": 4326,
             "outFields": "*", "f": "geojson" if geojson else "json",
             "resultRecordCount": 2000, "resultOffset": depart}
        donnees = lire_json(url + "/query?" + urllib.parse.urlencode(q))
        if "error" in donnees:
            raise RuntimeError(f"ArcGIS : {donnees['error']}")
        objets = donnees.get("features", [])
        for objet in objets:
            if geojson:
                geom = objet.get("geometry") or {}
                lignes_geo = ([geom.get("coordinates", [])] if geom.get("type") == "LineString"
                              else geom.get("coordinates", []) if geom.get("type") == "MultiLineString" else [])
                classe = objet.get("properties", {}).get("General_Activity", "sentier")
            else:
                lignes_geo = (objet.get("geometry") or {}).get("paths", [])
                classe = objet.get("attributes", {}).get("difficulty", "sentier")
            for points in lignes_geo:
                if len(points) >= 2:
                    lignes.append(([[lat, lon] for lon, lat in points], classe))
        if len(objets) < 2000:
            return lignes
    raise RuntimeError("ArcGIS : plus de 100 000 objets dans cette tuile")


def source_ca(s, w, n, e, i, j):
    """Sentiers officiels ouverts en été de Parcs Canada."""
    url = ("https://services2.arcgis.com/wCOMu5IS7YdSyPNx/arcgis/rest/services/"
           "vw_Trails_Sentiers_APCA_V2_FGP/FeatureServer/0")
    return [(pts, c) for pts, c in en_cache(f"ca_{i}_{j}",
        lambda: _arcgis_trails(url, s, w, n, e, geojson=True,
                               condition="Official_Officiel=1 AND Restr_Sum_Ete_Interd=0"))]


def source_nz(s, w, n, e, i, j):
    """Itinéraires de marche entretenus par le DOC néo-zélandais."""
    url = ("https://services1.arcgis.com/3JjYDyG3oajxU6HO/ArcGIS/rest/services/"
           "DOC_Walking_Experiences/FeatureServer/1")
    return [(pts, c) for pts, c in en_cache(f"nz_{i}_{j}",
        lambda: _arcgis_trails(url, s, w, n, e, geojson=False))]


def source_cz(s, w, n, e, i, j):
    """Sentiers et chemins ZABAGED du service national tchèque."""
    racine = "https://ags.cuzk.gov.cz/arcgis/rest/services/ZABAGED_POLOHOPIS/MapServer"
    def lire():
        lignes = []
        for couche, classe in ((82, "Pěšina"), (83, "Cesta")):
            lignes.extend((pts, classe) for pts, _ in _arcgis_trails(
                f"{racine}/{couche}", s, w, n, e, geojson=False))
        return lignes
    return [(pts, c) for pts, c in en_cache(f"cz_{i}_{j}", lire)]


def source_pl_ds(s, w, n, e, i, j):
    """Voies piétonnes et cyclables BDOT10k de Basse-Silésie."""
    url = "https://geoportal.dolnyslask.pl/gisserver1/rest/services/BDOT10k/FeatureServer/18"
    return [(pts, "SKRP") for pts, _ in en_cache(f"pl_ds_{i}_{j}",
        lambda: _arcgis_trails(url, s, w, n, e, geojson=False))]


def fr_lignes(geometrie):
    return bdtopo._lignes(geometrie)


SOURCES = {"FR": source_fr, "US": source_us, "CH": source_ch, "NL": source_nl,
           "DE": source_de, "DE-TH": source_de_th,
           "CA": source_ca, "NZ": source_nz, "CZ": source_cz,
           "PL-DS": source_pl_ds}


# ------------------------------------------------------------------ mesure

def decoupees(lignes, s, w, n, e):
    return [(m, c) for pts, c in lignes for m in decouper(pts, s, w, n, e)]


def mesurer(pays, nom, lat, lon):
    i0, j0 = fr.tuile_du_point(lat, lon)
    classement = []
    for di, dj in VOISINES[pays]:
        i, j = i0 + di, j0 + dj
        s, w, n, e = fr.bornes_tuile(i, j)
        lignes = decoupees(SOURCES[pays](s, w, n, e, i, j), s, w, n, e)
        # En France, la densité se juge sur les seuls chemins : classée sur
        # toute la BD TOPO, une ville l'emporte sur un massif (essai de
        # l'Estérel, 2026-10-23 : Fréjus retenu à la place du massif).
        classement.append((sum(longueur_km(m) for m, c in lignes if pays != "FR" or c in CHEMINS_FR), i, j))
    classement.sort(reverse=True)
    _, i, j = classement[0]
    s, w, n, e = fr.bornes_tuile(i, j)
    lignes = decoupees(SOURCES[pays](s, w, n, e, i, j), s, w, n, e)
    km_source = sum(longueur_km(m) for m, _ in lignes)

    elements = en_cache(f"osm_{i}_{j}", lambda: fr.interroger(fr.requete(s - MARGE, w - MARGE, n + MARGE, e + MARGE)))
    reseau = fusion.Reseau()
    reseau.ajouter_osm(elements)
    km_osm = sum(longueur_km(m) for ids, tags in reseau.voies.values() if fr._praticable(tags)
                 for m in decouper([tuple(reseau.noeuds[x][:2]) for x in ids], s, w, n, e))
    parts = fusion.parts_couvertes([m for m, _ in lignes], reseau.segments_osm())
    nouveaux = [(m, c) for (m, c), p in zip(lignes, parts) if p < fusion.PART_COUVERTE_MAX]
    km_nouveaux = sum(longueur_km(m) for m, _ in nouveaux)
    par_classe = {}
    for m, c in nouveaux:
        par_classe[str(c)] = par_classe.get(str(c), 0.0) + longueur_km(m)
    resultat = {"pays": pays, "zone": nom, "tuile": [i, j], "centre": [round((s + n) / 2, 3), round((w + e) / 2, 3)],
                "densites_voisines_km": [round(k, 1) for k, _, _ in classement],
                "km_source": round(km_source, 1), "km_osm": round(km_osm, 1), "km_nouveaux": round(km_nouveaux, 1),
                "part_source_absente_osm": round(km_nouveaux / km_source, 3) if km_source else None,
                "gain_reseau": round(km_nouveaux / km_osm, 3) if km_osm else None,
                "nouveaux_par_classe_km": {k: round(v, 1) for k, v in sorted(par_classe.items(), key=lambda x: -x[1])[:6]}}
    if pays == "FR":
        km_chemins = sum(longueur_km(m) for m, c in lignes if c in CHEMINS_FR)
        resultat["km_source_sentiers_chemins"] = round(km_chemins, 1)
        resultat["km_nouveaux_sentiers_chemins"] = round(sum(longueur_km(m) for m, c in nouveaux if c in CHEMINS_FR), 1)
    return resultat


if __name__ == "__main__":
    choix = sys.argv[1:] or None
    resultats = []
    for pays, nom, lat, lon in ZONES:
        if choix and pays not in choix and not any(c in nom for c in choix):
            continue
        debut = time.monotonic()
        try:
            r = mesurer(pays, nom, lat, lon)
        except Exception as exc:                                    # noqa: BLE001
            r = {"pays": pays, "zone": nom, "erreur": repr(exc)}
        r["duree_s"] = round(time.monotonic() - debut)
        resultats.append(r)
        print(json.dumps(r, ensure_ascii=True), flush=True)
    (CACHE / f"resultats_{'_'.join(choix or ['tous'])}.json").write_text(
        json.dumps(resultats, ensure_ascii=False, indent=1), encoding="utf-8")
