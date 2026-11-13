import pytest


@pytest.fixture(autouse=True)
def depot_des_lots_local(tmp_path, monkeypatch):
    """Aucun essai ne lit le vrai dépôt des lots sur GitHub : la question de
    la planification y chercherait le lot de sa zone (zone_planification), et
    un essai pourrait en télécharger un vrai. Le dépôt d'essai est un fichier absent ; un essai qui
    sert un catalogue remplace urlopen (test_depot.servir)."""
    monkeypatch.setenv("HIKE2GPX_DEPOT", (tmp_path / "depot-des-lots" / "catalog.json").as_uri())


# Fixtures de test_fabrication.py servies à tous les fichiers (la fabrication
# répartie, les calques en parallèle) : les importer fichier par fichier les
# faisait passer pour des redéfinitions aux yeux de ruff (F811).
from test_fabrication import mode_en_ligne, osm_installe  # noqa: E402,F401
