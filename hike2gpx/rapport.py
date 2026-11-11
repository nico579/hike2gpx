"""Le compte rendu d'une fabrication des lots par le serveur (workflow bundles).

Écrit à la fin de chaque run, réussi ou non, et gardé dans le dépôt des lots
(rapports/AAAA-MM-JJTHHMMZ-runN.md) : l'historique des fabrications se lit sur
GitHub, sans dépendre des journaux des runs, effacés au bout de 90 jours.

Il part de la liste des jobs du run (API GitHub, actions/runs/N/jobs) et du
catalogue publié : pour chaque case, l'état de ses quatre étapes, l'étape
fautive d'un échec, ce qui a été publié, et l'âge des lots (depot.fraicheur).
"""
from __future__ import annotations

import re
import time

from . import depot

# Les jobs du workflow, vus du dépôt appelant : « bundles / données E0_N45 »,
# « bundles / calques E0_N45 2/4 », « bundles / fin E0_N45 ».
_JOB = re.compile(r"(?:.* / )?(données|case|calques|fin) ([EW]\d{1,3}_[NS]\d{1,2})(?: (\d+)/(\d+))?$")
ETAPES = (("données", "Données"), ("case", "Calcul"), ("calques", "Calques"), ("fin", "Assemblage"))
_VERDICTS = {"success": "ok", "failure": "échec", "cancelled": "annulé", "skipped": "sauté",
             "timed_out": "trop long"}


def _instant(texte: str | None) -> float | None:
    if not texte:
        return None
    try:
        import calendar
        return calendar.timegm(time.strptime(texte, "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return None


def _verdict(jobs: list) -> str:
    """L'état d'une étape d'une case, ses parts réunies (les 4 calques) : un
    échec l'emporte, puis une annulation ; ok seulement si toutes ont réussi."""
    if not jobs:
        return ""
    conclusions = [j.get("conclusion") for j in jobs]
    for grave in ("failure", "timed_out", "cancelled"):
        if grave in conclusions:
            return _VERDICTS[grave]
    if all(c == "success" for c in conclusions):
        return "ok"
    if all(c == "skipped" for c in conclusions):
        return "sauté"
    return "en cours"


def _etape_fautive(job: dict) -> str:
    for etape in job.get("steps") or []:
        if etape.get("conclusion") == "failure":
            return etape.get("name", "")
    return ""


def etats(jobs: list) -> dict:
    """Les jobs du run rangés par case puis par étape : {case: {étape: [jobs]}}."""
    par_case: dict = {}
    for job in jobs:
        trouve = _JOB.match(job.get("name", ""))
        if trouve:
            etape, case = trouve.group(1), trouve.group(2)
            par_case.setdefault(case, {}).setdefault(etape, []).append(job)
    return par_case


def compte_rendu(jobs: list, contenu: dict, cases: list, *, run: str, ref: str, version: str,
                 maintenant: float, jours_max: int = 14) -> str:
    """Le compte rendu en Markdown. contenu : le catalogue publié après le run
    (vide si la publication a échoué) ; cases : celles demandées au run."""
    debuts = [t for t in (_instant(j.get("started_at")) for j in jobs) if t]
    fins = [t for t in (_instant(j.get("completed_at")) for j in jobs) if t]
    debut = min(debuts) if debuts else maintenant
    fin = max(fins) if fins else maintenant
    par_case = etats(jobs)
    publier = [j for j in jobs if j.get("name", "").endswith("publier")]
    publie = bool(publier) and publier[0].get("conclusion") == "success"
    catalogue = {l["case"]: l for l in contenu.get("lots", [])}

    def heure(t: float) -> str:
        return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(t))

    sortie = [f"# Fabrication des lots du {heure(debut)}", "",
              f"- Run : {run}",
              f"- hike2gpx : {version} (ref `{ref}`)",
              f"- Durée : {heure(debut)} → {heure(fin)}, {(fin - debut) / 60:.0f} min",
              f"- Cases demandées ({len(cases)}) : {' '.join(cases) or 'aucune'}",
              f"- Publication : {'faite' if publie else 'non faite'}", "",
              "## Par case", "",
              "| Case | " + " | ".join(nom for _, nom in ETAPES) + " | Publié | Taille |",
              "|---" * (len(ETAPES) + 3) + "|"]
    echecs = []
    for case in sorted(set(cases) | set(par_case)):
        etapes = par_case.get(case, {})
        cellules = [_verdict(etapes.get(cle, [])) for cle, _ in ETAPES]
        # Après la première étape en échec, les suivantes échouent en cascade
        # (« Reprendre le calcul » ne trouve rien) : elles ne sont pas faites,
        # et seule la cause compte.
        cause = next((i for i, v in enumerate(cellules) if v in ("échec", "trop long")), None)
        if cause is not None:
            cellules = cellules[:cause + 1] + ["non faite" if v else "" for v in cellules[cause + 1:]]
        assemble = cellules[-1] == "ok"
        lot = catalogue.get(case)
        if assemble and publie:
            etat_publie = "oui, ce run"
        elif lot is not None:
            etat_publie = "ancien lot"
        else:
            etat_publie = "non"
        taille = f"{lot['octets'] / 1e6:.0f} Mo" if lot and lot.get("octets") else ""
        sortie.append(f"| {case} | " + " | ".join(cellules) + f" | {etat_publie} | {taille} |")
        for cle, nom in ETAPES[cause:cause + 1] if cause is not None else ():
            for job in sorted(etapes.get(cle, []), key=lambda j: j.get("name", "")):
                if job.get("conclusion") in ("failure", "timed_out"):
                    fautive = _etape_fautive(job)
                    echecs.append(f"- {case}, {nom.lower()}"
                                  + (f" ({job['name'].rsplit(' ', 1)[-1]})" if cle == "calques" else "")
                                  + (f" : échec à l'étape « {fautive} »" if fautive else " : échec")
                                  + (f", [journal]({job['html_url']})" if job.get("html_url") else ""))
    sortie += ["", "## Échecs", ""] + (echecs or ["Aucun."])
    lignes, problemes = depot.fraicheur(contenu, cases, maintenant, jours_max)
    sortie += ["", depot.tableau_fraicheur(lignes, problemes, jours_max).rstrip("\n").replace(
        "## Fraîcheur des lots", "## Fraîcheur du catalogue publié")]
    return "\n".join(sortie) + "\n"
