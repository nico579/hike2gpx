package org.hike2gpx.android

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * Ce que l'application garde d'une session à l'autre : les PC ajoutés par QR
 * code. GitHub, source par défaut, n'y figure pas : il est toujours là.
 */
class Reglages(context: Context) {
    private val preferences = context.getSharedPreferences("hike2gpx", Context.MODE_PRIVATE)

    fun pcs(): List<Source> {
        val a = JSONArray(preferences.getString(PCS, "[]"))
        return List(a.length()) { a.getJSONObject(it) }.map { Source(it.getString("catalogue"), it.getString("jeton")) }
    }

    /** Un PC déjà connu (même catalogue) reçoit son nouveau jeton. */
    fun ajouterPc(source: Source) = enregistrer(pcs().filter { it.catalogue != source.catalogue } + source)

    fun oublierPc(source: Source) = enregistrer(pcs().filter { it.catalogue != source.catalogue })

    /** Le fond affiché : « osm », « topo », ou la source d'un fond hors ligne (« scan25 »…). */
    var fond: String
        get() = preferences.getString(FOND, "osm") ?: "osm"
        set(v) = preferences.edit().putString(FOND, v).apply()

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

    /** La légende des symboles de la carte, sous le bandeau d'état. */
    var legende: Boolean
        get() = preferences.getBoolean(LEGENDE, true)
        set(v) = preferences.edit().putBoolean(LEGENDE, v).apply()

    /** La courbe du dénivelé, au-dessus des boutons, comme le profil de la page. */
    var courbeDenivele: Boolean
        get() = preferences.getBoolean(COURBE_DENIVELE, true)
        set(v) = preferences.edit().putBoolean(COURBE_DENIVELE, v).apply()

    /** La dernière vue de la carte : latitude, longitude, zoom ; Garéoult au premier lancement. */
    var vue: Triple<Double, Double, Double>
        get() = preferences.getString(VUE, null)?.split(',')?.mapNotNull { it.toDoubleOrNull() }
            ?.takeIf { it.size == 3 }?.let { Triple(it[0], it[1], it[2]) } ?: Triple(43.458, 6.045, 13.0)
        set(v) = preferences.edit().putString(VUE, "${v.first},${v.second},${v.third}").apply()

    private fun enregistrer(liste: List<Source>) {
        val a = JSONArray()
        liste.forEach { a.put(JSONObject().put("catalogue", it.catalogue).put("jeton", it.jeton)) }
        preferences.edit().putString(PCS, a.toString()).apply()
    }

    companion object {
        private const val PCS = "pcs"
        private const val FOND = "fond"
        private const val STRICT = "strict"
        private const val OFFICIELS = "officiels"
        private const val CALQUE_OSM = "calque_osm"
        private const val CALQUES_OFFICIELS = "calques_officiels"
        private const val CALQUE_OFFICIEL = "calque_officiel"       // ancien réglage unique, repris une fois
        private const val LEGENDE = "legende"
        private const val COURBE_DENIVELE = "courbe_denivele"
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
