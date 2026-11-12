package org.hike2gpx.android

import org.json.JSONObject
import org.w3c.dom.Element
import java.io.ByteArrayInputStream
import javax.xml.parsers.DocumentBuilderFactory
import kotlin.math.asin
import kotlin.math.cos
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Une trace importée d'un GPX ou d'un KML, comme sur la page du PC : ses
 * segments (latitude, longitude), sa couleur et son épaisseur quand le KML en
 * donne, et ses données (ExtendedData, en JSON quand elles viennent de gpx2elev).
 */
data class TraceImportee(
    val nom: String,
    val segments: List<List<Pair<Double, Double>>>,
    val couleur: Int? = null,
    val epaisseur: Float? = null,
    val infos: Map<String, String> = emptyMap(),
)

/**
 * Ce que gpx2dash range dans le nom d'une trace, « 2020-12-13_LA ROQUEBRUSSANNE_8.7KM_D+350M_2H18 » :
 * la date (aaaa-mm-jj), le lieu, la distance, le D+ et la durée. Un autre nom reste tel quel.
 */
data class NomTrace(val titre: String, val date: String? = null, val km: Double? = null,
                    val dplus: Int? = null, val minutes: Int? = null, val heure: String? = null)

object TracesImportees {
    private val NOM_GPX2DASH =
        Regex("""^(\d{4}-\d{2}-\d{2})_(?:(\d{1,2})-(\d{2})\s+)?(.+?)(?:_([\d.]+)km)?(?:_D\+(\d+)m)?(?:_(\d+)h(\d+))?$""", RegexOption.IGNORE_CASE)

    /** Les traces d'un fichier GPX ou KML ; une liste vide s'il n'en contient aucune. */
    fun lire(texte: String, nomFichier: String): List<TraceImportee> {
        val fabrique = DocumentBuilderFactory.newInstance().apply { isNamespaceAware = true }
        val document = fabrique.newDocumentBuilder().parse(ByteArrayInputStream(texte.toByteArray(Charsets.UTF_8)))
        val racine = document.documentElement
        return when (racine.localName) {
            "kml" -> lireKml(racine)
            "gpx" -> lireGpx(racine, nomFichier.substringBeforeLast('.'))
            else -> emptyList()
        }
    }

    private fun Element.tous(nom: String): List<Element> {
        val liste = getElementsByTagNameNS("*", nom)
        return List(liste.length) { liste.item(it) as Element }
    }

    private fun Element.enfant(nom: String): Element? {
        var n = firstChild
        while (n != null) {
            if (n is Element && n.localName == nom) return n
            n = n.nextSibling
        }
        return null
    }

    private fun lireGpx(racine: Element, nom: String): List<TraceImportee> {
        fun points(parent: Element, balise: String) = parent.tous(balise).mapNotNull { p ->
            val lat = p.getAttribute("lat").toDoubleOrNull()
            val lon = p.getAttribute("lon").toDoubleOrNull()
            if (lat == null || lon == null || kotlin.math.abs(lat) > 90 || kotlin.math.abs(lon) > 180) null else lat to lon
        }
        val segments = racine.tous("trkseg").map { points(it, "trkpt") } + racine.tous("rte").map { points(it, "rtept") }
        val utiles = segments.filter { it.size > 1 }
        return if (utiles.isEmpty()) emptyList() else listOf(TraceImportee(nom, utiles))
    }

    private fun lireKml(racine: Element): List<TraceImportee> {
        val styles = mutableMapOf<String, Pair<Int?, Float?>>()
        for (style in racine.tous("Style")) {
            val id = style.getAttribute("id").ifEmpty { null } ?: continue
            val ligne = style.tous("LineStyle").firstOrNull() ?: continue
            styles[id] = couleurKml(ligne.tous("color").firstOrNull()?.textContent) to
                ligne.tous("width").firstOrNull()?.textContent?.trim()?.toFloatOrNull()
        }
        return racine.tous("Placemark").mapNotNull { repere ->
            val segments = repere.tous("LineString").mapNotNull { ligne ->
                val brut = ligne.tous("coordinates").firstOrNull()?.textContent ?: return@mapNotNull null
                brut.trim().split(Regex("\\s+")).mapNotNull { triplet ->
                    val v = triplet.split(",")
                    val lon = v.getOrNull(0)?.toDoubleOrNull()
                    val lat = v.getOrNull(1)?.toDoubleOrNull()
                    if (lat == null || lon == null || kotlin.math.abs(lat) > 90 || kotlin.math.abs(lon) > 180) null else lat to lon
                }.takeIf { it.size > 1 }
            }
            if (segments.isEmpty()) return@mapNotNull null
            val infos = repere.tous("Data").associate { d ->
                d.getAttribute("name") to (d.tous("value").firstOrNull()?.textContent ?: "")
            }
            val style = styles[repere.enfant("styleUrl")?.textContent?.trim()?.removePrefix("#") ?: ""]
            TraceImportee(repere.enfant("name")?.textContent?.trim() ?: "", segments,
                style?.first, style?.second, infos)
        }
    }

    /** Une couleur KML (aabbggrr) en ARGB Android ; null si elle est illisible. */
    fun couleurKml(texte: String?): Int? {
        val t = texte?.trim() ?: return null
        if (!Regex("[0-9a-fA-F]{8}").matches(t)) return null
        val a = t.substring(0, 2); val b = t.substring(2, 4); val g = t.substring(4, 6); val r = t.substring(6, 8)
        return (a + r + g + b).toLong(16).toInt()
    }

    fun lireNom(nom: String): NomTrace {
        val m = NOM_GPX2DASH.matchEntire(nom) ?: return NomTrace(nom)
        val g = m.groupValues
        // Les traces récentes ajoutent l'heure de départ devant le lieu : « 2026-04-27_12-14 La Roquebrussanne_… ».
        return NomTrace(g[4].replace('_', ' '), g[1], g[5].toDoubleOrNull(), g[6].toIntOrNull(),
            if (g[7].isNotEmpty()) g[7].toInt() * 60 + g[8].toInt() else null,
            if (g[2].isNotEmpty()) "${g[2].toInt()} h ${g[3]}" else null)
    }

    /** Le dénivelé exact de gpx2elev (D+, D−) et son modèle, quand le KML les porte. */
    fun denivele(trace: TraceImportee): Triple<Int, Int, String>? = try {
        val d = JSONObject(trace.infos["denivele_exact"] ?: return null)
        val modele = trace.infos["modele"]?.let { runCatching { JSONObject("{\"m\":$it}").getString("m") }.getOrNull() }
        Triple(Math.round(d.getDouble("Dplus_m")).toInt(), Math.round(d.getDouble("Dmoins_m")).toInt(), modele ?: "gpx2elev")
    } catch (e: Exception) {
        null
    }

    /** La longueur des segments, en mètres (grand cercle). */
    fun longueur(segments: List<List<Pair<Double, Double>>>): Double = segments.sumOf { points ->
        points.zipWithNext().sumOf { (a, b) ->
            val p1 = Math.toRadians(a.first); val p2 = Math.toRadians(b.first)
            val dl = Math.toRadians(b.second - a.second)
            val h = sin((p2 - p1) / 2).pow(2) + cos(p1) * cos(p2) * sin(dl / 2).pow(2)
            2 * 6_371_008.8 * asin(sqrt(h))
        }
    }
}
