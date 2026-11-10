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
 * proposée, à côté de la coche OSM toujours présente.
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

    private fun visibles(sud: Double, ouest: Double, nord: Double, est: Double) =
        Calques(HorsLigne(dossier.root)).fournisseursVisibles(zone(sud, ouest, nord, est))
            .map { it.cle }

    @Test fun la_coche_suit_le_lot_de_la_zone_affichee() {
        lot("E0_N45", listOf("ign"), listOf(48, 2, 49, 3))
        lot("E5_N45", listOf("swisstlm3d"), listOf(46, 6, 47, 7))

        assertEquals(listOf("ign"), visibles(48.8, 2.2, 48.9, 2.4))          // Paris
        assertEquals(listOf("swisstlm3d"), visibles(46.1, 6.0, 46.3, 6.3))   // Genève
    }

    @Test fun sans_lot_de_la_zone_il_ne_reste_que_osm() {
        lot("E0_N45", listOf("ign"), listOf(48, 2, 49, 3))
        assertTrue(visibles(41.8, 12.4, 42.0, 12.6).isEmpty())               // Rome
    }

    @Test fun un_lot_sans_tuiles_vectorielles_ne_propose_aucune_coche() {
        lot("E0_N45", listOf("ign"), listOf(48, 2, 49, 3), calques = false)
        assertTrue(visibles(48.8, 2.2, 48.9, 2.4).isEmpty())
    }
}
