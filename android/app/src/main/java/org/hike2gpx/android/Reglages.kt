package org.hike2gpx.android

import android.content.Context
import java.io.File

/**
 * Ce que l'application garde d'une session à l'autre : la carte, la vue, les
 * calques, les réglages de trace.
 */
class Reglages(context: Context) {
    private val preferences = context.getSharedPreferences("hike2gpx", Context.MODE_PRIVATE)

    /**
     * Les PC scannés n'étaient pas oubliés jusqu'en 0.9.13 : le téléphone les
     * relisait seul, avec un jeton que le PC avait périmé en refermant son
     * partage. Un PC ne se contacte plus qu'au scan de son QR code ; la
     * liste laissée par une version antérieure s'efface.
     */
    fun oublierPcs() = preferences.edit().remove(PCS).apply()

    /** Le fond affiché : une carte en ligne (« plan », « scan25 »…) ou la source d'un fond hors ligne. */
    var fond: String
        get() = preferences.getString(FOND, "plan") ?: "plan"
        set(v) = preferences.edit().putString(FOND, v).apply()

    /**
     * La clé IGN de l'utilisateur, pour le SCAN 25, comme le réglage du PC
     * (prefs « cle_ign »). Vide : la page propose le Plan IGN à sa place.
     */
    var cleIgn: String
        get() = preferences.getString(CLE_IGN, "") ?: ""
        set(v) = preferences.edit().putString(CLE_IGN, v.trim()).apply()

    var strict: Boolean
        get() = preferences.getBoolean(STRICT, false)
        set(v) = preferences.edit().putBoolean(STRICT, v).apply()

    var officiels: Boolean
        get() = preferences.getBoolean(OFFICIELS, true)
        set(v) = preferences.edit().putBoolean(OFFICIELS, v).apply()

    /** Les chemins OSM (voies, barrières, franchissements) dessinés sur la carte. */
    var calqueOsm: Boolean
        get() = preferences.getBoolean(CALQUE_OSM, true)
        set(v) = preferences.edit().putBoolean(CALQUE_OSM, v).apply()

    /**
     * Les fournisseurs nationaux dont les chemins sont dessinés (clés du
     * manifeste : « ign », « atkis »…). Chacun a sa coche, comme sur le PC.
     * Sans préférence enregistrée, tous sont cochés ; l'ancien réglage unique
     * « calque_officiel » est repris une fois.
     */
    var calquesOfficiels: Set<String>
        get() {
            preferences.getStringSet(CALQUES_OFFICIELS, null)?.let { return it.toSet() }
            if (preferences.contains(CALQUE_OFFICIEL) && !preferences.getBoolean(CALQUE_OFFICIEL, true))
                return emptySet()
            return Fournisseurs.TOUS.map { it.cle }.toSet()
        }
        set(v) = preferences.edit().putStringSet(CALQUES_OFFICIELS, v).apply()

    fun calqueOfficiel(cle: String): Boolean = cle in calquesOfficiels

    fun changerCalqueOfficiel(cle: String, actif: Boolean) {
        calquesOfficiels = calquesOfficiels.toMutableSet().apply {
            if (actif) add(cle) else remove(cle)
        }
    }

    /** La légende des symboles, au bord droit de la carte ; décochée par défaut, comme sur le PC. */
    var legende: Boolean
        get() = preferences.getBoolean(LEGENDE, false)
        set(v) = preferences.edit().putBoolean(LEGENDE, v).apply()

    /** La courbe du dénivelé, au-dessus des boutons, comme le profil de la page. */
    var courbeDenivele: Boolean
        get() = preferences.getBoolean(COURBE_DENIVELE, true)
        set(v) = preferences.edit().putBoolean(COURBE_DENIVELE, v).apply()

    /** La distance minimale entre deux points d'une trace GPS, en mètres (Locus : 10). */
    var distanceMin: Double
        get() = preferences.getFloat(DISTANCE_MIN, 10f).toDouble()
        set(v) = preferences.edit().putFloat(DISTANCE_MIN, v.toFloat()).apply()

    /** La durée minimale entre deux points d'une trace GPS, en secondes (Locus : 10). */
    var dureeMin: Int
        get() = preferences.getInt(DUREE_MIN, 10)
        set(v) = preferences.edit().putInt(DUREE_MIN, v).apply()

    /** La déviation GPS maximale acceptée pour un point, en mètres (Locus : 100). */
    var precisionMax: Double
        get() = preferences.getFloat(PRECISION_MAX, 100f).toDouble()
        set(v) = preferences.edit().putFloat(PRECISION_MAX, v.toFloat()).apply()

    /** La dernière vue de la carte : latitude, longitude, zoom ; Garéoult au premier lancement. */
    var vue: Triple<Double, Double, Double>
        get() = preferences.getString(VUE, null)?.split(',')?.mapNotNull { it.toDoubleOrNull() }
            ?.takeIf { it.size == 3 }?.let { Triple(it[0], it[1], it[2]) } ?: Triple(43.458, 6.045, 13.0)
        set(v) = preferences.edit().putString(VUE, "${v.first},${v.second},${v.third}").apply()

    companion object {
        private const val PCS = "pcs"                               // ancienne liste des PC, effacée
        private const val FOND = "fond"
        private const val CLE_IGN = "cle_ign"
        private const val STRICT = "strict"
        private const val OFFICIELS = "officiels"
        private const val CALQUE_OSM = "calque_osm"
        private const val CALQUES_OFFICIELS = "calques_officiels"
        private const val CALQUE_OFFICIEL = "calque_officiel"       // ancien réglage unique, repris une fois
        private const val LEGENDE = "legende"
        private const val COURBE_DENIVELE = "courbe_denivele"
        private const val DISTANCE_MIN = "trace_distance_min"
        private const val DUREE_MIN = "trace_duree_min"
        private const val PRECISION_MAX = "trace_precision_max"
        private const val VUE = "vue"

        /**
         * Les profils BRouter des assets, recopiés à chaque démarrage là où
         * BRouter sait les lire (des fichiers) : une correction livrée avec
         * l'application s'applique aussitôt.
         */
        fun profils(context: Context): File {
            val racine = File(context.filesDir, "profils")
            for (genre in listOf("osm", "enrichi")) {
                val dossier = File(racine, genre).apply { mkdirs() }
                for (nom in context.assets.list("brouter/$genre") ?: emptyArray()) {
                    context.assets.open("brouter/$genre/$nom").use { entree ->
                        File(dossier, nom).outputStream().use { entree.copyTo(it) }
                    }
                }
            }
            return racine
        }
    }
}
