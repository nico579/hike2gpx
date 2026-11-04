package org.hike2gpx.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

class AutomatiqueTest {
    @get:Rule val dossier = TemporaryFolder()

    /** Un lot enrichi de la case, son emprise enrichie couvrant toute la case. */
    private fun lot(case: String, boite: List<Double>, osm: String) = Lot(case, "enrichi", 3, listOf("bdtopo"), boite, boite,
        mapOf("osm" to osm), 1, emptyList())

    private val e5n40 = listOf(40.0, 5.0, 45.0, 10.0)
    private val e0n40 = listOf(40.0, 0.0, 45.0, 5.0)
    private val gareoult = Zone(43.45, 6.03, 43.47, 6.06)

    @Test fun le_lot_de_la_case_du_parcours_quand_il_manque() {
        val offres = listOf(Offre(Source.GITHUB, lot("E0_N40", e0n40, "2026-11-01")),
            Offre(Source.GITHUB, lot("E5_N40", e5n40, "2026-11-01")))
        val choix = lotsATelecharger(offres, emptyList(), gareoult, emptySet())
        assertEquals(listOf("E5_N40"), choix.map { it.lot.case })
    }

    @Test fun rien_si_le_lot_installe_est_a_jour_et_un_plus_recent_le_remplace() {
        val installe = lot("E5_N40", e5n40, "2026-11-01")
        val memeEdition = listOf(Offre(Source.GITHUB, lot("E5_N40", e5n40, "2026-11-01")))
        assertTrue(lotsATelecharger(memeEdition, listOf(installe), gareoult, emptySet()).isEmpty())
        val plusRecent = listOf(Offre(Source.GITHUB, lot("E5_N40", e5n40, "2026-11-08")))
        assertEquals(1, lotsATelecharger(plusRecent, listOf(installe), gareoult, emptySet()).size)
    }

    @Test fun une_case_exclue_ne_revient_pas() {
        val offres = listOf(Offre(Source.GITHUB, lot("E5_N40", e5n40, "2026-11-01")))
        assertTrue(lotsATelecharger(offres, emptyList(), gareoult, setOf("E5_N40")).isEmpty())
    }

    @Test fun un_parcours_a_cheval_prend_les_deux_cases() {
        val offres = listOf(Offre(Source.GITHUB, lot("E0_N40", e0n40, "2026-11-01")),
            Offre(Source.GITHUB, lot("E5_N40", e5n40, "2026-11-01")))
        val frontiere = Zone(43.0, 4.9, 43.1, 5.1)
        assertEquals(listOf("E0_N40", "E5_N40"), lotsATelecharger(offres, emptyList(), frontiere, emptySet()).map { it.lot.case })
        assertFalse(Zone(45.1, 6.0, 45.2, 6.1).touche(e5n40))
    }

    private fun fond(nom: String) = Fond(nom, e5n40, "[6,13]", Fonds.source(nom), 10, "0".repeat(64), "fonds/$nom.mbtiles")

    @Test fun la_source_d_un_fond_se_lit_dans_son_nom() {
        assertEquals("scan25", Fonds.source("E5_N40-scan25"))
        assertEquals("plan", Fonds.source("E5_N40-plan-vue-3fa2c1"))
        assertEquals("bizarre", Fonds.source("bizarre"))
        assertEquals("SCAN 25 (IGN)", Fonds.titre("scan25"))
    }

    @Test fun les_fonds_des_pc_qui_manquent_une_fois_chacun() {
        val pc1 = Source("http://192.168.1.20/depot/catalog.json", "a")
        val pc2 = Source("http://192.168.1.21/depot/catalog.json", "b")
        val proposes = fondsProposes(listOf(
            Source.GITHUB to Catalogue("", emptyList(), emptyList()),
            pc1 to Catalogue("", emptyList(), listOf(fond("E5_N40-scan25"), fond("E5_N45-scan25"))),
            pc2 to Catalogue("", emptyList(), listOf(fond("E5_N40-scan25"), fond("E5_N40-plan"))),
        ), installes = setOf("E5_N45-scan25"))
        assertEquals(listOf("E5_N40-plan" to pc2, "E5_N40-scan25" to pc1), proposes.map { it.second.nom to it.first })
    }

    @Test fun vider_retire_lots_et_fonds_et_dit_ce_qui_est_libere() {
        val hl = HorsLigne(dossier.root)
        File(hl.segments, "E5_N40.rd5").apply { parentFile!!.mkdirs(); writeBytes(ByteArray(100)) }
        File(hl.racine, "E5_N40/manifest.json").apply { parentFile!!.mkdirs(); writeText("{}") }
        File(Fonds(hl.racine).dossier, "E5_N40-plan.mbtiles").apply { parentFile!!.mkdirs(); writeBytes(ByteArray(50)) }
        assertEquals(152L, hl.vider())
        assertFalse(hl.racine.exists())
        assertTrue(hl.lots().isEmpty())
        assertEquals(0L, hl.vider())
    }

    @Test fun les_fonds_installes_se_groupent_par_source() {
        val fonds = Fonds(dossier.root)
        val recu = dossier.newFile("E5_N40-scan25.mbtiles")
        fonds.installer(recu, fond("E5_N40-scan25"))
        fonds.installer(dossier.newFile("x"), fond("E5_N45-scan25"))
        fonds.installer(dossier.newFile("y"), fond("E5_N40-plan-vue-3fa2c1"))
        File(fonds.dossier, "note.txt").writeText("pas un fond")
        assertFalse(recu.exists())
        assertEquals(mapOf("plan" to listOf("E5_N40-plan-vue-3fa2c1"), "scan25" to listOf("E5_N40-scan25", "E5_N45-scan25")),
            fonds.parSource().mapValues { (_, f) -> f.map { it.nameWithoutExtension } }.toSortedMap())
    }
}
