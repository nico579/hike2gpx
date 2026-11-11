"""Le compte rendu d'une fabrication des lots : états par case, cause des échecs, publication, fraîcheur."""
import calendar
import time

from hike2gpx import rapport


def _instant(texte):
    return calendar.timegm(time.strptime(texte, "%Y-%m-%dT%H:%M:%SZ"))


def _job(nom, conclusion="success", etape_fautive=None, debut="2026-11-11T15:22:00Z", fin="2026-11-11T16:00:00Z"):
    etapes = [{"name": "Set up job", "conclusion": "success"}]
    if etape_fautive:
        etapes.append({"name": etape_fautive, "conclusion": "failure"})
    return {"name": f"bundles / {nom}", "conclusion": conclusion, "started_at": debut, "completed_at": fin,
            "html_url": f"https://exemple/{nom.replace(' ', '_')}", "steps": etapes}


def _run_complet(case):
    return ([_job(f"données {case}"), _job(f"case {case}")]
            + [_job(f"calques {case} {i}/4") for i in range(1, 5)] + [_job(f"fin {case}")])


def test_une_case_reussie_est_publiee_et_dite_ok_a_chaque_etape():
    jobs = _run_complet("W5_N40") + [_job("publier")]
    contenu = {"lots": [{"case": "W5_N40", "octets": 266e6, "sources": {"osm": "2026-11-10T21:00:00Z"}}]}
    texte = rapport.compte_rendu(jobs, contenu, ["W5_N40"], run="https://run", ref="main", version="0.9.15",
                                 maintenant=_instant("2026-11-11T17:00:00Z"))
    assert "| W5_N40 | ok | ok | ok | ok | oui, ce run | 266 Mo |" in texte
    assert "- Publication : faite" in texte and "## Échecs\n\nAucun." in texte
    assert "hike2gpx : 0.9.15 (ref `main`)" in texte and "Durée : 2026-11-11 15:22 UTC" in texte


def test_seule_la_cause_d_un_echec_est_retenue_pas_la_cascade():
    # Les données échouent : le calcul, les calques et l'assemblage échouent à leur
    # tour faute d'entrée, mais ce ne sont pas des causes.
    jobs = ([_job("données E10_N45", "failure", "Télécharger les données de la case"),
             _job("case E10_N45", "failure", "Reprendre le calcul")]
            + [_job(f"calques E10_N45 {i}/4", "failure", "Reprendre le calcul") for i in range(1, 5)]
            + [_job("fin E10_N45", "failure", "Reprendre le calcul"), _job("publier")])
    texte = rapport.compte_rendu(jobs, {"lots": []}, ["E10_N45"], run="", ref="main", version="x",
                                 maintenant=_instant("2026-11-11T17:00:00Z"))
    assert "| E10_N45 | échec | non faite | non faite | non faite | non |  |" in texte
    echecs = texte.split("## Échecs")[1].split("##")[0]
    assert echecs.count("- E10_N45") == 1
    assert "données : échec à l'étape « Télécharger les données de la case »" in echecs
    # La case absente du catalogue est signalée par le contrôle de fraîcheur.
    assert "E10_N45 : absent du catalogue" in texte


def test_un_echec_aux_calques_nomme_ses_parts_et_garde_l_ancien_lot():
    jobs = ([_job("données E10_N50"), _job("case E10_N50"), _job("calques E10_N50 1/4"),
             _job("calques E10_N50 3/4", "failure", "Calques, part 3/4"),
             _job("calques E10_N50 2/4", "failure", "Calques, part 2/4"), _job("calques E10_N50 4/4"),
             _job("fin E10_N50", "failure", "Assembler le lot"), _job("publier")])
    contenu = {"lots": [{"case": "E10_N50", "octets": 400e6, "sources": {"osm": "2026-11-09T21:00:00Z"}}]}
    texte = rapport.compte_rendu(jobs, contenu, ["E10_N50"], run="", ref="main", version="x",
                                 maintenant=_instant("2026-11-11T17:00:00Z"))
    assert "| E10_N50 | ok | ok | échec | non faite | ancien lot | 400 Mo |" in texte
    echecs = texte.split("## Échecs")[1].split("##")[0]
    assert "calques (2/4)" in echecs and "calques (3/4)" in echecs and "assemblage" not in echecs
    assert echecs.index("(2/4)") < echecs.index("(3/4)"), "les parts dans l'ordre"


def test_sans_publication_rien_n_est_dit_publie_ce_run():
    jobs = _run_complet("E0_N40") + [_job("publier", "failure", "Catalogue et publication")]
    texte = rapport.compte_rendu(jobs, {"lots": []}, ["E0_N40"], run="", ref="main", version="x",
                                 maintenant=_instant("2026-11-11T17:00:00Z"))
    assert "- Publication : non faite" in texte
    assert "| E0_N40 | ok | ok | ok | ok | non |  |" in texte


def test_les_jobs_hors_cases_sont_ignores():
    etats = rapport.etats([_job("liste"), _job("bdtopo"), _job("données E0_N45"), _job("calques E0_N45 2/4")])
    assert list(etats) == ["E0_N45"] and sorted(etats["E0_N45"]) == ["calques", "données"]
