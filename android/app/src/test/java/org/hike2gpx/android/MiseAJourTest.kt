package org.hike2gpx.android

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.net.URL

class MiseAJourTest {
    private val sha = "cfcfee5fc181434f730d673fe4d4891361086d192e436bf09c054ca72509503a"

    /** La réponse de l'API pour une release, à la forme de celle de v0.9.0. */
    private fun release(tag: String = "v0.9.1", digest: String? = "sha256:$sha", avecEmpreinte: Boolean = true,
                        url: String = "https://github.com/nico579/hike2gpx/releases/download/$tag/hike2gpx-android.apk",
                        draft: Boolean = false): JSONObject {
        val assets = JSONArray()
        assets.put(JSONObject().put("name", "hike2gpx-android.apk").put("size", 1757967)
            .put("digest", digest ?: JSONObject.NULL).put("browser_download_url", url))
        if (avecEmpreinte) assets.put(JSONObject().put("name", "hike2gpx-android.apk.sha256").put("size", 87)
            .put("browser_download_url", "https://github.com/nico579/hike2gpx/releases/download/$tag/hike2gpx-android.apk.sha256"))
        assets.put(JSONObject().put("name", "hike2gpx-windows-x86_64.zip").put("size", 1))
        return JSONObject().put("tag_name", tag).put("draft", draft).put("prerelease", false).put("assets", assets)
    }

    private fun refuse(texte: Int, bloc: () -> Unit) {
        try {
            bloc(); fail()
        } catch (e: ErreurMaj) {
            assertEquals(texte, e.texte)
        }
    }

    @Test fun les_versions_se_comparent_nombre_par_nombre() {
        assertTrue(MiseAJour.plusRecente("v0.10.0", "0.9.1"))
        assertTrue(MiseAJour.plusRecente("1.0.0", "0.99.99"))
        assertFalse(MiseAJour.plusRecente("v0.9.0", "0.9.0"))
        assertFalse(MiseAJour.plusRecente("0.8.1", "0.9.0"))
        refuse(R.string.maj_version_invalide) { MiseAJour.version("0.9") }
        refuse(R.string.maj_version_invalide) { MiseAJour.version("0.9.0-rc1") }
    }

    @Test fun une_release_plus_recente_avec_son_empreinte() {
        val p = MiseAJour.lire(release(), "0.9.0")!!
        assertEquals("0.9.1", p.version)
        assertEquals("https://github.com/nico579/hike2gpx/releases/download/v0.9.1/hike2gpx-android.apk", p.url)
        assertEquals(1757967L, p.octets)
        assertEquals(sha, p.sha256)
        assertNull(p.urlEmpreinte)
        assertNull("à jour : rien à proposer", MiseAJour.lire(release("v0.9.0"), "0.9.0"))
    }

    @Test fun sans_digest_le_fichier_sha256_fait_foi() {
        val p = MiseAJour.lire(release(digest = null), "0.9.0")!!
        assertNull(p.sha256)
        assertEquals("https://github.com/nico579/hike2gpx/releases/download/v0.9.1/hike2gpx-android.apk.sha256", p.urlEmpreinte)
        refuse(R.string.maj_empreinte_absente) { MiseAJour.lire(release(digest = null, avecEmpreinte = false), "0.9.0") }
    }

    @Test fun une_reponse_hors_de_la_forme_attendue_est_refusee() {
        refuse(R.string.maj_reponse_invalide) { MiseAJour.lire(release(draft = true), "0.9.0") }
        refuse(R.string.maj_reponse_invalide) { MiseAJour.lire(release(url = "https://exemple.org/hike2gpx-android.apk"), "0.9.0") }
        refuse(R.string.maj_empreinte_invalide) { MiseAJour.lire(release(digest = "md5:abc"), "0.9.0") }
        val sansApk = release().apply { put("assets", JSONArray()) }
        refuse(R.string.maj_apk_absent) { MiseAJour.lire(sansApk, "0.9.0") }
    }

    @Test fun le_fichier_sha256_au_format_de_sha256sum() {
        assertEquals(sha, MiseAJour.empreinteDuFichier("$sha  hike2gpx-android.apk\n"))
        assertEquals(sha, MiseAJour.empreinteDuFichier("${sha.uppercase()} *hike2gpx-android.apk"))
        refuse(R.string.maj_empreinte_absente) { MiseAJour.empreinteDuFichier("$sha  autre.apk") }
    }

    @Test fun seul_github_en_https_est_contacte() {
        var ouvertes = 0
        val client = ClientMaj { url: URL -> ouvertes++; url.openConnection() as java.net.HttpURLConnection }
        val publication = Publication("0.9.1", "v0.9.1", "http://github.com/nico579/hike2gpx/x.apk", 10, sha, null)
        refuse(R.string.maj_adresse_invalide) { client.telecharger(publication, createTempDir()) }
        refuse(R.string.maj_adresse_invalide) {
            client.telecharger(publication.copy(url = "https://exemple.org/hike2gpx-android.apk"), createTempDir())
        }
        assertEquals("aucune connexion ouverte hors de GitHub", 0, ouvertes)
    }
}
