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

    /** Les sources dans l'ordre de préférence : GitHub d'abord, puis les PC. */
    fun sources(): List<Source> = listOf(Source.GITHUB) + pcs()

    private fun enregistrer(liste: List<Source>) {
        val a = JSONArray()
        liste.forEach { a.put(JSONObject().put("catalogue", it.catalogue).put("jeton", it.jeton)) }
        preferences.edit().putString(PCS, a.toString()).apply()
    }

    companion object {
        private const val PCS = "pcs"

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
