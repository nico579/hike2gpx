package org.hike2gpx.android

import org.json.JSONArray
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/** Le tracé GeoJSON [lon, lat, alt] en GPX 1.1, une trace d'un seul segment. */
object Gpx {
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
     * aussi) : le GPX produit se relit dans les autres applications.
     */
    fun ecrireTrace(points: List<PointTrace>, nom: String = "hike2gpx"): String {
        val heure = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply {
            timeZone = TimeZone.getTimeZone("UTC")
        }
        val gpx = StringBuilder("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n")
            .append("<gpx version=\"1.1\" creator=\"hike2gpx\" xmlns=\"http://www.topografix.com/GPX/1/1\">\n")
            .append("<trk><name>").append(echapper(nom)).append("</name><trkseg>\n")
        for (p in points) {
            gpx.append("<trkpt lat=\"").append(p.lat).append("\" lon=\"").append(p.lon).append("\">")
            p.altitude?.let { gpx.append("<ele>").append(it).append("</ele>") }
            gpx.append("<time>").append(heure.format(Date(p.instant))).append("</time>")
            gpx.append("</trkpt>\n")
        }
        return gpx.append("</trkseg></trk></gpx>\n").toString()
    }

    private fun echapper(texte: String) = texte.replace("&", "&amp;").replace("<", "&lt;")
}
