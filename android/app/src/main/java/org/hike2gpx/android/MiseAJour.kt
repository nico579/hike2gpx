package org.hike2gpx.android

import android.content.Context
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.FileProvider
import org.json.JSONException
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean

/**
 * La mise à jour de l'application depuis les releases GitHub, sur le modèle
 * de gpxelev et blink2temp (update/ReleaseUpdates.kt) : la dernière release
 * publiée, son APK hike2gpx-android.apk téléchargé seulement depuis GitHub en
 * HTTPS, contrôlé par sa taille et son SHA-256 (le champ digest de l'API, ou
 * le fichier .sha256 publié à côté), puis par son paquet, sa version et sa
 * signature avant d'être confié à l'installateur d'Android.
 */
object MiseAJour {
    const val DEPOT = "https://github.com/nico579/hike2gpx"
    const val DERNIERE = "https://api.github.com/repos/nico579/hike2gpx/releases/latest"
    const val APK = "hike2gpx-android.apk"
    private const val APK_MAX = 64L * 1024 * 1024
    val HOTES = setOf("api.github.com", "github.com", "release-assets.githubusercontent.com",
        "objects.githubusercontent.com")

    /** 0.9.0 > 0.8.1 ; une version qui n'a pas la forme majeure.mineure.corrective est refusée. */
    fun version(texte: String): List<Int> {
        if (!Regex("v?(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)").matches(texte))
            throw ErreurMaj(R.string.maj_version_invalide)
        return texte.removePrefix("v").split('.').map { it.toInt() }
    }

    fun plusRecente(candidate: String, actuelle: String): Boolean {
        val a = version(candidate)
        val b = version(actuelle)
        return a.indices.firstOrNull { a[it] != b[it] }?.let { a[it] > b[it] } ?: false
    }

    /** La release plus récente que la version actuelle, ou null ; refuse toute réponse hors de la forme attendue. */
    fun lire(json: JSONObject, actuelle: String): Publication? {
        if (json.opt("draft") != false || json.opt("prerelease") != false) throw ErreurMaj(R.string.maj_reponse_invalide)
        val tag = json.optString("tag_name")
        if (!plusRecente(tag, actuelle)) return null
        val assets = json.optJSONArray("assets") ?: throw ErreurMaj(R.string.maj_reponse_invalide)
        val fichiers = (0 until assets.length()).mapNotNull { assets.optJSONObject(it) }
        val apk = fichiers.filter { it.optString("name") == APK }.singleOrNull() ?: throw ErreurMaj(R.string.maj_apk_absent)
        val url = "$DEPOT/releases/download/$tag/$APK"
        val octets = apk.optLong("size", -1)
        if (apk.optString("browser_download_url") != url || octets !in 1..APK_MAX ||
            (apk.opt("size") !is Int && apk.opt("size") !is Long)) throw ErreurMaj(R.string.maj_reponse_invalide)
        val digest = if (apk.isNull("digest")) null else apk.optString("digest")
        if (digest != null && !Regex("sha256:[0-9a-fA-F]{64}").matches(digest)) throw ErreurMaj(R.string.maj_empreinte_invalide)
        val empreinte = "$url.sha256"
        if (digest == null && fichiers.none { it.optString("name") == "$APK.sha256" && it.optString("browser_download_url") == empreinte })
            throw ErreurMaj(R.string.maj_empreinte_absente)
        return Publication(tag.removePrefix("v"), tag, url, octets, digest?.substring(7)?.lowercase(),
            if (digest == null) empreinte else null)
    }

    /** L'empreinte d'un fichier .sha256 au format de sha256sum : « <64 hexadécimaux>  hike2gpx-android.apk ». */
    fun empreinteDuFichier(texte: String): String {
        val valeurs = texte.lineSequence().mapNotNull { Regex("([0-9a-fA-F]{64}) [ *](.+)").matchEntire(it.trim()) }
            .filter { it.groupValues[2] == APK }.map { it.groupValues[1].lowercase() }.toList()
        return valeurs.singleOrNull() ?: throw ErreurMaj(R.string.maj_empreinte_absente)
    }

    @Suppress("DEPRECATION")
    private fun drapeaux() = if (Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES

    @Suppress("DEPRECATION")
    fun installee(context: Context): PackageInfo = context.packageManager.getPackageInfo(context.packageName, drapeaux())

    @Suppress("DEPRECATION")
    private fun signataires(info: PackageInfo): Set<String> {
        val signatures = if (Build.VERSION.SDK_INT >= 28) info.signingInfo?.apkContentsSigners else info.signatures
        return signatures?.map { hex(MessageDigest.getInstance("SHA-256").digest(it.toByteArray())) }?.toSet() ?: emptySet()
    }

    /** Même paquet, version annoncée et plus récente, même signature que l'application installée. */
    @Suppress("DEPRECATION")
    fun verifier(context: Context, apk: File, publication: Publication) {
        val candidate = context.packageManager.getPackageArchiveInfo(apk.absolutePath, drapeaux())
            ?: throw ErreurMaj(R.string.maj_apk_illisible)
        val actuelle = installee(context)
        val codeCandidat = if (Build.VERSION.SDK_INT >= 28) candidate.longVersionCode else candidate.versionCode.toLong()
        val codeActuel = if (Build.VERSION.SDK_INT >= 28) actuelle.longVersionCode else actuelle.versionCode.toLong()
        if (candidate.packageName != actuelle.packageName || candidate.versionName != publication.version || codeCandidat <= codeActuel)
            throw ErreurMaj(R.string.maj_autre_application)
        val attendus = signataires(actuelle)
        if (attendus.isEmpty() || signataires(candidate) != attendus) throw ErreurMaj(R.string.maj_signature)
    }

    /** Le dossier privé des APK téléchargés, le seul que partage le FileProvider (xml/maj_chemins). */
    fun dossier(context: Context) = File(context.cacheDir, "maj")

    fun uri(context: Context, apk: File) = FileProvider.getUriForFile(context, "${context.packageName}.maj", apk)

    fun hex(octets: ByteArray): String = octets.joinToString("") { "%02x".format(it) }
}

class ErreurMaj(texte: Int) : ErreurTexte(texte)

data class Publication(val version: String, val tag: String, val url: String, val octets: Long,
                       val sha256: String?, val urlEmpreinte: String?)

/** Le dialogue avec GitHub : adresses officielles en HTTPS, redirections, taille et délais bornés. */
class ClientMaj(private val ouvrir: (URL) -> HttpURLConnection = { it.openConnection() as HttpURLConnection }) {
    private val annule = AtomicBoolean(false)

