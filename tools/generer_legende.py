"""Écrit la légende du PC et d'Android depuis leur source unique, hike2gpx/assets/legende.json.

    python tools/generer_legende.py            écrit les fichiers
    python tools/generer_legende.py --check    sort en erreur si l'un d'eux s'écarte de la source

Les parties générées d'un fichier existant sont entre deux balises « DEBUT LEGENDE » et
« FIN LEGENDE » ; le reste du fichier n'est pas touché. Le fichier Kotlin est entièrement
généré. tests/test_legende.py lance le mode --check : une légende modifiée à la main, ou
une source modifiée sans régénération, fait échouer la CI.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
SOURCE = RACINE / "hike2gpx" / "assets" / "legende.json"
WEB = RACINE / "hike2gpx" / "assets" / "web"
ANDROID = RACINE / "android" / "app" / "src" / "main"
NOTE = "généré par tools/generer_legende.py depuis hike2gpx/assets/legende.json : ne pas modifier à la main"


def charger() -> dict:
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def entrees(donnees: dict, plateforme: str) -> list:
    return [e for e in donnees["entrees"] if plateforme in e["plateformes"]]


# ------------------------------------------------------------------------------------------ PC
def bloc_html(donnees: dict) -> str:
    lignes = [f'      <div class="legende-tete"><h3 data-i18n="legende.titre">{donnees["titre"]["fr"]}</h3>'
              f'<button id="legendFermer" type="button" class="legende-fermer" title="{donnees["fermer"]["fr"]}" '
              f'aria-label="{donnees["fermer"]["fr"]}">×</button></div><ul id="legendRows">']
    for e in entrees(donnees, "pc"):
        pc = e["pc"]
        attributs = (f' id="{pc["idLigne"]}"' if pc.get("idLigne") else "") + (" hidden" if pc.get("masquee") else "")
        forme = "pastille" if e["forme"] == "pastille" else "trait"
        if pc.get("idTexte"):
            corps = f'<span id="{pc["idTexte"]}">{e["fr"].format(reseau=pc["reseauParDefaut"])}</span>'
        else:
            corps = f'<span data-i18n="legende.{e["id"]}">{e["fr"]}</span>'
        lignes.append(f'        <li{attributs}><span class="{forme} {pc["classe"]}"></span> {corps}</li>')
    lignes.append("      </ul>")
    return "\n".join(lignes)


def bloc_css(donnees: dict) -> str:
    regles = []
    for e in entrees(donnees, "pc"):
        pc = e["pc"]
        supplement = f" {pc['css']};" if pc.get("css") else ""
        if e["forme"] == "pastille":
            contour = f" border-color: {e['contour']};" if e.get("contour") else ""
            regles.append(f".pastille.{pc['classe']} {{ background: {e['couleur']};{contour} }}")
        else:
            style = "dashed" if e["forme"] == "tirets" else "solid"
            regles.append(f".trait.{pc['classe']} {{ border-top: {e['epaisseur']}px {style} {e['couleur']};{supplement} }}")
    return "\n".join(regles)


def bloc_js(donnees: dict, langue: str) -> str:
    def js(texte: str) -> str:
        return texte.replace("\\", "\\\\").replace('"', '\\"')
    lignes = [f'    "legende.titre": "{js(donnees["titre"][langue])}",',
              f'    "legende.fermer": "{js(donnees["fermer"][langue])}",']
    lignes += [f'    "legende.{e["id"]}": "{js(e[langue])}",' for e in entrees(donnees, "pc")]
    return "\n".join(lignes)


# ------------------------------------------------------------------------------------- Android
def bloc_strings(donnees: dict, langue: str) -> str:
    def xml(texte: str) -> str:
        # L'apostrophe droite se protège en Android ; le dépôt écrit l'apostrophe typographique.
        return texte.replace("&", "&amp;").replace("<", "&lt;").replace("'", "’").replace("{reseau}", "%1$s")
    lignes = [f'    <string name="legende_titre">{xml(donnees["titre"][langue])}</string>',
              f'    <string name="legende_fermer">{xml(donnees["fermer"][langue])}</string>']
    lignes += [f'    <string name="legende_{e["id"]}">{xml(e[langue])}</string>' for e in entrees(donnees, "android")]
    return "\n".join(lignes)


def argb(couleur: str) -> str:
    return f"0xff{couleur.lstrip('#').lower()}.toInt()"


def kotlin(donnees: dict) -> str:
    formes = {"trait": "TRAIT", "tirets": "TIRETS", "pastille": "PASTILLE"}
    lignes = []
    for e in entrees(donnees, "android"):
        contour = argb(e["contour"]) if e.get("contour") else "null"
        epaisseur = f"{e.get('epaisseur', 0)}f"
        lignes.append(f'        EntreeLegende("{e["id"]}", FormeLegende.{formes[e["forme"]]}, {argb(e["couleur"])}, '
                      f'{contour}, {epaisseur}, R.string.legende_{e["id"]}),')
    return f"""package org.hike2gpx.android

