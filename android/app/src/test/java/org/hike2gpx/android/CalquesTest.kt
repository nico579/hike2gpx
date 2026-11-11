package org.hike2gpx.android

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

/**
 * Les coches de superposition ne suivent pas les lots installés (un lot de
 * France reste installé en Suisse) : seule celle du lot qui couvre la vue est
 * proposée, et seulement pour le pays affiché. À Genève, un lot frontalier qui
 * contient l'IGN et swissTLM3D ne propose que swissTLM3D.
 */
class CalquesTest {

    @get:Rule val dossier = TemporaryFolder()

    private val racine get() = File(dossier.root, "hors-ligne")

    /** Un lot installé : son manifeste et ses tuiles vectorielles. */
    private fun lot(case: String, fournisseurs: List<String>, emprise: List<Int>, calques: Boolean = true) {
        val dossierLot = File(racine, case).apply { mkdirs() }
        if (calques) File(dossierLot, "calques.mbtiles").writeText("tuiles")
        File(dossierLot, "manifest.json").writeText(JSONObject()
            .put("format", 3).put("case", case).put("type", "enrichi")
            .put("fournisseurs", JSONArray(fournisseurs))
            .put("zone", JSONArray(emprise)).put("emprise_enrichie", JSONArray(emprise))
            .put("fichiers", JSONArray()).toString())
    }

    private fun zone(sud: Double, ouest: Double, nord: Double, est: Double) = Zone(sud, ouest, nord, est)

    private fun visibles(pays: String, sud: Double, ouest: Double, nord: Double, est: Double) =
        Calques(HorsLigne(dossier.root)).fournisseursVisibles(zone(sud, ouest, nord, est), pays)
            .map { it.cle }

    @Test fun la_coche_suit_le_lot_de_la_zone_affichee() {
        lot("E0_N45", listOf("ign"), listOf(48, 2, 49, 3))
        lot("E5_N45", listOf("swisstlm3d"), listOf(46, 6, 47, 7))

        assertEquals(listOf("ign"), visibles("fr", 48.8, 2.2, 48.9, 2.4))          // Paris
        assertEquals(listOf("swisstlm3d"), visibles("ch", 46.1, 6.0, 46.3, 6.3))   // Genève
    }

    @Test fun un_lot_frontalier_ne_propose_que_le_fournisseur_du_pays() {
        lot("E5_N45", listOf("ign", "swisstlm3d"), listOf(45, 5, 50, 10))

        assertEquals(listOf("ign"), visibles("fr", 48.6, 6.1, 48.7, 6.2))            // Nancy
        assertEquals(listOf("swisstlm3d"), visibles("ch", 46.1, 6.0, 46.3, 6.3))     // Genève
    }

    @Test fun la_coche_ne_suit_pas_un_lot_installe_hors_de_son_pays() {
        lot("E0_N45", listOf("ign"), listOf(48, 2, 49, 3))

        assertTrue("l'IGN ne sert pas en Suisse", visibles("ch", 48.8, 2.2, 48.9, 2.4).isEmpty())
    }

    @Test fun sans_lot_de_la_zone_il_ne_reste_que_osm() {
        lot("E0_N45", listOf("ign"), listOf(48, 2, 49, 3))
        assertTrue(visibles("fr", 41.8, 12.4, 42.0, 12.6).isEmpty())               // Rome
    }

    @Test fun un_lot_sans_tuiles_vectorielles_ne_propose_aucune_coche() {
        lot("E0_N45", listOf("ign"), listOf(48, 2, 49, 3), calques = false)
        assertTrue(visibles("fr", 48.8, 2.2, 48.9, 2.4).isEmpty())
    }
}