    fun annuler() = annule.set(true)

    private fun connexion(adresse: String): HttpURLConnection {
        var url = URL(adresse)
        repeat(6) {
            if (annule.get()) throw Abandon()
            if (url.protocol != "https" || url.host !in MiseAJour.HOTES || url.userInfo != null || url.port !in listOf(-1, 443))
                throw ErreurMaj(R.string.maj_adresse_invalide)
            val c = ouvrir(url)
            try {
                c.connectTimeout = 15_000
                c.readTimeout = 30_000
                c.instanceFollowRedirects = false
                c.setRequestProperty("User-Agent", Depot.AGENT)
                c.setRequestProperty("Accept-Encoding", "identity")
                c.setRequestProperty("Accept", if (adresse == MiseAJour.DERNIERE) "application/vnd.github+json" else "application/octet-stream")
                val code = c.responseCode
                if (code in listOf(301, 302, 303, 307, 308)) {
                    url = URL(url, c.getHeaderField("Location") ?: throw ErreurMaj(R.string.maj_adresse_invalide))
                    c.disconnect()
                } else {
                    if (code != 200) throw ErreurMaj(when (code) {
                        403, 429 -> R.string.maj_limite
                        404 -> if (adresse == MiseAJour.DERNIERE) R.string.maj_aucune_release else R.string.maj_indisponible
                        else -> R.string.maj_indisponible
                    })
                    return c
                }
            } catch (e: Exception) {
                c.disconnect()
                throw e
            }
        }
        throw ErreurMaj(R.string.maj_adresse_invalide)
    }

    private fun octets(adresse: String, limite: Int): ByteArray {
        val c = connexion(adresse)
        try {
            c.inputStream.use { entree ->
                val sortie = ByteArrayOutputStream()
                val bloc = ByteArray(65536)
                while (true) {
                    if (annule.get()) throw Abandon()
                    val n = entree.read(bloc)
                    if (n < 0) break
                    if (sortie.size() + n > limite) throw ErreurMaj(R.string.maj_reponse_invalide)
                    sortie.write(bloc, 0, n)
                }
                return sortie.toByteArray()
            }
        } finally {
            c.disconnect()
        }
    }

    /** La release plus récente que la version actuelle, ou null si l'application est à jour. */
    fun verifier(actuelle: String): Publication? {
        val json = try {
            JSONObject(octets(MiseAJour.DERNIERE, 1 shl 20).toString(Charsets.UTF_8))
        } catch (e: JSONException) {
            throw ErreurMaj(R.string.maj_reponse_invalide)
        }
        return MiseAJour.lire(json, actuelle)
    }

    /** L'APK dans dossier, contrôlé par sa taille et son SHA-256 ; suivi(reçus, total). */
    fun telecharger(publication: Publication, dossier: File, suivi: (Long, Long) -> Unit = { _, _ -> },
                    continuer: () -> Boolean = { true }): File {
        if (!dossier.isDirectory && !dossier.mkdirs()) throw IOException("dossier $dossier")
        val attendue = publication.sha256 ?: MiseAJour.empreinteDuFichier(
            octets(publication.urlEmpreinte ?: throw ErreurMaj(R.string.maj_empreinte_absente), 65536).toString(Charsets.UTF_8))
        val provisoire = File(dossier, "telechargement-${UUID.randomUUID()}.part")
        val final = File(dossier, MiseAJour.APK)
        val c = connexion(publication.url)
        try {
            val h = MessageDigest.getInstance("SHA-256")
            var recus = 0L
            provisoire.outputStream().use { sortie ->
                c.inputStream.use { entree ->
                    val bloc = ByteArray(65536)
                    while (true) {
                        if (annule.get() || !continuer()) throw Abandon()
                        val n = entree.read(bloc)
                        if (n < 0) break
                        recus += n
                        if (recus > publication.octets) throw ErreurMaj(R.string.maj_corrompu)
                        sortie.write(bloc, 0, n)
                        h.update(bloc, 0, n)
                        suivi(recus, publication.octets)
                    }
                }
            }
            if (recus != publication.octets || MiseAJour.hex(h.digest()) != attendue) throw ErreurMaj(R.string.maj_corrompu)
            Files.move(provisoire.toPath(), final.toPath(), StandardCopyOption.REPLACE_EXISTING)
            return final
        } finally {
            c.disconnect()
            provisoire.delete()
        }
    }
}
