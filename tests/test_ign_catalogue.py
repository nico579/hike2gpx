import xml.etree.ElementTree as ET

from deploy.linux import ign_catalogue


def test_catalogue_choisit_la_derniere_edition_et_ses_archives():
    nom = "BDTOPO_3-5_TOUSTHEMES_GPKG_LAMB93_R93_2026-09-15"
    base = "https://data.geopf.fr/telechargement/download/BDTOPO/" + nom + "/" + nom
    ressources = """<feed xmlns="http://www.w3.org/2005/Atom">
      <entry><title>BDTOPO_3-5_TOUSTHEMES_GPKG_LAMB93_R93_2026-06-15</title></entry>
      <entry><title>BDTOPO_3-5_TOUSTHEMES_GPKG_LAMB93_R93_2026-09-15</title></entry>
    </feed>"""
    fichiers = f"""<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:gpf_dl="https://data.geopf.fr/annexes/ressources/xsd/gpf_dl.xsd">
      <entry><link rel="alternate" href="{base}.7z" gpf_dl:length="120"/>
        <content>0123456789abcdef0123456789abcdef</content></entry>
    </feed>"""
    paquet = ign_catalogue.derniere_edition("R93", lambda url: ET.fromstring(
        ressources if "?lang=" in url else fichiers))
    assert paquet["edition"] == nom
    assert paquet["octets"] == 120
    assert paquet["fichiers"][0]["url"] == base + ".7z"
