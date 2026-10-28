package org.hike2gpx.android

import com.google.gson.stream.JsonReader
import com.google.gson.stream.JsonToken
import org.json.JSONObject
import java.io.File
import java.io.InputStreamReader
import java.util.Locale
import java.util.zip.GZIPInputStream
import kotlin.math.cos
import kotlin.math.max

data class Point(val lat: Double, val lon: Double)

/** Une zone [sud, ouest, nord, est] en degrés. */
data class Zone(val sud: Double, val ouest: Double, val nord: Double, val est: Double) {
    fun dans(boite: List<Double>): Boolean =
        boite[0] <= sud && boite[1] <= ouest && nord <= boite[2] && est <= boite[3]

    companion object {
        private const val MARGE_DEG = 0.01           // environ 1 km autour des points
        private const val MARGE_RELATIVE = 0.25

        /** La zone d'un parcours, marges comprises (application.zone_autour). */
        fun autour(points: List<Point>, margeRelative: Double = MARGE_RELATIVE): Zone {
            val lats = points.map { it.lat }
            val lons = points.map { it.lon }
            val margeLat = max(MARGE_DEG, (lats.max() - lats.min()) * margeRelative)
            val margeLon = max(MARGE_DEG / max(.2, cos(Math.toRadians(lats.average()))),
                (lons.max() - lons.min()) * margeRelative)
            return Zone(lats.min() - margeLat, lons.min() - margeLon, lats.max() + margeLat, lons.max() + margeLon)
        }
    }
}

/** Un franchissement du lot : sa position, son statut et les coupes données à BRouter. */
data class Franchissement(val lat: Double, val lon: Double, val statut: String, val coupes: List<List<DoubleArray>>)

class ErreurLot(message: String) : Exception(message)

/**
 * Les lots installés pour le calcul sans réseau, rangés comme sur le PC
 * (hors_ligne.HorsLigne) :
 *
 *   hors-ligne/segments/E5_N40.rd5        RD5 des lots enrichis
 *   hors-ligne/segments-osm/E5_N40.rd5    RD5 officielles des lots OSM
 *   hors-ligne/E5_N40/manifest.json, franchissements.json.gz, calques.mbtiles
 *
 * Règle unique : un parcours dont la zone tient dans un lot se calcule sur ce
 * lot seul.
 */
class HorsLigne(dossier: File) {
    val racine = File(dossier, "hors-ligne")
    val segments = File(racine, "segments")
    val segmentsOsm = File(racine, "segments-osm")

    fun segmentsDe(lot: Lot): File = if (lot.osm) segmentsOsm else segments

    /** Les lots installés, d'après leur manifeste. */
    fun lots(): List<Lot> =
        (racine.listFiles() ?: emptyArray()).filter { it.isDirectory && !it.name.startsWith(".") }
            .sortedBy { it.name }
            .mapNotNull { d ->
                val m = File(d, "manifest.json")
                if (!m.isFile) null else try {
                    Catalogue.lot(JSONObject(m.readText()), avecUrl = false)
                } catch (e: Exception) {
                    null                            // un manifeste abîmé n'empêche pas les autres
                }
            }

    /**
     * Installe le lot du dossier source après vérification de chaque fichier
     * contre son manifeste ; remplace un lot plus ancien de la même case. Les
     * fichiers sont déplacés, non copiés : un lot pèse des centaines de Mo.
     */
    fun installer(source: File): Lot {
        val json = try {
            JSONObject(File(source, "manifest.json").readText())
        } catch (e: Exception) {
            throw ErreurLot("Manifeste illisible : ${e.message}")
        }
        val format = json.optInt("format", -1)
        if (format !in FORMATS_LUS) throw ErreurLot("Format de lot $format inconnu (attendu : ${FORMATS_LUS.last()}).")
        val lot = try {
            Catalogue.lot(json, avecUrl = false)
        } catch (e: Exception) {
            throw ErreurLot("Manifeste invalide : ${e.message}")
        }
        for (f in lot.fichiers) {
            val chemin = File(source, f.nom)
            if (!chemin.isFile || chemin.length() != f.octets) throw ErreurLot("${f.nom} manquant ou de taille inattendue.")
            if (empreinte(chemin) != f.sha256) throw ErreurLot("${f.nom} ne correspond pas à son empreinte SHA-256.")
        }
        val rd5 = "${lot.case}.rd5"
        if (lot.fichiers.none { it.nom == rd5 }) throw ErreurLot("Le lot ne contient pas $rd5.")
        // Rangé à côté, puis remplacement : un lot à moitié rangé n'est jamais lu.
        val dossierSegments = segmentsDe(lot).apply { mkdirs() }
        val provisoire = File(racine, ".${lot.case}.part")
        provisoire.deleteRecursively()
        provisoire.mkdirs()
        for (f in lot.fichiers) if (f.nom != rd5) deplacer(File(source, f.nom), File(provisoire, f.nom))
        deplacer(File(source, "manifest.json"), File(provisoire, "manifest.json"))
        val rd5Provisoire = File(dossierSegments, ".$rd5.part")
        deplacer(File(source, rd5), rd5Provisoire)
        val final = File(racine, lot.case)
        final.deleteRecursively()
        if (!provisoire.renameTo(final)) throw ErreurLot("Impossible de ranger le lot ${lot.case}.")
        deplacer(rd5Provisoire, File(dossierSegments, rd5))
        // Une RD5 de l'autre genre (lot OSM remplacé par un lot enrichi) ne doit plus servir.
        File(if (lot.osm) segments else segmentsOsm, rd5).delete()
        return lot
    }

