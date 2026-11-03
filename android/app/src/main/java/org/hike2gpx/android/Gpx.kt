package org.hike2gpx.android

import org.json.JSONArray

/** Le tracé GeoJSON [lon, lat, alt] en GPX 1.1, une trace d'un seul segment. */
object Gpx {
    fun ecrire(coordonnees: JSONArray, nom: String = "hike2gpx"): String {
        val gpx = StringBuilder("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n")
            .append("<gpx version=\"1.1\" creator=\"hike2gpx\" xmlns=\"http://www.topografix.com/GPX/1/1\">\n")
            .append("<trk><name>").append(nom.replace("&", "&amp;").replace("<", "&lt;")).append("</name><trkseg>\n")
        for (i in 0 until coordonnees.length()) {
            val p = coordonnees.getJSONArray(i)
            gpx.append("<trkpt lat=\"").append(p.getDouble(1)).append("\" lon=\"").append(p.getDouble(0)).append("\">")
            if (p.length() > 2) gpx.append("<ele>").append(p.getDouble(2)).append("</ele>")
            gpx.append("</trkpt>\n")
        }
        return gpx.append("</trkseg></trk></gpx>\n").toString()
    }
}
