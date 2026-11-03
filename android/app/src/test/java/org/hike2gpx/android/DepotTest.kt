package org.hike2gpx.android

import com.sun.net.httpserver.HttpServer
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.net.InetSocketAddress
import java.security.MessageDigest
import java.util.Collections

/**
 * Le téléchargement contre un vrai serveur HTTP local (celui du JDK) : reprise
 * par Range, contrôle SHA-256, jeton du PC.
 */
class DepotTest {
    @get:Rule val dossier = TemporaryFolder()

    private lateinit var serveur: HttpServer
    private val fichiers = mutableMapOf<String, ByteArray>()
    private val requetes = Collections.synchronizedList(mutableListOf<Map<String, String?>>())
    private var jetonExige: String? = null
    private var accepteRange = true
    private var couperUneFois = mutableSetOf<String>()

    private val base get() = "http://127.0.0.1:${serveur.address.port}"

    @Before fun demarrer() {
        serveur = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
        serveur.createContext("/") { e ->
            val chemin = e.requestURI.path
            requetes.add(mapOf("chemin" to chemin, "range" to e.requestHeaders.getFirst("Range"),
                "auth" to e.requestHeaders.getFirst("Authorization")))
            val contenu = fichiers[chemin]
            when {
                jetonExige != null && e.requestHeaders.getFirst("Authorization") != "Bearer $jetonExige" ->
                    e.sendResponseHeaders(401, -1)
                contenu == null -> e.sendResponseHeaders(404, -1)
                else -> {
                    val range = e.requestHeaders.getFirst("Range")
                    val debut = if (accepteRange && range != null) range.removePrefix("bytes=").removeSuffix("-").toInt() else 0
                    if (debut > 0) e.responseHeaders.add("Content-Range", "bytes $debut-${contenu.size - 1}/${contenu.size}")
                    e.sendResponseHeaders(if (debut > 0) 206 else 200, (contenu.size - debut).toLong())
                    if (couperUneFois.remove(chemin)) {
                        // Coupure : la moitié, puis la connexion tombe.
                        e.responseBody.write(contenu, debut, (contenu.size - debut) / 2)
                        e.responseBody.flush()
                        e.close()
                        return@createContext
                    }
                    e.responseBody.use { it.write(contenu, debut, contenu.size - debut) }
                }
            }
            e.close()
        }
        serveur.start()
    }

    @After fun arreter() = serveur.stop(0)

    private fun sha(b: ByteArray) = MessageDigest.getInstance("SHA-256").digest(b).joinToString("") { "%02x".format(it) }

    private fun publier(nom: String, contenu: ByteArray): Fichier {
        fichiers["/depot/E5_N40.$nom"] = contenu
        return Fichier(nom, contenu.size.toLong(), sha(contenu), "E5_N40.$nom")
    }

    private fun lot(vararg f: Fichier) = Lot("E5_N40", "enrichi", 3, listOf("ign"), null, null, emptyMap(),
        f.sumOf { it.octets }, f.toList())

    private val donnees = ByteArray(300_000) { (it * 31 % 251).toByte() }

    @Test fun empreinte_d_un_fichier() {
        val f = dossier.newFile().apply { writeText("abc") }
        assertEquals("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", empreinte(f))
    }

    @Test fun lit_le_catalogue() {
        fichiers["/depot/catalog.json"] = """{"format": 1, "lots": []}""".toByteArray()
        val c = Depot().lireCatalogue(Source("$base/depot/catalog.json"))
        assertTrue(c.lots.isEmpty())
    }

    @Test fun telecharge_et_verifie() {
        val lot = lot(publier("E5_N40.rd5", donnees), publier("manifest.json", "{}".toByteArray()))
        val travail = dossier.newFolder()
        var dernier = 0L
        Depot { }.telecharger(lot, Source("$base/depot/catalog.json"), travail, { faits, _ -> dernier = faits })
        assertArrayEquals(donnees, File(travail, "E5_N40.rd5").readBytes())
        assertEquals(lot.octets, dernier)
        assertTrue(requetes.all { it["range"] == null && it["auth"] == null })
    }

    @Test fun reprend_un_fichier_entame() {
        val lot = lot(publier("E5_N40.rd5", donnees))
        val travail = dossier.newFolder()
        File(travail, "E5_N40.rd5").writeBytes(donnees.copyOf(100_000))
        Depot { }.telecharger(lot, Source("$base/depot/catalog.json"), travail)
        assertArrayEquals(donnees, File(travail, "E5_N40.rd5").readBytes())
        assertEquals(listOf("bytes=100000-"), requetes.map { it["range"] })
    }

