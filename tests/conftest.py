import pytest


@pytest.fixture(autouse=True)
def depot_des_lots_local(tmp_path, monkeypatch):
    """Aucun essai ne lit le vrai dépôt des lots sur GitHub : un calcul ou un
    calque y chercherait le lot de sa zone (_lot_automatique), et pourrait en
    télécharger un vrai. Le dépôt d'essai est un fichier absent ; un essai qui
    sert un catalogue remplace urlopen (test_depot.servir)."""
    monkeypatch.setenv("HIKE2GPX_DEPOT", (tmp_path / "depot-des-lots" / "catalog.json").as_uri())
