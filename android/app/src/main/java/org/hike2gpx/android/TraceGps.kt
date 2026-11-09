package org.hike2gpx.android

import org.json.JSONArray
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
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

    /** Le dénivelé gpx2elev de ce qui est déjà enregistré, ou null hors cache. */
    var profil: ProfilAltimetrique? = null

    /** Les points retenus, dans l'ordre. */
    val points: List<PointTrace> get() = retenus.toList()

    val taille: Int get() = retenus.size

    /** Le dernier point retenu, sans copier toute la trace. */
    val dernier: PointTrace? get() = retenus.lastOrNull()

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
 * L'enregistrement en cours, gardé au niveau du processus : ServiceTrace y
 * verse les positions, l'écran s'y abonne pour dessiner. Une rotation, ou un
 * écran fermé pendant que le service tourne, ne perd ni les points ni l'état.
 *
 * Chaque point retenu s'ajoute aussi au journal `<trace>.gpx.journal`, une
 * ligne par point, synchronisée sur disque. Si Android tue le processus ou si
 * la batterie lâche en route, [recuperer] refait le GPX au lancement suivant ;
 * à l'arrêt normal, le GPX est écrit puis le journal effacé ([terminer]).
 *
 * Toutes les fonctions s'appellent sur le fil principal, sauf les lectures de
 * [trace] et de [fichier].
 */
object EnregistrementGps {
    @Volatile
    var trace: TraceGps? = null
        private set

    @Volatile
    var fichier: File? = null
        private set

    private var journal: FileOutputStream? = null
    private val observateurs = mutableSetOf<() -> Unit>()

    val actif: Boolean get() = trace != null

    fun demarrer(trace: TraceGps, fichier: File) {
        fermerJournal()
        this.trace = trace
        this.fichier = fichier
        journal = try {
            FileOutputStream(journalDe(fichier), true)
        } catch (e: IOException) {
            null        // la trace continue en mémoire, comme avant le journal
        }
    }

    /** Une position reçue : filtre de la trace, journal, puis les écrans abonnés. */
    fun ajouter(lat: Double, lon: Double, altitude: Double?, instant: Long,
                precision: Double?): Boolean {
        val trace = trace ?: return false
        if (!trace.ajouter(lat, lon, altitude, instant, precision)) return false
        journal?.let { flux ->
            try {
                flux.write(ligne(trace.dernier!!))
                flux.fd.sync()
            } catch (e: IOException) {
                // disque plein ou retiré : le point reste en mémoire
            }
        }
        observateurs.toList().forEach { it() }
        return true
    }

    /** Arrête l'enregistrement ; le journal reste tant que le GPX n'est pas écrit. */
    fun arreter(): TraceGps? {
        val fini = trace
        trace = null
        fermerJournal()
        return fini
    }

    /** Le GPX de [fichier] est écrit : son journal ne sert plus. */
    fun terminer(fichier: File) {
        journalDe(fichier).delete()
    }

    fun abonner(observateur: () -> Unit) { observateurs.add(observateur) }

    fun desabonner(observateur: () -> Unit) { observateurs.remove(observateur) }

    private fun fermerJournal() {
        try {
            journal?.close()
        } catch (e: IOException) {
            // rien à sauver de plus
        }
        journal = null
    }

    fun journalDe(fichier: File) = File(fichier.parentFile, fichier.name + SUFFIXE)

    /** Une ligne du journal : latitude;longitude;altitude (vide si absente);instant. */
    fun ligne(p: PointTrace): ByteArray =
        "${p.lat};${p.lon};${p.altitude ?: ""};${p.instant}\n".toByteArray(Charsets.US_ASCII)

    /** Les points d'un journal ; une dernière ligne coupée par l'arrêt brutal est ignorée. */
    fun lireJournal(journal: File): List<PointTrace> = journal.readLines(Charsets.US_ASCII).mapNotNull {
        val champs = it.split(';')
        if (champs.size != 4) return@mapNotNull null
        val lat = champs[0].toDoubleOrNull() ?: return@mapNotNull null
        val lon = champs[1].toDoubleOrNull() ?: return@mapNotNull null
        val instant = champs[3].toLongOrNull() ?: return@mapNotNull null
        PointTrace(lat, lon, champs[2].toDoubleOrNull(), instant)
    }

    /**
     * Les traces interrompues de [dossier] : chaque journal resté sans
     * enregistrement en cours redevient un GPX, puis s'efface. Rend les GPX
     * refaits ; un journal vide s'efface sans rien produire.
     */
    fun recuperer(dossier: File): List<File> {
        if (actif) return emptyList()
        val journaux = dossier.listFiles { f -> f.isFile && f.name.endsWith(".gpx$SUFFIXE") }
            ?: return emptyList()
        return journaux.sortedBy { it.name }.mapNotNull { journal ->
            try {
                val points = lireJournal(journal)
                val gpx = File(dossier, journal.name.removeSuffix(SUFFIXE))
                if (points.isNotEmpty()) gpx.writeText(Gpx.ecrireTrace(points, gpx.nameWithoutExtension))
                journal.delete()
                if (points.isNotEmpty()) gpx else null
            } catch (e: IOException) {
                null    // illisible aujourd'hui : on réessaiera au prochain lancement
            }
        }
    }

    private const val SUFFIXE = ".journal"
}
