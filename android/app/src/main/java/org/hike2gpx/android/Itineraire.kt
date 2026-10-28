package org.hike2gpx.android

import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

data class Resultat(val lot: Lot, val feature: JSONObject, val franchissements: List<Franchissement>) {
    val coordonnees: JSONArray get() = feature.getJSONObject("geometry").getJSONArray("coordinates")
}

/**
 * Le calcul hors ligne d'un parcours, comme application.itineraire sur le PC
 * quand un lot couvre la zone : franchissements de la zone en coupes, nouvel
 * essai sur une zone élargie si le tracé en sort, puis un dernier contrôle,
 * indépendant de BRouter, qu'aucune coupe interdite n'est traversée.
 */
class Itineraire(private val horsLigne: HorsLigne, private val routeur: Routeur) {

    fun calculer(points: List<Point>, strict: Boolean, officiels: Boolean, memoireMo: Int): Resultat {
        var zone = Zone.autour(points)
        repeat(ELARGISSEMENTS) {
            val lot = horsLigne.lotCouvrant(zone)
                ?: throw ErreurCalcul("Aucun lot installé ne couvre ce parcours : téléchargez la case qui le contient.")
            val liste = horsLigne.franchissements(lot, zone)
            val feature = routeur.calculer(horsLigne.segmentsDe(lot), !lot.osm, points,
                HorsLigne.polylines(liste, strict), officiels, memoireMo)
            val coords = feature.getJSONObject("geometry").getJSONArray("coordinates")
            val etendue = etendue(coords)
            if (contient(zone, etendue)) {
                val traverse = traverses(coords, liste, strict)
                if (traverse != null) {
                    val mot = if (traverse.statut == "blocked") "bloquant" else "à vérifier, en mode strict"
                    throw ErreurCalcul("Itinéraire refusé : le tracé passe un franchissement $mot.")
                }
                return Resultat(lot, feature, liste)
            }
            zone = union(zone, Zone.autour(listOf(Point(etendue.sud, etendue.ouest), Point(etendue.nord, etendue.est)), 0.1))
        }
        throw ErreurCalcul("Le tracé sort sans cesse de la zone examinée : rapprochez les points.")
    }

    companion object {
        const val ELARGISSEMENTS = 3

        fun etendue(coords: JSONArray): Zone {
            var s = 90.0; var o = 180.0; var n = -90.0; var e = -180.0
            for (i in 0 until coords.length()) {
                val p = coords.getJSONArray(i)
                val lon = p.getDouble(0); val lat = p.getDouble(1)
                s = min(s, lat); o = min(o, lon); n = max(n, lat); e = max(e, lon)
            }
            return Zone(s, o, n, e)
        }

        fun contient(zone: Zone, autre: Zone, marge: Double = 0.002): Boolean =
            zone.sud + marge <= autre.sud && zone.ouest + marge <= autre.ouest &&
                autre.nord <= zone.nord - marge && autre.est <= zone.est - marge

        fun union(a: Zone, b: Zone) = Zone(min(a.sud, b.sud), min(a.ouest, b.ouest), max(a.nord, b.nord), max(a.est, b.est))

        /** Le premier franchissement interdit dont une coupe croise le tracé, ou null. */
        fun traverses(coords: JSONArray, liste: List<Franchissement>, strict: Boolean): Franchissement? {
            val trace = List(coords.length()) { coords.getJSONArray(it).let { p -> doubleArrayOf(p.getDouble(0), p.getDouble(1)) } }
            return liste.firstOrNull { f ->
                (f.statut == "blocked" || strict) && f.coupes.any { coupe ->
                    coupe.size >= 2 && (1 until trace.size).any { k -> croise(trace[k - 1], trace[k], coupe[0], coupe[1]) }
                }
            }
        }

        private fun vectoriel(a: DoubleArray, b: DoubleArray, c: DoubleArray) =
            (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

        fun croise(a: DoubleArray, b: DoubleArray, c: DoubleArray, d: DoubleArray): Boolean {
            val abc = vectoriel(a, b, c); val abd = vectoriel(a, b, d)
            val cda = vectoriel(c, d, a); val cdb = vectoriel(c, d, b)
            if (abc * abd < 0 && cda * cdb < 0) return true
            return touche(a, b, c, abc) || touche(a, b, d, abd) || touche(c, d, a, cda) || touche(c, d, b, cdb)
        }

        private fun touche(a: DoubleArray, b: DoubleArray, p: DoubleArray, cote: Double) =
            abs(cote) < 1e-13 && p[0] >= min(a[0], b[0]) - 1e-9 && p[0] <= max(a[0], b[0]) + 1e-9 &&
                p[1] >= min(a[1], b[1]) - 1e-9 && p[1] <= max(a[1], b[1]) + 1e-9
    }
}
