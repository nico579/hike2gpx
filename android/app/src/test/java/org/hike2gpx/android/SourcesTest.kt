package org.hike2gpx.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

class SourcesTest {
    @Test fun lit_le_qr_d_un_pc() {
        val s = LienDepot.lire("hike2gpx://depot?url=http%3A%2F%2F192.168.1.20%3A8790%2Fdepot%2Fcatalog.json&jeton=Ab-_9%2B")
        assertEquals("http://192.168.1.20:8790/depot/catalog.json", s.catalogue)
        assertEquals("Ab-_9+", s.jeton)
        assertFalse(s.github)
        assertEquals("PC 192.168.1.20:8790", s.libelle)
    }

    @Test fun refuse_un_lien_incomplet_ou_etranger() {
        val mauvais = listOf(
            "https://depot?url=x&jeton=j",                                       // pas le bon schéma
            "hike2gpx://autre?url=http%3A%2F%2F192.168.1.2%2Fc.json&jeton=j",    // pas le bon hôte
            "hike2gpx://depot?url=http%3A%2F%2F192.168.1.2%2Fc.json",            // sans jeton
            "hike2gpx://depot?jeton=j",                                          // sans adresse
            "hike2gpx://depot?url=ftp%3A%2F%2F192.168.1.2%2Fc.json&jeton=j",     // ni HTTP ni HTTPS
            "hike2gpx://depot?url=http%3A%2F%2Fexemple.org%2Fc.json&jeton=j",    // HTTP hors du réseau local
            "hike2gpx://depot?url=http%3A%2F%2F8.8.8.8%2Fc.json&jeton=j",
        )
        for (lien in mauvais) {
            try {
                LienDepot.lire(lien); fail(lien)
            } catch (e: ErreurDepot) {
            }
        }
    }

    @Test fun https_partout_http_en_local() {
        LienDepot.verifierAdresse("https://pc.exemple.org/catalog.json")
        for (hote in listOf("10.0.0.5", "172.16.3.4", "192.168.0.10", "169.254.1.1", "127.0.0.1", "monpc", "monpc.local"))
            assertTrue(hote, LienDepot.local(hote))
        for (hote in listOf("172.32.0.1", "8.8.8.8", "exemple.org"))
            assertFalse(hote, LienDepot.local(hote))
    }

    private fun lot(case: String, osm: String?) = Lot(case, "enrichi", 3, emptyList(), null, null,
        if (osm == null) emptyMap() else mapOf("osm" to osm), 1, emptyList())

    private val pc = Source("http://192.168.1.20/catalog.json", "j")

    @Test fun la_source_la_plus_recente_par_case() {
        val github = Catalogue("", listOf(lot("E5_N40", "2026-10-26T21:24:46Z"), lot("E5_N45", "2026-10-26T21:00:00Z")), emptyList())
        val local = Catalogue("", listOf(lot("E5_N40", "2026-10-27T08:00:00Z"), lot("E5_N45", "2026-10-20T00:00:00Z"),
            lot("E0_N45", "2026-10-01")), emptyList())
        val choix = choisir(listOf(Source.GITHUB to github, pc to local)).associate { it.lot.case to it.source }
        assertEquals(pc, choix["E5_N40"])            // le PC a un extrait plus récent
        assertEquals(Source.GITHUB, choix["E5_N45"])
        assertEquals(pc, choix["E0_N45"])            // seul le PC l'a
    }

    @Test fun a_egalite_ou_sans_date_github_reste() {
        val github = Catalogue("", listOf(lot("E5_N40", "2026-10-26T21:24:46Z"), lot("E5_N45", null)), emptyList())
        val local = Catalogue("", listOf(lot("E5_N40", "2026-10-26T21:24:46Z"), lot("E5_N45", null)), emptyList())
        val choix = choisir(listOf(Source.GITHUB to github, pc to local))
        assertTrue(choix.all { it.source == Source.GITHUB })
        // Un lot daté l'emporte sur un lot sans date.
        val date = Catalogue("", listOf(lot("E5_N45", "2026-01-01")), emptyList())
        assertEquals(pc, choisir(listOf(Source.GITHUB to github, pc to date)).single { it.lot.case == "E5_N45" }.source)
    }
}
