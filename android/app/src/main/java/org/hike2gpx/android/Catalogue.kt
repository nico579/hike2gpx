package org.hike2gpx.android

import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset

/**
 * Le catalogue d'un dépôt de lots, tel que l'écrit depot.ecrire_catalogue côté
 * Python : le même format, qu'il vienne de GitHub ou d'un PC.
 *
 *   {"format": 1, "genere": "…", "lots": [{"case": "E5_N40", "type": "enrichi", …,
 *     "fichiers": [{"nom": "E5_N40.rd5", "octets": …, "sha256": "…", "url": "E5_N40.E5_N40.rd5"}]}],
 *    "fonds": [{"nom", "zone", "zoom", "source", "octets", "sha256", "url"}],
 *    "cartes": [{"nom", "zone", "zoom", "source", "octets", "sha256", "url"}]}
 *
 * Les adresses des fichiers sont relatives à celle du catalogue. Les listes
 * « fonds » (MBTiles d'un PC) et « cartes » (cartes vectorielles Mapsforge du
 * même PC, en .map) sont facultatives et de même forme.
 */
class ErreurDepot(texte: Int, args: List<Any> = emptyList(), cause: Throwable? = null) :
    ErreurTexte(texte, args, cause)

data class Fichier(val nom: String, val octets: Long, val sha256: String, val url: String)

/** Un lot de case : la même description dans le catalogue et dans le manifeste installé. */
data class Lot(
    val case: String,
    val type: String,
    val format: Int?,
    val fournisseurs: List<String>,
    val zone: List<Double>?,
    val empriseEnrichie: List<Double>?,
    val sources: Map<String, String>,
    val octets: Long,
    val fichiers: List<Fichier>,
) {
    val osm: Boolean get() = type == "osm"

    /** Ce que le lot couvre seul (hors_ligne.lot_couvrant) : l'emprise enrichie
     *  d'un lot enrichi, la zone d'un lot OSM ; [sud, ouest, nord, est]. */
    val couverture: List<Double>? get() = if (osm) zone else empriseEnrichie

    /** L'édition de l'extrait OSM, qui date le lot. */
    val editionOsm: Instant? get() = date(sources["osm"])
}

data class Fond(
    val nom: String,
    val zone: List<Double>?,
    val zoom: String,
    val source: String,
    val octets: Long,
    val sha256: String,
    val url: String,
    /** « map » pour une carte vectorielle Mapsforge, null pour un MBTiles d'images. */
    val format: String? = null,
) {
    /** Le suffixe du fichier installé, celui de l'URL du catalogue. */
    val extension: String get() = if (format == "map") ".map" else ".mbtiles"
}

data class Catalogue(val genere: String, val lots: List<Lot>, val fonds: List<Fond>,
                     val cartes: List<Fond> = emptyList()) {
    companion object {
        const val FORMAT = 1
        private val CASE = Regex("[EW][0-9]{1,3}_[NS][0-9]{1,2}")
        private val SHA256 = Regex("[0-9a-f]{64}")

        /** Le catalogue, vérifié dans sa forme (depot.lire_catalogue). */
        fun lire(texte: String): Catalogue {
            try {
                val json = JSONObject(texte)
                if (json.optInt("format", -1) != FORMAT || json.optJSONArray("lots") == null)
                    throw ErreurDepot(R.string.err_catalogue_format)
                val lots = json.getJSONArray("lots").objets().map { lot(it, avecUrl = true) }
                val fonds = json.optJSONArray("fonds")?.objets()?.map { fond(it, null) } ?: emptyList()
                val cartes = json.optJSONArray("cartes")?.objets()?.map { fond(it, "map") } ?: emptyList()
                return Catalogue(json.optString("genere"), lots, fonds, cartes)
            } catch (e: ErreurDepot) {
                throw e
            } catch (e: Exception) {
                throw ErreurDepot(R.string.err_catalogue_illisible, listOf(e.message ?: e.toString()), e)
            }
        }

        /** Un lot du catalogue, ou le manifeste d'un lot installé (sans adresses). */
        fun lot(json: JSONObject, avecUrl: Boolean): Lot {
            val case = json.getString("case")
            if (!CASE.matches(case)) throw ErreurDepot(R.string.err_case_invalide, listOf(case))
            val fichiers = json.getJSONArray("fichiers").objets().map { fichier(it, avecUrl) }
            val sources = json.optJSONObject("sources")
            return Lot(
                case = case,
                type = json.optString("type", "enrichi"),
                format = if (json.has("format") && !json.isNull("format")) json.getInt("format") else null,
                fournisseurs = json.optJSONArray("fournisseurs")?.let { a -> List(a.length()) { a.getString(it) } }
                    ?: emptyList(),
                zone = boite(json.optJSONArray("zone")),
                empriseEnrichie = boite(json.optJSONArray("emprise_enrichie")),
                sources = sources?.keys()?.asSequence()?.associateWith { sources.get(it).toString() } ?: emptyMap(),
                octets = json.optLong("octets", fichiers.sumOf { it.octets }),
                fichiers = fichiers,
            )
        }

        private fun fichier(json: JSONObject, avecUrl: Boolean): Fichier {
            val sha = json.getString("sha256")
            if (!SHA256.matches(sha)) throw ErreurDepot(R.string.err_sha256, listOf(sha))
            val octets = json.getLong("octets")
            if (octets < 0) throw ErreurDepot(R.string.err_taille, listOf(octets))
            return Fichier(nomSur(json.getString("nom")), octets, sha, if (avecUrl) json.getString("url") else "")
        }

        /** Un fond ou une carte : la clé du catalogue dit le format, absent des entrées. */
        private fun fond(json: JSONObject, format: String?): Fond {
            val sha = json.getString("sha256")
            if (!SHA256.matches(sha)) throw ErreurDepot(R.string.err_sha256, listOf(sha))
            return Fond(nomSur(json.getString("nom")), boite(json.optJSONArray("zone")), json.opt("zoom")?.toString() ?: "",
                json.optString("source"), json.getLong("octets"), sha, json.getString("url"), format)
        }

        /** Jamais de chemin venu du catalogue : le seul nom du fichier. */
        fun nomSur(nom: String): String {
            val seul = nom.substringAfterLast('/').substringAfterLast('\\')
            if (seul.isEmpty() || seul == "." || seul == "..") throw ErreurDepot(R.string.err_nom_fichier, listOf(nom))
            return seul
        }

        private fun boite(a: JSONArray?): List<Double>? =
            if (a == null || a.length() != 4) null else List(4) { a.getDouble(it) }

        private fun JSONArray.objets(): List<JSONObject> = List(length()) { getJSONObject(it) }
    }
}

/** Une date ISO 8601, à la seconde ou au jour ; null si elle manque ou ne se lit pas. */
fun date(texte: String?): Instant? {
    if (texte.isNullOrBlank()) return null
    return try {
        Instant.parse(texte)
    } catch (e: Exception) {
        try {
            LocalDate.parse(texte.take(10)).atStartOfDay().toInstant(ZoneOffset.UTC)
        } catch (e: Exception) {
            null
        }
    }
}
