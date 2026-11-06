package org.hike2gpx.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Chaque fournisseur national a son nom et son calque, comme sur le PC : les
 * coches des réglages et la lecture de `calques.mbtiles` s'appuient dessus.
 */
class FournisseursTest {

    private fun lot(type: String, format: Int?, fournisseurs: List<String>) =
        Lot("E5_N40", type, format, fournisseurs, null, null, emptyMap(), 0, emptyList())

    @Test fun la_bd_topo_a_son_propre_calque() {
        val ign = Fournisseurs.deCle("ign")
        assertEquals("IGN BD TOPO", ign.nom)
        assertEquals("bdtopo", ign.calque)
        assertEquals(ign, Fournisseurs.deCalque("bdtopo"))
    }

    @Test fun chaque_fournisseur_a_une_cle_et_un_calque_distincts() {
        assertEquals(Fournisseurs.TOUS.size, Fournisseurs.TOUS.map { it.cle }.distinct().size)
        assertEquals(Fournisseurs.TOUS.size, Fournisseurs.TOUS.map { it.calque }.distinct().size)
    }

    @Test fun un_fournisseur_inconnu_garde_sa_cle_comme_calque() {
        assertEquals(Fournisseur("futur", "futur", "futur"), Fournisseurs.deCle("futur"))
        assertEquals(Fournisseur("futur", "futur", "futur"), Fournisseurs.deCalque("futur"))
    }

    @Test fun un_lot_de_format_3_nomme_ses_fournisseurs() {
        val fournisseurs = Fournisseurs.duLot(lot("enrichi", 3, listOf("ign", "swisstlm3d")))
        assertEquals(listOf("ign", "swisstlm3d"), fournisseurs.map { it.cle })
    }

    @Test fun un_lot_ancien_sans_fournisseur_est_celui_de_la_bd_topo() {
        assertEquals(listOf("ign"), Fournisseurs.duLot(lot("enrichi", 2, emptyList())).map { it.cle })
        assertTrue(Fournisseurs.duLot(lot("osm", 2, emptyList())).isEmpty())
    }
}
