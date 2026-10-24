"""Lecture par zone des tuiles officielles basemap.de."""
from io import BytesIO

import mapbox_vector_tile

from hike2gpx import basemap_atkis


def test_tuile_vectorielle_est_decoupee_et_filtree_par_land():
    x, y = 17585, 10977
    bornes = (basemap_atkis._lat(y + 1), basemap_atkis._lon(x),
              basemap_atkis._lat(y), basemap_atkis._lon(x + 1))
    objets = [{"geometry": {"type": "LineString", "coordinates": [[-40, 2000], [4140, 2000]]},
               "properties": {"land": land, "klasse": "Wirtschaftsweg"}}
              for land in ("SN", "BY")]
    pbf = mapbox_vector_tile.encode({"name": "Verkehrslinie", "features": objets},
                                    default_options={"y_coord_down": True})
    requetes = []

    def ouvrir(demande, timeout):
        requetes.append(demande.full_url)
        return BytesIO(pbf)

    troncons = basemap_atkis._lire_tuile(x, y, bornes, ouvrir)
    assert len(requetes) == 1 and f"/15/{x}/{y}.pbf" in requetes[0]
    assert len(troncons) == 1 and troncons[0]["land"] == "SN"
    assert len(troncons[0]["pts"]) == 2
    assert troncons[0]["bords"] == [True, True]
    assert all(bornes[0] <= lat <= bornes[2] and bornes[1] <= lon <= bornes[3]
               for lat, lon in troncons[0]["pts"])
