"""Écrit les profils BRouter de l'application Android, dans ses assets.

Le téléphone calcule sur les RD5 des lots sans rien fabriquer : il lui faut
pourtant la table de tags et le profil avec lesquels le PC calcule sur ces
mêmes RD5 (brouter.py). Ils sont tirés des fichiers de BRouter 1.7.10 (le
sous-module android/brouter) par les fonctions mêmes du PC, puis versionnés :
tests/test_android.py vérifie qu'ils n'ont pas dérivé.

  osm/      lot OSM : table de tags standard, profil hike2gpx
  enrichi/  lot enrichi : table de tags avec la clé hike2gpx, profil maison

    python tools/profils_android.py
"""
from pathlib import Path
import sys

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
from hike2gpx import brouter  # noqa: E402

SOURCE = RACINE / "android" / "brouter" / "misc" / "profiles2"
ASSETS = RACINE / "android" / "app" / "src" / "main" / "assets" / "brouter"


def profils(lookups: str, randonnee: str) -> dict:
    """Contenu de chaque fichier d'assets, par chemin relatif."""
    profil = brouter.profil_hike2gpx(randonnee)
    return {"osm/lookups.dat": lookups,
            f"osm/{brouter.PROFIL}.brf": profil,
            "enrichi/lookups.dat": brouter.lookups_ign(lookups),
            f"enrichi/{brouter.PROFIL}.brf": brouter.profil_maison(profil)}


def main() -> None:
    lookups = (SOURCE / "lookups.dat").read_text(encoding="utf-8")
    randonnee = (SOURCE / "hiking-mountain.brf").read_text(encoding="utf-8")
    for relatif, texte in profils(lookups, randonnee).items():
        chemin = ASSETS / relatif
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(texte, encoding="utf-8", newline="\n")
        print(chemin.relative_to(RACINE))


if __name__ == "__main__":
    main()