    @Test fun reprend_apres_une_coupure() {
        val lot = lot(publier("E5_N40.rd5", donnees))
        couperUneFois.add("/depot/E5_N40.E5_N40.rd5")
        val travail = dossier.newFolder()
        val pauses = mutableListOf<Long>()
        Depot { pauses.add(it) }.telecharger(lot, Source("$base/depot/catalog.json"), travail)
        assertArrayEquals(donnees, File(travail, "E5_N40.rd5").readBytes())
        assertEquals(2, requetes.size)
        assertNull(requetes[0]["range"])
        assertTrue(requetes[1]["range"]!!.startsWith("bytes="))
        assertEquals(1, pauses.size)
    }

    @Test fun serveur_sans_range_repart_de_zero() {
        accepteRange = false
        val lot = lot(publier("E5_N40.rd5", donnees))
        val travail = dossier.newFolder()
        File(travail, "E5_N40.rd5").writeBytes(donnees.copyOf(100_000))
        Depot { }.telecharger(lot, Source("$base/depot/catalog.json"), travail)
        assertArrayEquals(donnees, File(travail, "E5_N40.rd5").readBytes())
    }

    @Test fun debut_altere_refait_le_fichier() {
        val lot = lot(publier("E5_N40.rd5", donnees))
        val travail = dossier.newFolder()
        File(travail, "E5_N40.rd5").writeBytes(ByteArray(100_000))      // des zéros : faux
        Depot { }.telecharger(lot, Source("$base/depot/catalog.json"), travail)
        assertArrayEquals(donnees, File(travail, "E5_N40.rd5").readBytes())
        assertEquals(listOf("bytes=100000-", null), requetes.map { it["range"] })
    }

    @Test fun empreinte_fausse_echoue_apres_trois_essais() {
        val f = publier("E5_N40.rd5", donnees).copy(sha256 = "0".repeat(64))
        val travail = dossier.newFolder()
        try {
            Depot { }.telecharger(lot(f), Source("$base/depot/catalog.json"), travail)
            fail()
        } catch (e: ErreurDepot) {
            assertTrue(e.message!!.contains("altéré"))
        }
        assertEquals(3, requetes.size)
        assertFalse(File(travail, "E5_N40.rd5").exists())
    }

    @Test fun jeton_envoye_au_pc() {
        jetonExige = "s3cret"
        fichiers["/depot/catalog.json"] = """{"format": 1, "lots": []}""".toByteArray()
        val pc = Source("$base/depot/catalog.json", "s3cret")
        Depot().lireCatalogue(pc)
        val lot = lot(publier("E5_N40.rd5", donnees))
        Depot { }.telecharger(lot, pc, dossier.newFolder())
        assertTrue(requetes.all { it["auth"] == "Bearer s3cret" })
    }

    @Test fun jeton_refuse() {
        jetonExige = "bon"
        fichiers["/depot/catalog.json"] = """{"format": 1, "lots": []}""".toByteArray()
        try {
            Depot().lireCatalogue(Source("$base/depot/catalog.json", "mauvais"))
            fail()
        } catch (e: ErreurDepot) {
            assertTrue(e.message!!.contains("jeton"))
        }
    }

    @Test fun adresses_relatives_au_catalogue() {
        val depot = Depot()
        assertEquals("https://github.com/nico579/hike2gpx-bundles/releases/download/bundles/E5_N40.E5_N40.rd5",
            depot.adresse(Source.GITHUB, "E5_N40.E5_N40.rd5").toString())
        val pc = Source("http://192.168.1.10:8790/lots/catalog.json", "j")
        assertEquals("http://192.168.1.10:8790/lots/E5_N40/manifest.json", depot.adresse(pc, "E5_N40/manifest.json").toString())
        // Le jeton ne doit jamais partir ailleurs : un fichier hors de l'origine du PC est refusé.
        try {
            depot.adresse(pc, "http://ailleurs.example/x.rd5")
            fail()
        } catch (e: ErreurDepot) {
        }
        assertEquals("https://ailleurs.example/x.rd5", depot.adresse(Source.GITHUB, "https://ailleurs.example/x.rd5").toString())
    }
}
