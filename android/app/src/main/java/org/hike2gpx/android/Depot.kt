package org.hike2gpx.android

import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import java.security.MessageDigest

class Abandon : Exception("Téléchargement interrompu.")

/** Le SHA-256 d'un fichier, en hexadécimal (lot.empreinte). */
fun empreinte(fichier: File): String {
    val h = MessageDigest.getInstance("SHA-256")
    fichier.inputStream().use { entree ->
        val bloc = ByteArray(1 shl 20)
        while (true) {
            val n = entree.read(bloc)
            if (n < 0) break
            h.update(bloc, 0, n)
        }
    }
    return h.digest().joinToString("") { "%02x".format(it) }
}

/**
 * La lecture d'un dépôt : son catalogue, puis les fichiers d'un lot, repris
 * là où ils se sont arrêtés (en-tête Range) et contrôlés par leur SHA-256.
 * C'est depot.lire_catalogue et depot.telecharger du PC, en Kotlin.
 *
 * Vers un PC, le jeton ne part qu'à l'origine de son catalogue (même schéma,
 * hôte et port) et les redirections ne sont pas suivies : un fichier ailleurs
 * ne le recevrait pas.
 */
class Depot(private val pause: (Long) -> Unit = { Thread.sleep(it) }) {

    fun lireCatalogue(source: Source): Catalogue {
        val connexion = try {
            ouvrir(URL(source.catalogue), source, 0)
        } catch (e: IOException) {
            throw ErreurDepot("Catalogue de ${source.libelle} injoignable (${e.message}).", e)
        }
        try {
            val code = connexion.responseCode
            if (code == 401 || code == 403) throw ErreurDepot("${source.libelle} refuse le jeton : rescannez son QR code.")
            if (code != 200) throw ErreurDepot("Catalogue de ${source.libelle} : réponse HTTP $code.")
            return Catalogue.lire(connexion.inputStream.use { String(it.readBytes(), Charsets.UTF_8) })
        } catch (e: IOException) {
            throw ErreurDepot("Catalogue de ${source.libelle} illisible (${e.message}).", e)
        } finally {
            connexion.disconnect()
        }
    }

    /**
     * Les fichiers d'un lot dans travail, sous leur nom de lot (manifest.json,
     * E5_N40.rd5…), prêts pour HorsLigne.installer, qui les revérifie contre le
     * manifeste. suivi(faits, total) en octets ; continuer() faux interrompt.
     */
    fun telecharger(lot: Lot, source: Source, travail: File,
                    suivi: (Long, Long) -> Unit = { _, _ -> }, continuer: () -> Boolean = { true }): File {
        travail.mkdirs()
        val total = lot.fichiers.sumOf { it.octets }
        val deja = lot.fichiers.sumOf { f -> File(travail, f.nom).let { if (it.exists()) minOf(it.length(), f.octets) else 0L } }
        val manque = total - deja
        if (travail.usableSpace < manque + MARGE_DISQUE)
            throw ErreurDepot("Place insuffisante : il faut ${manque / 1_000_000 + 1} Mo.")
        var recus = 0L
        val avancer = { n: Long -> recus += n; suivi(recus, total) }
        for (f in lot.fichiers) {
            if (!continuer()) throw Abandon()
            val cible = File(travail, Catalogue.nomSur(f.nom))
            recus += if (cible.exists()) minOf(cible.length(), f.octets) else 0
            fichier(adresse(source, f.url), source, cible, f, avancer, continuer)
        }
        return travail
    }

    /** L'adresse d'un fichier, relative à celle du catalogue ; vers un PC, à la même origine. */
    fun adresse(source: Source, relative: String): URL {
        val base = URI(source.catalogue)
        val cible = base.resolve(relative.replace(" ", "%20"))
        if (source.jeton != null && !memeOrigine(base, cible))
            throw ErreurDepot("Fichier hors du dépôt du PC : $cible")
        return cible.toURL()
    }

    private fun fichier(url: URL, source: Source, cible: File, f: Fichier,
                        avancer: (Long) -> Unit, continuer: () -> Boolean) {
        repeat(ESSAIS) { essai ->
            val deja = if (cible.exists()) cible.length() else 0L
            if (deja < f.octets) {
                try {
                    recevoir(url, source, cible, deja, avancer, continuer)
                } catch (e: IOException) {          // coupure : l'essai suivant reprend
                    pause(2_000L * (essai + 1))
                    return@repeat
                }
                if (cible.length() < f.octets) {    // coupure sans erreur, flux fini trop tôt : de même
                    pause(2_000L * (essai + 1))
                    return@repeat
                }
            }
            if (cible.length() == f.octets && empreinte(cible) == f.sha256) return
            avancer(-cible.length())
            cible.delete()                          // contenu faux : on repart de zéro
        }
        throw ErreurDepot("${cible.name} : téléchargement impossible ou altéré.")
    }

    private fun recevoir(url: URL, source: Source, cible: File, deja: Long,
                         avancer: (Long) -> Unit, continuer: () -> Boolean) {
        val connexion = ouvrir(url, source, deja)
        try {
            val code = connexion.responseCode
            when {
                code == 401 || code == 403 -> throw ErreurDepot("${source.libelle} refuse le jeton : rescannez son QR code.")
                code == 416 -> return                  // déjà complet (ou trop long) : l'empreinte tranche
                code in 400..499 -> throw ErreurDepot("${cible.name} : réponse HTTP $code.")
                code != 200 && code != 206 -> throw IOException("réponse HTTP $code")
            }
            // Une reprise n'est acceptée que si le serveur repart bien de là où l'on s'est arrêté.
            val reprise = deja > 0 && code == 206 &&
                connexion.getHeaderField("Content-Range")?.startsWith("bytes $deja-") == true
            if (!reprise) avancer(-deja)
            connexion.inputStream.use { entree ->
                FileOutputStream(cible, reprise).use { sortie ->
                    val bloc = ByteArray(BLOC)
                    while (true) {
                        val n = entree.read(bloc)
                        if (n < 0) break
                        if (!continuer()) throw Abandon()
                        sortie.write(bloc, 0, n)
                        avancer(n.toLong())
                    }
                }
            }
        } finally {
            connexion.disconnect()
        }
    }

    private fun ouvrir(url: URL, source: Source, debut: Long): HttpURLConnection {
        val connexion = url.openConnection() as HttpURLConnection
        connexion.connectTimeout = 30_000
        connexion.readTimeout = 60_000
        connexion.setRequestProperty("User-Agent", AGENT)
        // Pas de compression transparente : elle fausserait tailles et reprises.
        connexion.setRequestProperty("Accept-Encoding", "identity")
        if (source.jeton != null) {
            connexion.instanceFollowRedirects = false
            if (memeOrigine(URI(source.catalogue), url.toURI()))
                connexion.setRequestProperty("Authorization", "Bearer ${source.jeton}")
        }
        if (debut > 0) connexion.setRequestProperty("Range", "bytes=$debut-")
        return connexion
    }

    companion object {
        const val AGENT = "hike2gpx-android/0.2"
        const val ESSAIS = 3
        const val BLOC = 1 shl 16
        const val MARGE_DISQUE = 50L shl 20

        fun memeOrigine(a: URI, b: URI): Boolean =
            a.scheme.equals(b.scheme, true) && a.host.equals(b.host, true) && port(a) == port(b)

        private fun port(u: URI): Int = if (u.port != -1) u.port else if (u.scheme.equals("https", true)) 443 else 80
    }
}
