package org.hike2gpx.android

import org.json.JSONArray
import java.io.File
import kotlin.math.asin
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt

/** Un point retenu dans une trace GPS, avec son instant (ms depuis 1970). */
data class PointTrace(val lat: Double, val lon: Double, val altitude: Double?, val instant: Long)

/** La distance en mètres entre deux points, formule de haversine (rayon terrestre moyen). */
fun distanceMetres(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Double {
    val rayon = 6_371_000.0
    val dLat = Math.toRadians(lat2 - lat1)
    val dLon = Math.toRadians(lon2 - lon1)
    val a = sin(dLat / 2).pow(2) +
        cos(Math.toRadians(lat1)) * cos(Math.toRadians(lat2)) * sin(dLon / 2).pow(2)
    return 2 * rayon * asin(min(1.0, sqrt(a)))
}

/**
 * Le filtre d'enregistrement de Locus Map : un point n'entre dans la trace
 * que si le GPS est assez précis (au plus [precisionMax] mètres de déviation),
 * et si [distanceMin] mètres et [dureeMin] millisecondes ont passé depuis le
 * point précédent. Le premier point n'a que la précision à respecter.
 *
 * Les fonctions sont pures : les tests les exercent sans réseau ni capteur.
 */
class TraceGps(
    var distanceMin: Double = 10.0,
    var dureeMin: Long = 10_000L,
    var precisionMax: Double = 100.0,
) {
    private val retenus = mutableListOf<PointTrace>()

    /** Les points retenus, dans l'ordre. */
    val points: List<PointTrace> get() = retenus.toList()

    val taille: Int get() = retenus.size

    /** La longueur de la trace, en mètres. */
    val distance: Double
        get() = retenus.zipWithNext().sumOf {
            distanceMetres(it.first.lat, it.first.lon, it.second.lat, it.second.lon)
        }

    /** La durée entre le premier et le dernier point, en millisecondes. */
    val duree: Long
        get() = if (retenus.size < 2) 0 else retenus.last().instant - retenus.first().instant

    /**
     * Ajoute un point s'il passe le filtre. [precision] est la déviation
     * annoncée par le GPS, en mètres ; null quand le GPS ne la donne pas (le
     * point est alors accepté, comme le fait Locus).
     */
    fun ajouter(lat: Double, lon: Double, altitude: Double?, instant: Long,
                precision: Double?): Boolean {
        if (!lat.isFinite() || !lon.isFinite() || lat !in -90.0..90.0 || lon !in -180.0..180.0)
            return false
        if (precision != null && precision > precisionMax) return false
        val dernier = retenus.lastOrNull()
        if (dernier != null) {
            if (instant - dernier.instant < dureeMin) return false
            if (distanceMetres(dernier.lat, dernier.lon, lat, lon) < distanceMin) return false
        }
        retenus.add(PointTrace(lat, lon, altitude, instant))
        return true
    }

    /** Le même ordre que les tracés de la page : [lon, lat, alt]. */
    fun geojson(): JSONArray = JSONArray().apply {
        retenus.forEach { p ->
            put(JSONArray().put(p.lon).put(p.lat).apply { p.altitude?.let { put(it) } })
        }
    }
}

/**
 * L'enregistrement en cours, gardé au niveau du processus : une rotation de
 * l'écran ne perd ni les points déjà retenus, ni l'état du bouton. Le fichier
 * GPX n'est écrit qu'à l'arrêt, avec tous les points.
 */
object EnregistrementGps {
    @Volatile
    var trace: TraceGps? = null
        private set

    @Volatile
    var fichier: File? = null
        private set

    val actif: Boolean get() = trace != null

    fun demarrer(trace: TraceGps, fichier: File) {
        this.trace = trace
        this.fichier = fichier
    }

    fun arreter(): TraceGps? {
        val fini = trace
        trace = null
        return fini
    }
}
