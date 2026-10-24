# Supported countries

This table is generated from `hike2gpx/assets/web/providers/*.js`. It lists each national map, its path layers and the data used by BRouter for route calculation. OpenStreetMap remains available everywhere.

| Country | Map base | Path layers | Route calculation |
| --- | --- | --- | --- |
| Austria | basemap.at | OSM | OSM |
| Czechia | ZTM map (ČÚZK) | ZABAGED paths (Czechia) | OSM + ZABAGED |
| France | IGN map (SCAN 25 with a key) | BD TOPO paths (IGN) | OSM + IGN |
| Germany | BKG TopPlusOpen | ATKIS paths (Germany) | OSM + ATKIS |
| Luxembourg | ACT topographic map | OSM | OSM |
| Netherlands | PDOK topographic map | OSM | OSM |
| Norway | Kartverket topographic map | OSM | OSM |
| Poland | Polish topographic map (Geoportal) | BDOT10k paths (Lower Silesia) | OSM + BDOT10k (Lower Silesia) |
| Spain | Spanish IGN topographic map | FEDME waymarked trails | OSM |
| Switzerland | swisstopo national map | swissTLM3D paths (Switzerland) · swisstopo hiking trails | OSM + swissTLM3D |
| United States | USGS topographic map | USGS trails | OSM |

Official paths are loaded only for the area being viewed. In Poland, the BDOT10k path layer and routing support cover Lower Silesia only. Marked trails in Spain and the United States are display only.

For the measurements and source limitations, see the [French report](RAPPORT_SOURCES_CHEMINS_BROUTER.md).
