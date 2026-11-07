package org.hike2gpx.android

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Les tuiles vectorielles du lot sont du protobuf MVT écrit par le PC
 * (mapbox-vector-tile) : le décodeur du téléphone doit y retrouver les mêmes
 * couches, attributs et géométries.
 */
class MvtTest {

    // ---------------------------------------------------------- encodage d'essai

    private fun varint(valeur: Long): ByteArray {
        var v = valeur
        val octets = mutableListOf<Byte>()
        while (true) {
            val bas = (v and 0x7f).toInt()
            v = v ushr 7
            if (v == 0L) {
                octets.add(bas.toByte()); break
            }
            octets.add((bas or 0x80).toByte())
        }
        return octets.toByteArray()
    }

    private fun cle(champ: Int, fil: Int) = varint(((champ shl 3) or fil).toLong())

    private fun message(champ: Int, contenu: ByteArray) = cle(champ, 2) + varint(contenu.size.toLong()) + contenu

    private fun chaine(champ: Int, texte: String) = message(champ, texte.toByteArray(Charsets.UTF_8))

    private fun entier(champ: Int, valeur: Long) = cle(champ, 0) + varint(valeur)

    private fun paquet(champ: Int, valeurs: List<Long>) =
        message(champ, valeurs.fold(ByteArray(0)) { acc, v -> acc + varint(v) })

    private fun zigzag(v: Long) = (v shl 1) xor (v shr 63)

    private fun tuileEssai(): ByteArray {
        // Une ligne (100, 200) -> (300, 200) -> (300, 400) en unités de tuile.
        val geometrie = listOf(
            (1L shl 3) or 1L, zigzag(100), zigzag(200),          // MoveTo
            (2L shl 3) or 2L, zigzag(200), zigzag(0),            // LineTo, 2 points
            zigzag(0), zigzag(200),
        )
        val objet = paquet(2, listOf(0, 0)) +                       // tags : clé 0, valeur 0
            entier(3, Mvt.LIGNE.toLong()) + paquet(4, geometrie)
        val couche = chaine(1, "voies") + message(2, objet) +
            chaine(3, "genre") + message(4, chaine(1, "sentier")) + entier(5, 4096)
        return message(3, couche)
    }

    // ------------------------------------------------------------------- essais

    @Test fun lit_une_ligne_et_ses_attributs() {
        val couches = Mvt.decoder(tuileEssai())
        assertEquals(setOf("voies"), couches.keys)
        val objets = couches.getValue("voies")
        assertEquals(1, objets.size)
        assertEquals(Mvt.LIGNE, objets[0].type)
        assertEquals("sentier", objets[0].attributs["genre"])
        val ligne = objets[0].lignes.single()
        assertEquals(3, ligne.size)
        assertArrayEquals(doubleArrayOf(100.0, 200.0), ligne[0], 0.0)
        assertArrayEquals(doubleArrayOf(300.0, 200.0), ligne[1], 0.0)
        assertArrayEquals(doubleArrayOf(300.0, 400.0), ligne[2], 0.0)
    }

    @Test fun un_point_par_move_to() {
        val commandes = listOf((2L shl 3) or 1L, zigzag(10), zigzag(20), zigzag(30), zigzag(40))
        val lignes = Mvt.geometrie(Mvt.POINT, commandes.map { it.toInt() })
        assertEquals(2, lignes.size)
        assertArrayEquals(doubleArrayOf(10.0, 20.0), lignes[0].single(), 0.0)
        assertArrayEquals(doubleArrayOf(40.0, 60.0), lignes[1].single(), 0.0)
    }

    @Test fun une_couche_inconnue_est_ignoree() {
        val couche = chaine(1, "autre") + entier(5, 4096)
        val couches = Mvt.decoder(message(3, couche))
        assertTrue(couches.getValue("autre").isEmpty())
    }

    @Test fun un_objet_sans_geometrie_ou_sans_type_est_ecarte() {
        val objet = entier(3, 0)
        val couche = chaine(1, "voies") + message(2, objet)
        assertTrue(Mvt.decoder(message(3, couche)).getValue("voies").isEmpty())
    }

    @Test fun les_coordonnees_de_tuile_reviennent_en_latlon() {
        // Le centre du planisphère au zoom 14 : la tuile 8192/8192.
        assertEquals(8192, Calques.xDeLon(0.0))
        assertEquals(8192, Calques.yDeLat(0.0))
        val bornes = Calques.bornes(8192, 8192)
        assertEquals(0.0, bornes.ouest, 1e-12)
        assertEquals(0.0, bornes.nord, 1e-9)
        assertEquals(360.0 / (1 shl 14), bornes.est, 1e-12)
        assertEquals(-360.0 / (1 shl 14), bornes.sud, 1e-9)
        assertEquals(0.0, Calques.mercatorY(0.0), 1e-9)
    }

    @Test fun le_relief_mapterhorn_est_au_zoom_12() {
        val (x, y) = Mapterhorn.pixel(0.0, 0.0)
        assertEquals(1_048_576.0, x, 1e-9)
        assertEquals(1_048_576.0, y, 1e-9)
    }

    @Test fun une_tuile_tronquee_ne_rend_pas_d_objet() {
        val tronquee = message(3, chaine(1, "voies")).copyOf(5)
        var couches: Map<String, List<Mvt.Objet>>? = null
        try {
            couches = Mvt.decoder(tronquee)
        } catch (e: IllegalArgumentException) {
            // Une tuile abîmée peut aussi être refusée : Calques la remplace par du vide.
        }
        assertTrue(couches == null || couches.isEmpty())
        assertNull(couches?.get("voies")?.firstOrNull())
    }
}