    /** Le lot installé qui couvre toute la zone ; à égalité, l'enrichi d'abord (lot_couvrant). */
    fun lotCouvrant(zone: Zone): Lot? =
        lots().filter { lot ->
            val c = lot.couverture
            c != null && File(segmentsDe(lot), "${lot.case}.rd5").isFile && zone.dans(c)
        }.minByOrNull { if (it.osm) 1 else 0 }

    /** Les franchissements du lot qui tombent dans la zone, lus au fil du fichier. */
    fun franchissements(lot: Lot, zone: Zone): List<Franchissement> =
        GZIPInputStream(File(File(racine, lot.case), "franchissements.json.gz").inputStream()).use {
            lireFranchissements(InputStreamReader(it, Charsets.UTF_8), zone)
        }

    companion object {
        val FORMATS_LUS = listOf(2, 3)

        private fun deplacer(de: File, vers: File) {
            vers.delete()
            if (!de.renameTo(vers)) {
                de.copyTo(vers, overwrite = true)
                de.delete()
            }
        }

        /**
         * Lecture en flux : le fichier d'une case entière décompressé pèse des
         * dizaines de Mo, on n'en garde que la zone du parcours.
         */
        fun lireFranchissements(lecteur: java.io.Reader, zone: Zone): List<Franchissement> {
            val resultat = mutableListOf<Franchissement>()
            JsonReader(lecteur).use { r ->
                r.beginArray()
                while (r.hasNext()) {
                    var lat = Double.NaN
                    var lon = Double.NaN
                    var statut = ""
                    val coupes = mutableListOf<List<DoubleArray>>()
                    r.beginObject()
                    while (r.hasNext()) {
                        when (r.nextName()) {
                            "lat" -> lat = r.nextDouble()
                            "lon" -> lon = r.nextDouble()
                            "statut" -> statut = r.nextString()
                            "coupes" -> {
                                r.beginArray()
                                while (r.hasNext()) {
                                    val coupe = mutableListOf<DoubleArray>()
                                    r.beginArray()
                                    while (r.hasNext()) {
                                        r.beginArray()
                                        val p = DoubleArray(2) { r.nextDouble() }
                                        while (r.peek() != JsonToken.END_ARRAY) r.skipValue()
                                        r.endArray()
                                        coupe.add(p)
                                    }
                                    r.endArray()
                                    coupes.add(coupe)
                                }
                                r.endArray()
                            }
                            else -> r.skipValue()
                        }
                    }
                    r.endObject()
                    if (lat in zone.sud..zone.nord && lon in zone.ouest..zone.est)
                        resultat.add(Franchissement(lat, lon, statut, coupes))
                }
                r.endArray()
            }
            return resultat
        }

        /** Coût d'un franchissement « à vérifier » (brouter.POIDS_A_VERIFIER). */
        const val POIDS_A_VERIFIER = 300

        /**
         * Le paramètre polylines de BRouter (brouter.requete) : une coupe par
         * ligne, [lon, lat] ; sans poids, elle interdit le tronçon, avec un poids
         * elle le rend coûteux. BRouter garde le coût de la dernière coupe qui
         * croise un segment : les interdites passent donc en dernier.
         */
        fun polylines(franchissements: List<Franchissement>, strict: Boolean, poids: Int = POIDS_A_VERIFIER): String {
            val lignes = mutableListOf<String>()
            for (interdite in listOf(false, true)) {
                for (f in franchissements) {
                    if ((f.statut == "blocked" || strict) != interdite) continue
                    for (coupe in f.coupes) {
                        val valeurs = coupe.flatMap { p -> p.map { String.format(Locale.US, "%.7f", it) } }
                        lignes.add((if (interdite) valeurs else valeurs + poids.toString()).joinToString(","))
                    }
                }
            }
            return lignes.joinToString("|")
        }
    }
}
