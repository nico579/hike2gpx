"""Chemins ZABAGED tchèques, lus par petite emprise."""
from .core import _arcgis


def lire(s, w, n, e):
    racine = "https://ags.cuzk.gov.cz/arcgis/rest/services/ZABAGED_POLOHOPIS/MapServer"
    return _arcgis(((f"{racine}/82", "Pěšina"), (f"{racine}/83", "Cesta")), (s, w, n, e))
