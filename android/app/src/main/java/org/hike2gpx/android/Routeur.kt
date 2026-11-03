package org.hike2gpx.android

import btools.router.FormatJson
import btools.router.RoutingContext
import btools.router.RoutingEngine
import btools.router.RoutingParamCollector
import org.json.JSONObject
import java.io.File
import java.util.Locale

class ErreurCalcul(message: String) : Exception(message)

/**
 * BRouter 1.7.10, compilé dans l'application, calcule sur la RD5 d'un lot
 * installé avec les coupes de ses franchissements (paramètre polylines),
 * comme le serveur BRouter du PC (brouter.calculer).
 *
 * profils contient deux dossiers, chacun avec sa table de tags et son profil
 * hike2gpx.brf (tools/profils_android.py) : enrichi/ pour les RD5 enrichies,
 * osm/ pour les RD5 officielles. BRouter lit lookups.dat à côté du profil.
 */
class Routeur(private val profils: File) {
    @Volatile private var courant: RoutingEngine? = null

    fun annuler() {
        courant?.terminate()
    }

    /** L'itinéraire en GeoJSON : une Feature LineString [lon, lat, alt]. */
    fun calculer(segments: File, enrichi: Boolean, points: List<Point>, polylines: String,
                 officiels: Boolean = true, memoireMo: Int = 64): JSONObject {
        require(points.size >= 2) { "Il faut au moins deux points." }
        val collecteur = RoutingParamCollector()
        val lonlats = points.joinToString("|") { String.format(Locale.US, "%.6f,%.6f", it.lon, it.lat) }
        val etapes = collecteur.getWayPointList(lonlats)
        val contexte = RoutingContext()
        contexte.localFunction = File(File(profils, if (enrichi) "enrichi" else "osm"), "$PROFIL.brf").absolutePath
        contexte.memoryclass = memoireMo.coerceIn(16, 256)
        val parametres = HashMap<String, String>()
        parametres["format"] = "geojson"
        parametres["alternativeidx"] = "0"
        if (polylines.isNotEmpty()) parametres["polylines"] = polylines
        // Un lot enrichi sert aussi sans ses chemins officiels (profil maison, chemins_officiels).
        if (enrichi && !officiels) parametres["profile:chemins_officiels"] = "0"
        collecteur.setParams(contexte, etapes, parametres)
        val moteur = RoutingEngine(null, null, segments, etapes, contexte)
        moteur.quite = true
        courant = moteur
        try {
            moteur.doRun(DELAI_MS)
        } finally {
            courant = null
        }
        moteur.errorMessage?.let { throw ErreurCalcul(message(it)) }
        val trace = moteur.foundTrack ?: throw ErreurCalcul("Aucun itinéraire trouvé.")
        val geojson = JSONObject(FormatJson(contexte).format(trace))
        val feature = geojson.optJSONArray("features")?.optJSONObject(0) ?: geojson
        if (feature.optJSONObject("geometry")?.optString("type") != "LineString")
            throw ErreurCalcul("Réponse BRouter inattendue.")
        return feature
    }

    companion object {
        const val PROFIL = "hike2gpx"
        const val DELAI_MS = 60_000L

        private val MESSAGES = listOf(
            "datafile" to "Données BRouter absentes pour cette zone.",
            "not found" to "Aucun chemin praticable trouvé près d'un des points.",
            "no track found" to "Aucun itinéraire ne respecte les barrières entre ces points.",
            "target island" to "Le point d'arrivée est isolé du réseau praticable.",
            "operation killed" to "Calcul trop long : rapprochez les points.",
        )

        fun message(brut: String): String =
            MESSAGES.firstOrNull { brut.lowercase().contains(it.first) }?.second ?: "BRouter : ${brut.take(200)}"
    }
}
