"""Prépare l'icône de hike2gpx depuis l'image choisie par Nico (courbes de
niveau, montagnes, sentier, clôture et épingle sur un carré vert) : recadrée
sur le carré, rendue franchement opaque, puis écrite en
hike2gpx/assets/hike2gpx.png (512 px : raccourcis Linux et macOS, icône du
programme macOS) et hike2gpx.ico (de 16 à 256 px : Windows, zone de
notification, onglet de la page).

    python tools/icone.py IMAGE     à partir d'une nouvelle image
    python tools/icone.py           refait le .ico depuis le .png en place
"""
import sys
from pathlib import Path

from PIL import Image

DOSSIER = Path(__file__).resolve().parents[1] / "hike2gpx" / "assets"
COTE = 512
TAILLES_ICO = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)]


def preparer(source: Path) -> Image.Image:
    image = Image.open(source).convert("RGBA")
    # Le générateur d'images laisse l'intérieur à 252/255 d'opacité et quelques
    # points presque invisibles autour du carré : les deux sont nettoyés, seuls
    # les bords adoucis gardent une opacité partielle.
    alpha = image.getchannel("A").point(lambda a: 255 if a >= 240 else 0 if a < 16 else a)
    image.putalpha(alpha)
    gauche, haut, droite, bas = alpha.point(lambda a: 255 if a >= 128 else 0).getbbox()
    cote = max(droite - gauche, bas - haut)
    x, y = (gauche + droite - cote) // 2, (haut + bas - cote) // 2
    return image.crop((x, y, x + cote, y + cote)).resize((COTE, COTE), Image.Resampling.LANCZOS)


if __name__ == "__main__":
    png = DOSSIER / "hike2gpx.png"
    if len(sys.argv) > 1:
        preparer(Path(sys.argv[1])).save(png, optimize=True)
    Image.open(png).save(DOSSIER / "hike2gpx.ico", sizes=TAILLES_ICO)
    print(f"Icône écrite dans {DOSSIER}")
