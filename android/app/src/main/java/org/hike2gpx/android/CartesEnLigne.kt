package org.hike2gpx.android

import org.osmdroid.tileprovider.tilesource.OnlineTileSourceBase
import org.osmdroid.util.MapTileIndex
import java.net.URLEncoder

/**
 * Une carte en ligne, la même que sur la page du PC : le gabarit de tuile et
 * l'attribution de providers/<pays>.js. Une carte nationale ne s'affiche que
 * dans son pays, et la page « Gestion des cartes » propose celles du pays du
 * centre de la carte : une carte nationale suit le pays, un fond du monde reste.
 * Le SCAN 25 est le seul à demander la clé IGN de l'utilisateur.
 */
data class CarteEnLigne(
    val cle: String,
    val libelle: Int,
    val gabarit: String,
    val zoomMax: Int,
    val attribution: String,
    val pays: String? = null,           // null : une carte du monde
    val cleRequise: Boolean = false,
    val wms4326: Boolean = false,       // le WMS de la Pologne, en degrés
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

    /** Les cartes de la page, pays par pays, puis celles du monde. */
    val TOUTES = listOf(
        CarteEnLigne("scan25", R.string.fond_scan25,
            ign("GEOGRAPHICALGRIDSYSTEMS.MAPS", "image/jpeg", true), 16, "© IGN",
            pays = "fr", cleRequise = true),
        CarteEnLigne("plan", R.string.fond_plan,
            ign("GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2", "image/png", false), 18, "© IGN",
            pays = "fr"),
        CarteEnLigne("photos", R.string.fond_photos,
            ign("ORTHOIMAGERY.ORTHOPHOTOS", "image/jpeg", false), 19, "© IGN",
            pays = "fr"),
        CarteEnLigne("relief", R.string.fond_relief,
            ign("IGNF_LIDAR-HD_MNT_ELEVATION.ELEVATIONGRIDCOVERAGE.SHADOW", "image/png", false, "PM_0_18"),
            18, "© IGN", pays = "fr"),

        CarteEnLigne("suisse", R.string.fond_suisse,
            "https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.pixelkarte-farbe/default/current/3857/{z}/{x}/{y}.jpeg",
            18, "© swisstopo", pays = "ch"),
        CarteEnLigne("allemagne", R.string.fond_allemagne,
            "https://sgx.geodatenzentrum.de/wmts_topplus_open/tile/1.0.0/web/default/WEBMERCATOR/{z}/{y}/{x}.png",
            18, "© BKG (dl-de/by-2-0)", pays = "de"),
        CarteEnLigne("autriche", R.string.fond_autriche,
            "https://mapsneu.wien.gv.at/basemap/geolandbasemap/normal/google3857/{z}/{y}/{x}.png",
            19, "© basemap.at", pays = "at"),
        CarteEnLigne("tchequie", R.string.fond_tchequie,
            "https://ags.cuzk.gov.cz/arcgis1/rest/services/ZTM_WM/MapServer/tile/{z}/{y}/{x}",
            18, "© ČÚZK", pays = "cz"),
        CarteEnLigne("espagne", R.string.fond_espagne,
            "https://www.ign.es/wmts/mapa-raster?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0" +
                "&LAYER=MTN&STYLE=default&TILEMATRIXSET=GoogleMapsCompatible&FORMAT=image/jpeg" +
                "&TILEMATRIX={z}&TILECOL={x}&TILEROW={y}",
            18, "© IGN España", pays = "es"),
        CarteEnLigne("luxembourg", R.string.fond_luxembourg,
            "https://wmts1.geoportail.lu/opendata/wmts/topomap/GLOBAL_WEBMERCATOR/{z}/{x}/{y}.png",
            19, "© ACT Luxembourg", pays = "lu"),
        CarteEnLigne("paysBas", R.string.fond_pays_bas,
            "https://service.pdok.nl/kadaster/brt-achtergrondkaart/wmts/v2_0/standaard/EPSG:3857/{z}/{x}/{y}.png",
            19, "© Kadaster / PDOK", pays = "nl"),
        CarteEnLigne("norvege", R.string.fond_norvege,
            "https://cache.kartverket.no/v1/wmts/1.0.0/toporaster/default/webmercator/{z}/{y}/{x}.png",
            18, "© Kartverket", pays = "no"),
        CarteEnLigne("etatsUnis", R.string.fond_etats_unis,
            "https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}",
            16, "© USGS The National Map", pays = "us"),
        // Le Geoportal polonais ne sert son fond qu'en WMS, en degrés, là où le
        // PC travaille en EPSG:4326 ; le téléphone demande la vue de la tuile.
        CarteEnLigne("plTopo", R.string.fond_pologne,
            "https://mapy.geoportal.gov.pl/wss/service/img/guest/TOPO/MapServer/WMSServer" +
                "?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&LAYERS=Raster&STYLES=&SRS=EPSG:4326" +
                "&BBOX={bbox}&WIDTH=256&HEIGHT=256&FORMAT=image/png",
            19, "© GUGiK / Geoportal Polska", pays = "pl", wms4326 = true),

        CarteEnLigne("topo", R.string.fond_topo,
            "https://tile.opentopomap.org/{z}/{x}/{y}.png", 17,
            "© OpenStreetMap, SRTM | © OpenTopoMap (CC-BY-SA)"),
        CarteEnLigne("osm", R.string.fond_osm,
            "https://tile.openstreetmap.org/{z}/{x}/{y}.png", 19, "© OpenStreetMap contributors"),
        CarteEnLigne("satellite", R.string.fond_satellite,
            "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            19, "Esri, Vantor, Earthstar Geographics, and the GIS User Community"),
    )

    /** Le fond national de chaque pays, d'après providers/<pays>.js. */
    private val DEFAUTS = mapOf(
        "fr" to "plan", "ch" to "suisse", "de" to "allemagne", "at" to "autriche",
        "cz" to "tchequie", "es" to "espagne", "lu" to "luxembourg", "nl" to "paysBas",
        "no" to "norvege", "us" to "etatsUnis", "pl" to "plTopo",
    )

    /** Le fond d'un pays : sa carte nationale, OSM ailleurs. */
    fun defaut(pays: String): String = DEFAUTS[pays] ?: "osm"

    fun parCle(cle: String): CarteEnLigne? = TOUTES.firstOrNull { it.cle == cle }

    /** Celles qu'on peut choisir ici : celles du pays affiché et celles du monde. */
    fun disponibles(pays: String, cleIgn: String): List<CarteEnLigne> =
        TOUTES.filter { (it.pays == null || it.pays == pays) && (!it.cleRequise || cleIgn.isNotBlank()) }

    /** Vrai si cette carte se sert dans ce pays, avec cette clé. */
    fun disponible(cle: String, pays: String, cleIgn: String): Boolean =
        parCle(cle)?.let { (it.pays == null || it.pays == pays) && (!it.cleRequise || cleIgn.isNotBlank()) } == true

    /** Une source osmdroid qui remplit le gabarit, la clé comprise. */
    fun tuile(carte: CarteEnLigne, cleIgn: String): OnlineTileSourceBase =
        object : OnlineTileSourceBase(carte.cle, 0, carte.zoomMax, 256, "", arrayOf(""), carte.attribution) {
            override fun getTileURLString(pMapTileIndex: Long): String {
                val z = MapTileIndex.getZoom(pMapTileIndex)
                val x = MapTileIndex.getX(pMapTileIndex)
                val y = MapTileIndex.getY(pMapTileIndex)
                if (carte.wms4326) {
                    val ouest = longitudeDe(z, x)
                    val est = longitudeDe(z, x + 1)
                    val nord = latitudeDe(z, y)
                    val sud = latitudeDe(z, y + 1)
                    return carte.gabarit.replace("{bbox}", "$ouest,$sud,$est,$nord")
                }
                return carte.gabarit
                    .replace("{z}", z.toString())
                    .replace("{x}", x.toString())
                    .replace("{y}", y.toString())
                    .replace("{cle}", URLEncoder.encode(cleIgn, "UTF-8"))
            }
        }

    /** Le bord ouest (x) d'une tuile, en degrés. */
    private fun longitudeDe(z: Int, x: Int): Double = x.toDouble() / (1L shl z) * 360.0 - 180.0

    /** Le bord nord (y) d'une tuile, en degrés (Mercator, comme la page). */
    private fun latitudeDe(z: Int, y: Int): Double =
        Math.toDegrees(kotlin.math.atan(kotlin.math.sinh(Math.PI * (1.0 - 2.0 * y / (1L shl z)))))
}
