package org.hike2gpx.android

import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.util.Locale

/**
 * Le MNT IGN LiDAR HD, la première source de gpx2elev : l'altimétrie de la
 * Géoplateforme répond pour des lots de 5000 points, sans clé, avec la même
 * requête que gpx2elev.providers.PublicModels.ign. Hors de la couverture (hors
 * de France, ou en mer), l'IGN renvoie −99999 et Denivele passe à Mapterhorn.
 *
 * Il faut le réseau : sans lui, la source échoue et Mapterhorn prend le relais
 * avec son cache.
 */
class IgnLidar : SourceRelief {
    override val nom = NOM

    override fun altitudes(lats: DoubleArray, lons: DoubleArray): DoubleArray? {
        val resultat = DoubleArray(lats.size)
        var debut = 0
        while (debut < lats.size) {
            val fin = minOf(debut + LOT, lats.size)
            val valeurs = analyser(demander(requete(lats, lons, debut, fin)), fin - debut) ?: return null
            valeurs.copyInto(resultat, debut)
            debut = fin
        }
        return resultat
    }

    private fun demander(corps: String): String {
        val connexion = URL(ADRESSE).openConnection() as HttpURLConnection
        try {
            connexion.connectTimeout = 10_000
            connexion.readTimeout = 15_000
            connexion.requestMethod = "POST"
            connexion.doOutput = true
            connexion.setRequestProperty("Content-Type", "application/json")
            connexion.setRequestProperty("User-Agent", "${Depot.AGENT} (relief IGN)")
            connexion.outputStream.use { it.write(corps.toByteArray(Charsets.UTF_8)) }
            val code = connexion.responseCode
            if (code != 200) throw ErreurDenivele("IGN LiDAR HD : réponse HTTP $code")
            return connexion.inputStream.use { it.readBytes() }.toString(Charsets.UTF_8)
        } catch (e: IOException) {
            throw ErreurDenivele("IGN LiDAR HD injoignable (${e.message})")
        } finally {
            connexion.disconnect()
        }
    }

    companion object {
        const val NOM = "IGN LiDAR HD"
        const val LOT = 5000
        const val ADRESSE = "https://data.geopf.fr/altimetrie/1.0/calcul/alti/rest/elevation.json"

        /** Le corps JSON de gpx2elev pour les points [debut, fin[. */
        fun requete(lats: DoubleArray, lons: DoubleArray, debut: Int, fin: Int): String =
            JSONObject()
                .put("resource", "ign_lidar_hd_mnt_mono_wld")
                .put("delimiter", "|")
                .put("zonly", "true")
                .put("lat", (debut until fin).joinToString("|") { String.format(Locale.ROOT, "%.7f", lats[it]) })
                .put("lon", (debut until fin).joinToString("|") { String.format(Locale.ROOT, "%.7f", lons[it]) })
                .toString()

        /**
         * Les altitudes d'une réponse, nombres seuls (zonly) ou objets {z: …}
         * comme les lit gpx2elev ; null si la réponse n'a pas le bon compte.
         * Les « sans donnée » restent tels quels : Denivele les écarte.
         */
        fun analyser(texte: String, attendu: Int): DoubleArray? {
            val elevations: JSONArray = JSONObject(texte).optJSONArray("elevations") ?: return null
            if (elevations.length() != attendu) return null
            return DoubleArray(attendu) { i ->
                when (val v = elevations.get(i)) {
                    is JSONObject -> v.optDouble("z", Double.NaN)
                    is Number -> v.toDouble()
                    else -> Double.NaN
                }
            }
        }
    }
}
