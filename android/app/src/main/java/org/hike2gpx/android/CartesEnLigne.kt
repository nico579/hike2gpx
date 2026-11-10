package org.hike2gpx.android

import org.osmdroid.tileprovider.tilesource.OnlineTileSourceBase
import org.osmdroid.util.MapTileIndex
import java.net.URLEncoder

/**
 * Une carte en ligne, la même que sur la page du PC : le gabarit de tuile et
 * l'attribution de providers/<pays>.js. Le SCAN 25 est le seul à demander la
 * clé IGN de l'utilisateur ; sans elle, la page propose le Plan IGN.
 */
data class CarteEnLigne(
    val cle: String,
    val libelle: Int,
    val gabarit: String,
    val zoomMax: Int,
    val attribution: String,
    val cleRequise: Boolean = false,
)

object CartesEnLigne {
    private const val WMTS = "https://data.geopf.fr/wmts"
    private const val WMTS_CLE = "https://data.geopf.fr/private/wmts"

    /** L'adresse WMTS de la Géoplateforme, comme tuileIgn() de providers/fr.js. */
    private fun ign(couche: String, format: String, cle: Boolean, matrices: String = "PM"): String {
        val base = if (cle) WMTS_CLE else WMTS
        return "$base?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=$couche&STYLE=normal" +
            "&TILEMATRIXSET=$matrices&FORMAT=$format&TILEMATRIX={z}&TILECOL={x}&TILEROW={y}" +
            if (cle) "&apikey={cle}" else ""
    }

    /** Les fonds en ligne de la page : les mêmes tuiles, servies au téléphone. */
    val TOUTES = listOf(
        CarteEnLigne("plan", R.string.fond_plan,
            ign("GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2", "image/png", false), 18, "© IGN"),
        CarteEnLigne("scan25", R.string.fond_scan25,
            ign("GEOGRAPHICALGRIDSYSTEMS.MAPS", "image/jpeg", true), 16, "© IGN", cleRequise = true),
        CarteEnLigne("osm", R.string.fond_osm,
            "https://tile.openstreetmap.org/{z}/{x}/{y}.png", 19, "© OpenStreetMap contributors"),
        CarteEnLigne("topo", R.string.fond_topo,
            "https://tile.opentopomap.org/{z}/{x}/{y}.png", 17,
            "© OpenStreetMap, SRTM | © OpenTopoMap (CC-BY-SA)"),
        CarteEnLigne("photos", R.string.fond_photos,
            ign("ORTHOIMAGERY.ORTHOPHOTOS", "image/jpeg", false), 19, "© IGN"),
        CarteEnLigne("relief", R.string.fond_relief,
            ign("IGNF_LIDAR-HD_MNT_ELEVATION.ELEVATIONGRIDCOVERAGE.SHADOW", "image/png", false, "PM_0_18"),
            18, "© IGN"),
        CarteEnLigne("satellite", R.string.fond_satellite,
            "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            19, "Esri, Vantor, Earthstar Geographics, and the GIS User Community"),
    )

    fun parCle(cle: String): CarteEnLigne? = TOUTES.firstOrNull { it.cle == cle }

    /** Celles qu'on peut choisir : le SCAN 25 seulement avec la clé IGN, comme sur le PC. */
    fun disponibles(cleIgn: String): List<CarteEnLigne> =
        TOUTES.filter { !it.cleRequise || cleIgn.isNotBlank() }

    /** Une source osmdroid qui remplit le gabarit, la clé comprise. */
    fun tuile(carte: CarteEnLigne, cleIgn: String): OnlineTileSourceBase =
        object : OnlineTileSourceBase(carte.cle, 0, carte.zoomMax, 256, "", arrayOf(""), carte.attribution) {
            override fun getTileURLString(pMapTileIndex: Long): String =
                carte.gabarit
                    .replace("{z}", MapTileIndex.getZoom(pMapTileIndex).toString())
                    .replace("{x}", MapTileIndex.getX(pMapTileIndex).toString())
                    .replace("{y}", MapTileIndex.getY(pMapTileIndex).toString())
                    .replace("{cle}", URLEncoder.encode(cleIgn, "UTF-8"))
        }
}
