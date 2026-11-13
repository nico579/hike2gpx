import pytest


@pytest.fixture(autouse=True)
def depot_des_lots_local(tmp_path, monkeypatch):
    """Aucun essai ne lit le vrai dépôt des lots sur GitHub : la question de
    la planification y chercherait le lot de sa zone (zone_planification), et
    un essai pourrait en télécharger un vrai. Le dépôt d'essai est un fichier absent ; un essai qui
    sert un catalogue remplace urlopen (test_depot.servir)."""
    monkeypatch.setenv("HIKE2GPX_DEPOT", (tmp_path / "depot-des-lots" / "catalog.json").as_uri())


@pytest.fixture(autouse=True)
def calques_en_serie(monkeypatch, request):
    """Les calques en série dans les essais : un fils lancé par spawn recharge
    les vrais modules, sans les remplacements de l'essai (mode_en_ligne). Le
    chemin parallèle a son propre essai, sur de vraies données
    (test_calques_paralleles.py), qui s'en dispense."""
    if "spawn_reel" not in request.keywords:
        from hike2gpx import fabrication
        monkeypatch.setattr(fabrication, "processus_spawn", lambda: 1)


@pytest.fixture(autouse=True)
def zones_de_routage_presentes(monkeypatch, request):
    """Les essais du calcul tournent sans lot installé : chaque case passe pour
    couverte. Le refus d'un tracé sans zone de routage a son propre essai
    (marqueur zones_reelles), qui s'en dispense."""
    if "zones_reelles" not in request.keywords:
        from hike2gpx import application
        monkeypatch.setattr(application.Application, "_cases_sans_lot", lambda self, zone: [])


# Fixtures de test_fabrication.py servies à tous les fichiers (la fabrication
# répartie, les calques en parallèle) : les importer fichier par fichier les
# faisait passer pour des redéfinitions aux yeux de ruff (F811).
from test_fabrication import mode_en_ligne, osm_installe  # noqa: E402,F401
