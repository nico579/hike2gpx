"""Capacités des fournisseurs officiels : fond, chemins et routage par zone.

Les lecteurs nationaux et les utilitaires communs vivent dans leurs modules.
"""
from . import atkis, bdtopo, bdot10k, swisstlm3d, zabaged
from .core import Source, TuilesOfficielles


SOURCES = {
    "ign": Source("ign", "fr", "IGN", bdtopo, "bdtopo"),
    "atkis": Source("atkis", "de", "ATKIS", atkis, "atkis"),
    "zabaged": Source("zabaged", "cz", "ZABAGED", TuilesOfficielles("zabaged", zabaged.lire), "zabaged"),
    "swisstlm3d": Source("swisstlm3d", "ch", "swissTLM3D", TuilesOfficielles("swisstlm3d", swisstlm3d.lire), "swisstlm3d"),
    "bdot10k_ds": Source("bdot10k_ds", "pl", "BDOT10k", TuilesOfficielles("bdot10k_ds", bdot10k.lire),
                          "bdot10k_ds", (50.0, 14.7, 51.85, 17.85)),
}

PAYS_CARTES = {"france": "fr", "spain": "es", "switzerland": "ch", "germany": "de",
               "austria": "at", "netherlands": "nl", "norway": "no",
               "luxembourg": "lu", "us": "us", "czech-republic": "cz", "poland": "pl"}


def source(cle):
    try:
        return SOURCES[cle]
    except KeyError as exc:
        raise ValueError("Source de chemins officiels inconnue.") from exc
