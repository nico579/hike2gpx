"""Chemins BDOT10k du service régional de Basse-Silésie."""
from .core import _arcgis


def lire(s, w, n, e):
    url = "https://geoportal.dolnyslask.pl/gisserver1/rest/services/BDOT10k/FeatureServer/18"
    return _arcgis(((url, "ścieżka"),), (s, w, n, e),
                   lambda a: a.get("rodzaj") == "ścieżka"
                   and a.get("kategoriaistnienia") in (None, "eksploatowany"))
