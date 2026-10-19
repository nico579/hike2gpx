import hashlib
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from hike2gpx import brouter

REFERENCE = Path(__file__).with_name("donnees") / "hiking-mountain-1.7.10.brf"


def test_profil_derive_de_hiking_mountain_par_ses_seuls_remplacements():
    source = REFERENCE.read_text(encoding="utf-8")
    profil = brouter.profil_hike2gpx(source)
    for avant, apres in brouter.REMPLACEMENTS:
        assert avant not in profil and profil.count(apres) == 1
    # Rien d'autre ne change : seules les lignes remplacées et l'en-tête diffèrent.
    differences = set(profil.splitlines()) ^ set(source.splitlines())
    assert {l for l in differences if not l.startswith("#")} == \
        {l for paire in brouter.REMPLACEMENTS for texte in paire for l in texte.splitlines()}


def test_profil_interdiction_pietonne_explicite_avant_les_permissions_deduites():
    # Audit B09 : trottoir, vélo poussé ou vélo admis ne lèvent plus foot=no|private.
    profil = brouter.profil_hike2gpx(REFERENCE.read_text(encoding="utf-8"))
    bloc = profil[profil.index("assign footaccess"):profil.index("assign accesspenalty")].split()
    assert bloc[:5] == ["assign", "footaccess", "and", "not", "foot=private|no"]


def test_profil_inattendu_refuse():
    with pytest.raises(ValueError):
        brouter.profil_hike2gpx("assign dummy 0\n")


@pytest.mark.parametrize("lat, lon, nom", [(43.3, 6.04, "E5_N40"), (45.0, 5.0, "E5_N45"),
                                           (48.8, 2.3, "E0_N45"), (43.6, -1.4, "W5_N40")])
def test_nom_segment(lat, lon, nom):
    assert brouter.nom_segment(lat, lon) == nom


def test_segments_zone():
    assert brouter.segments_zone(43.2, 5.9, 43.4, 6.1) == ["E5_N40"]
    assert brouter.segments_zone(44.9, 4.9, 45.1, 5.1) == ["E0_N40", "E5_N40", "E0_N45", "E5_N45"]


def test_requete_coupes_interdites_et_ponderees():
    franchissements = [
        {"statut": "blocked", "coupes": [[[6.1, 43.1], [6.2, 43.2]]]},
        {"statut": "uncertain", "coupes": [[[6.3, 43.3], [6.4, 43.4]], [[6.5, 43.5], [6.6, 43.6]]]},
    ]
    q = parse_qs(urlparse(brouter.requete([(43.0, 6.0), (43.5, 6.5)], franchissements)).query)
    assert q["lonlats"] == ["6.000000,43.000000|6.500000,43.500000"]
    assert q["profile"] == ["hike2gpx"] and q["format"] == ["geojson"]
    coupes = q["polylines"][0].split("|")
    # Audit B10 : BRouter garde le coût de la dernière coupe qu'un segment
    # croise ; les coupes interdites passent donc après les pondérées.
    assert coupes[-1] == "6.1000000,43.1000000,6.2000000,43.2000000"
    assert all(c.endswith(f",{brouter.POIDS_A_VERIFIER}") for c in coupes[:2]) and len(coupes) == 3
    strict = parse_qs(urlparse(brouter.requete([(43.0, 6.0), (43.5, 6.5)], franchissements, strict=True)).query)
    assert all(c.count(",") == 3 for c in strict["polylines"][0].split("|"))


def test_requete_sans_franchissement_sans_polylines():
    assert "polylines" not in brouter.requete([(43.0, 6.0), (43.5, 6.5)])


def test_lookups_ign_ajoute_la_cle_au_contexte_des_voies():
    source = "---lookupversion:10\n---context:way\nhighway;0000000001 path\n\n---context:node\nbarrier;0000000001 gate\n"
    voies, noeuds = brouter.lookups_ign(source).split("---context:node")
    assert voies.endswith("highway;0000000001 path\n\nhike2gpx;0000000001 ign\n\n") and "hike2gpx" not in noeuds
    with pytest.raises(ValueError):
        brouter.lookups_ign(brouter.lookups_ign(source))       # jamais deux fois


def test_profil_maison_rend_les_chemins_ign_plus_couteux():
    profil = brouter.profil_maison(brouter.profil_hike2gpx(REFERENCE.read_text(encoding="utf-8")))
    assert f"assign ign_penalty switch hike2gpx=ign {brouter.PENALITE_IGN} 0" in profil
    assert "assign costfactor\nadd ign_penalty\nadd town_penalty" in profil
    with pytest.raises(ValueError):
        brouter.profil_maison("assign dummy 0\n")


def test_archive_reprise_si_intacte(tmp_path, monkeypatch):
    inst = brouter.Installation(tmp_path)
    inst.racine.mkdir(parents=True)
    archive = inst.racine / f"brouter-{brouter.VERSION}.zip"
    archive.write_bytes(b"archive")
    monkeypatch.setattr(brouter, "ARCHIVE_SHA256", hashlib.sha256(b"archive").hexdigest())
    monkeypatch.setattr(brouter, "_telecharger", lambda *a: pytest.fail("archive téléchargée à nouveau"))
    assert inst._archive() == archive
    archive.write_bytes(b"abimee")
    telechargees = []
    monkeypatch.setattr(brouter, "_telecharger", lambda url, cible, empreinte: telechargees.append(cible) or cible)
    inst._archive()
    assert telechargees == [archive]


def test_programme_fige_n_emploie_que_son_java(monkeypatch, tmp_path):
    # Figé, hike2gpx prend le JRE embarqué (_internal/jre), jamais le Java du
    # système, même présent : c'est la version éprouvée avec le programme.
    monkeypatch.setattr(brouter.sys, "frozen", True, raising=False)
    monkeypatch.setattr(brouter.sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(brouter.shutil, "which", lambda nom: pytest.fail("Java du système consulté"))
    with pytest.raises(brouter.ErreurBRouter, match="réinstallez"):
        brouter.java()
    java = tmp_path / "jre" / "bin" / ("java.exe" if brouter.os.name == "nt" else "java")
    java.parent.mkdir(parents=True)
    java.write_bytes(b"")
    assert brouter.java() == str(java)
