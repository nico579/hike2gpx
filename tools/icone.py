"""Dessine l'icône de hike2gpx : une montagne blanche et un sentier orange en
lacets sur le bleu de la page, lisibles jusqu'en 16 px. Produit
hike2gpx/assets/hike2gpx.png (256 px) et hike2gpx.ico (de 16 à 256 px).

    python tools/icone.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

DOSSIER = Path(__file__).resolve().parents[1] / "hike2gpx" / "assets"
BLEU, ORANGE, BLANC = (21, 101, 192, 255), (239, 108, 0, 255), (255, 255, 255, 255)
COTE = 256


def dessiner() -> Image.Image:
    image = Image.new("RGBA", (COTE, COTE), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)
    d.rounded_rectangle([8, 8, COTE - 8, COTE - 8], radius=48, fill=BLEU)
    d.polygon([(26, 206), (104, 66), (146, 130), (170, 100), (230, 206)], fill=BLANC)
    d.line([(64, 228), (124, 202), (92, 178), (150, 156), (126, 134)], fill=ORANGE, width=16, joint="curve")
    return image


if __name__ == "__main__":
    icone = dessiner()
    icone.save(DOSSIER / "hike2gpx.png")
    icone.save(DOSSIER / "hike2gpx.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128),
                                               (256, 256)])
    print(f"Icône écrite dans {DOSSIER}")
