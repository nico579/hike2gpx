package org.hike2gpx.android

import java.net.Inet4Address
import java.net.InetAddress
import java.net.URI
import java.net.URLDecoder

/**
 * Une source de lots : un catalogue et, pour un PC, le jeton qui l'ouvre.
 *
 * GitHub est la source par défaut, toujours là. Un PC s'ajoute en lisant son
 * QR code, qui porte un lien hike2gpx://depot?url=<catalogue>&jeton=<jeton> ;
 * toutes les requêtes vers ce PC portent alors Authorization: Bearer <jeton>.
 */
data class Source(val catalogue: String, val jeton: String? = null) {
    val github: Boolean get() = jeton == null && catalogue == DEPOT_GITHUB

    val libelle: String get() = if (github) "GitHub" else "PC ${URI(catalogue).authority}"

    companion object {
        /** Le dépôt du serveur : une publication GitHub fixe, mise à jour sur place (depot.DEPOT). */
        const val DEPOT_GITHUB =
            "https://github.com/nico579/hike2gpx-bundles/releases/download/bundles/catalog.json"
        val GITHUB = Source(DEPOT_GITHUB)
    }
}

/** Le lien d'un QR code de PC : hike2gpx://depot?url=…&jeton=… */
object LienDepot {
    fun lire(lien: String): Source {
        val uri = try {
            URI(lien.trim())
        } catch (e: Exception) {
            throw ErreurDepot("Lien de dépôt illisible.", e)
        }
        if (uri.scheme != "hike2gpx" || uri.host != "depot" || uri.rawQuery == null)
            throw ErreurDepot("Ce n'est pas un lien de dépôt hike2gpx.")
        val parametres = uri.rawQuery.split('&').filter { '=' in it }.associate {
            URLDecoder.decode(it.substringBefore('='), "UTF-8") to URLDecoder.decode(it.substringAfter('='), "UTF-8")
        }
        val url = parametres["url"] ?: throw ErreurDepot("Le lien ne donne pas l'adresse du catalogue.")
        val jeton = parametres["jeton"]?.takeIf { it.isNotBlank() }
            ?: throw ErreurDepot("Le lien ne donne pas de jeton.")
        verifierAdresse(url)
        return Source(url, jeton)
    }

    /**
     * L'adresse du catalogue d'un PC. HTTPS partout ; HTTP seulement vers le
     * réseau local (adresse privée, nom sans domaine ou en .local), car le
     * jeton y circule en clair.
     */
    fun verifierAdresse(url: String) {
        val uri = try {
            URI(url)
        } catch (e: Exception) {
            throw ErreurDepot("Adresse de catalogue illisible : $url", e)
        }
        val hote = uri.host ?: throw ErreurDepot("Adresse de catalogue sans hôte : $url")
        when (uri.scheme) {
            "https" -> return
            "http" -> if (!local(hote)) throw ErreurDepot("Un catalogue en HTTP doit être sur le réseau local : $hote")
            else -> throw ErreurDepot("Adresse de catalogue non HTTP : $url")
        }
    }

    private val IPV4 = Regex("[0-9]{1,3}(\\.[0-9]{1,3}){3}")

    fun local(hote: String): Boolean {
        if (hote == "localhost" || hote.endsWith(".local") || ('.' !in hote && ':' !in hote)) return true
        if (!IPV4.matches(hote)) return false        // jamais de résolution DNS ici
        val adresse = InetAddress.getByName(hote) as Inet4Address
        return adresse.isSiteLocalAddress || adresse.isLinkLocalAddress || adresse.isLoopbackAddress
    }
}

/** Un lot proposé au téléchargement, avec la source qui le sert. */
data class Offre(val source: Source, val lot: Lot)

/**
 * Pour chaque case, le lot le plus récent parmi les catalogues lus, d'après
 * l'édition de son extrait OSM (sources.osm). Les catalogues viennent dans
 * l'ordre de préférence, GitHub d'abord : à égalité, ou sans date, le premier
 * l'emporte.
 */
fun choisir(catalogues: List<Pair<Source, Catalogue>>): List<Offre> {
    val choix = LinkedHashMap<String, Offre>()
    for ((source, catalogue) in catalogues) {
        for (lot in catalogue.lots) {
            val actuel = choix[lot.case]
            if (actuel == null || plusRecent(lot, actuel.lot)) choix[lot.case] = Offre(source, lot)
        }
    }
    return choix.values.sortedBy { it.lot.case }
}

/** Le lot a est-il d'une édition OSM strictement plus récente que b ? */
fun plusRecent(a: Lot, b: Lot): Boolean {
    val da = a.editionOsm ?: return false
    val db = b.editionOsm ?: return true
    return da.isAfter(db)
}
