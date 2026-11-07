package org.hike2gpx.android

import org.json.JSONArray
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/** Le tracé GeoJSON [lon, lat, alt] en GPX 1.1, une trace d'un seul segment. */
object Gpx {
    private val POINT = Regex("<trkpt\\b([^>]*)>(.*?)</trkpt>", RegexOption.DOT_MATCHES_ALL)
    private val LAT = Regex("\\blat=\"([^\"]+)\"")
    private val LON = Regex("\\blon=\"([^\"]+)\"")
    private val ELE = Regex("<ele>([^<]+)</ele>")
    private val TIME = Regex("<time>([^<]+)</time>")

    fun ecrire(coordonnees: JSONArray, nom: String = "hike2gpx"): String {
        val gpx = StringBuilder("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n")
            .append("<gpx version=\"1.1\" creator=\"hike2gpx\" xmlns=\"http://www.topografix.com/GPX/1/1\">\n")
            .append("<trk><name>").append(echapper(nom)).append("</name><trkseg>\n")
        for (i in 0 until coordonnees.length()) {
            val p = coordonnees.getJSONArray(i)
            gpx.append("<trkpt lat=\"").append(p.getDouble(1)).append("\" lon=\"").append(p.getDouble(0)).append("\">")
            if (p.length() > 2) gpx.append("<ele>").append(p.getDouble(2)).append("</ele>")
            gpx.append("</trkpt>\n")
        }
        return gpx.append("</trkseg></trk></gpx>\n").toString()
    }

    /**
     * Une trace enregistrée, avec l'heure de chaque point (Locus Map les garde
     * aussi) : le GPX produit se relit dans les autres applications. [description]
     * porte le dénivelé gpx2elev quand il a été calculé à l'export.
     */
    fun ecrireTrace(points: List<PointTrace>, nom: String = "hike2gpx",
                    description: String? = null): String {
        val heure = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply {
            timeZone = TimeZone.getTimeZone("UTC")
        }
        val gpx = StringBuilder("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n")
            .append("<gpx version=\"1.1\" creator=\"hike2gpx\" xmlns=\"http://www.topografix.com/GPX/1/1\">\n")
            .append("<trk><name>").append(echapper(nom)).append("</name>")
        if (description != null) gpx.append("<desc>").append(echapper(description)).append("</desc>")
        gpx.append("<trkseg>\n")
        for (p in points) {
            gpx.append("<trkpt lat=\"").append(p.lat).append("\" lon=\"").append(p.lon).append("\">")
            p.altitude?.let { gpx.append("<ele>").append(it).append("</ele>") }
            gpx.append("<time>").append(heure.format(Date(p.instant))).append("</time>")
            gpx.append("</trkpt>\n")
        }
        return gpx.append("</trkseg></trk></gpx>\n").toString()
    }

    /** Relit un GPX de l'historique : latitude, longitude, altitude et heure des points. */
    fun lireTrace(texte: String): List<PointTrace> {
        val heure = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply {
            timeZone = TimeZone.getTimeZone("UTC")
        }
        return POINT.findAll(texte).mapNotNull { point ->
            val attributs = point.groupValues[1]
            val corps = point.groupValues[2]
            val lat = LAT.find(attributs)?.groupValues?.get(1)?.toDoubleOrNull() ?: return@mapNotNull null
            val lon = LON.find(attributs)?.groupValues?.get(1)?.toDoubleOrNull() ?: return@mapNotNull null
            val altitude = ELE.find(corps)?.groupValues?.get(1)?.toDoubleOrNull()
            val instant = TIME.find(corps)?.groupValues?.get(1)?.let {
                try {
                    heure.parse(it)?.time
                } catch (e: Exception) {
                    null
                }
            } ?: 0L
            PointTrace(lat, lon, altitude, instant)
        }.toList()
    }

    /**
     * Remplace l'altitude GPS par celle de gpx2elev et calcule le profil.
     * [relief] peut être le cache seul (trace hors réseau) ou le modèle complet ;
     * une tuile absente du cache lève [ErreurDenivele], et l'appelant garde
     * alors le GPX d'origine.
     */
    fun enrichir(points: List<PointTrace>, relief: ModeleTerrain): Pair<List<PointTrace>, ProfilAltimetrique> {
        if (points.size < 2) throw ErreurDenivele("tracé trop court")
        val coordonnees = points.map { doubleArrayOf(it.lon, it.lat) }
        val profil = Denivele.calculer(coordonnees, relief)
        val enrichis = points.map { p ->
            val altitude = relief.altitude(p.lat, p.lon)
            if (altitude != null) p.copy(altitude = altitude) else p
        }
        return enrichis to profil
    }

    private fun echapper(texte: String) = texte
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
}
