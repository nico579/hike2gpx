package org.hike2gpx.android

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * La position approximative du téléphone d'après son adresse IP, pour le tout
 * premier lancement : la carte s'ouvre alors sur sa ville plutôt que sur un
 * point fixe. Le service (ipapi.co, en HTTPS, sans clé) reçoit l'adresse IP ;
 * il ne sert qu'une fois, tant qu'aucune vue n'est enregistrée.
 */
object PositionIp {
    const val ADRESSE = "https://ipapi.co/json/"

    /** La position et la ville d'une réponse d'ipapi.co ; null si elle n'en donne pas. */
    fun lire(json: String): Triple<Double, Double, String>? = try {
        val o = JSONObject(json)
        val lat = o.getDouble("latitude")
        val lon = o.getDouble("longitude")
        if (lat !in -85.0..85.0 || lon !in -180.0..180.0 || (lat == 0.0 && lon == 0.0)) null
        else Triple(lat, lon, o.optString("city", ""))
    } catch (e: Exception) {
        null
    }

    /** Interroge le service ; null sans réseau, sur un refus ou après 5 s. */
    fun demander(): Triple<Double, Double, String>? = try {
        val connexion = URL(ADRESSE).openConnection() as HttpURLConnection
        connexion.connectTimeout = 5_000
        connexion.readTimeout = 5_000
        connexion.setRequestProperty("User-Agent", "hike2gpx")
        try {
            if (connexion.responseCode != 200) null
            else lire(connexion.inputStream.bufferedReader().use { it.readText() })
        } finally {
            connexion.disconnect()
        }
    } catch (e: Exception) {
        null
    }
}