// {NOTE}

enum class FormeLegende {{ TRAIT, TIRETS, PASTILLE }}

/**
 * Une ligne de la légende. [texte] est la chaîne de ressource ; elle prend le nom du
 * réseau du pays (IGN, ATKIS…) en %1$s quand son identifiant est « chemins_officiels ».
 */
data class EntreeLegende(
    val id: String,
    val forme: FormeLegende,
    val couleur: Int,
    val contour: Int?,
    val epaisseur: Float,
    val texte: Int,
)

object LegendeGeneree {{
    val ENTREES = listOf(
{chr(10).join(lignes)}
    )
}}
"""


# -------------------------------------------------------------------------------------- cibles
def balises(commentaire: str, suffixe: str = "") -> tuple[str, str]:
    """Les deux lignes de balises d'un type de fichier : « /* … */ », « <!-- … --> » ou « // … »."""
    debut = f"DEBUT LEGENDE{suffixe} : {NOTE}"
    fin = f"FIN LEGENDE{suffixe}"
    if commentaire == "html":
        return f"<!-- {debut} -->", f"<!-- {fin} -->"
    if commentaire == "css":
        return f"/* {debut} */", f"/* {fin} */"
    return f"// {debut}", f"// {fin}"


def remplacer(texte: str, debut: str, fin: str, contenu: str) -> str:
    """Remplace ce qui sépare les lignes de balises ; les balises elles-mêmes et leur retrait restent."""
    motif = re.compile(rf"(?P<retrait>^[ \t]*){re.escape(debut)}\n(?P<corps>.*?)^[ \t]*{re.escape(fin)}", re.S | re.M)
    trouve = motif.search(texte)
    if not trouve:
        raise SystemExit(f"balises absentes : {debut}")
    return texte[:trouve.start("corps")] + contenu + "\n" + trouve.group("retrait") + fin + texte[trouve.end():]


def fichiers(donnees: dict) -> dict:
    """{chemin: nouveau contenu} de chaque fichier généré ou partiellement généré."""
    sorties = {}

    def partiel(chemin: Path, remplacements: list) -> None:
        texte = chemin.read_text(encoding="utf-8")
        for debut, fin, contenu in remplacements:
            texte = remplacer(texte, debut, fin, contenu)
        sorties[chemin] = texte

    partiel(WEB / "index.html", [(*balises("html"), bloc_html(donnees))])
    partiel(WEB / "style.css", [(*balises("css"), bloc_css(donnees))])
    partiel(WEB / "app.js", [(*balises("js", f" {langue}"), bloc_js(donnees, langue)) for langue in ("fr", "en")])
    partiel(ANDROID / "res" / "values-fr" / "strings.xml", [(*balises("html"), bloc_strings(donnees, "fr"))])
    partiel(ANDROID / "res" / "values" / "strings.xml", [(*balises("html"), bloc_strings(donnees, "en"))])
    sorties[ANDROID / "java" / "org" / "hike2gpx" / "android" / "LegendeGeneree.kt"] = kotlin(donnees)
    return sorties


def main(argv: list) -> int:
    verifier = "--check" in argv
    ecarts = []
    for chemin, contenu in fichiers(charger()).items():
        actuel = chemin.read_text(encoding="utf-8") if chemin.exists() else None
        if actuel == contenu:
            continue
        ecarts.append(chemin.relative_to(RACINE).as_posix())
        if not verifier:
            chemin.write_text(contenu, encoding="utf-8", newline="\n")
    if ecarts and verifier:
        print("La légende générée n'est pas à jour (python tools/generer_legende.py) :\n  " + "\n  ".join(ecarts))
        return 1
    print("légende : à jour" if not ecarts else "légende : écrit " + ", ".join(ecarts))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")    # la console Windows est en cp1252
    sys.exit(main(sys.argv[1:]))
