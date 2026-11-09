package org.hike2gpx.android

import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * IGN LiDAR HD puis Mapterhorn, l'ordre de gpx2elev. Réponses de l'IGN
 * recopiées d'un vrai appel (Sainte-Baume, puis Rome hors couverture) ; aucun
 * réseau.
 */
class IgnLidarTest {
    private val lats = doubleArrayOf(43.33, 41.9)
    private val lons = doubleArrayOf(5.7, 12.5)

    @Test fun la_requete_est_celle_de_gpx2elev() {
        val corps = JSONObject(IgnLidar.requete(lats, lons, 0, 2))
        assertEquals("ign_lidar_hd_mnt_mono_wld", corps.getString("resource"))
        assertEquals("|", corps.getString("delimiter"))
        assertEquals("true", corps.getString("zonly"))
        assertEquals("43.3300000|41.9000000", corps.getString("lat"))
        assertEquals("5.7000000|12.5000000", corps.getString("lon"))
    }

    @Test fun les_reponses_zonly_et_objets_se_lisent() {
        assertArrayEquals(doubleArrayOf(652.64, -99999.0),
            IgnLidar.analyser("""{"elevations": [652.64, -99999.0]}""", 2), 0.0)
        assertArrayEquals(doubleArrayOf(652.64),
            IgnLidar.analyser("""{"elevations": [{"lon": 5.7, "lat": 43.33, "z": 652.64}]}""", 1), 0.0)
    }

    @Test fun une_reponse_incomplete_est_rejetee() {
        assertNull(IgnLidar.analyser("""{"elevations": [652.64]}""", 2))
        assertNull(IgnLidar.analyser("""{"erreur": "x"}""", 1))
    }

    private fun source(nom: String, valeurs: DoubleArray?) = object : SourceRelief {
        override val nom = nom
        override fun altitudes(lats: DoubleArray, lons: DoubleArray) = valeurs
    }

    @Test fun hors_couverture_ign_mapterhorn_prend_le_relais() {
        val ign = source(IgnLidar.NOM, doubleArrayOf(652.64, -99999.0))
        val mapterhorn = source(Mapterhorn.NOM, doubleArrayOf(650.0, 20.0))
        val (retenue, valeurs) = Denivele.obtenir(listOf(ign, mapterhorn), lats, lons)
        assertEquals(Mapterhorn.NOM, retenue.nom)
        assertArrayEquals(doubleArrayOf(650.0, 20.0), valeurs, 0.0)
    }

    @Test fun l_ign_l_emporte_quand_il_couvre_tout() {
        val ign = source(IgnLidar.NOM, doubleArrayOf(652.64, 640.0))
        val mapterhorn = source(Mapterhorn.NOM, doubleArrayOf(650.0, 638.0))
        assertEquals(IgnLidar.NOM, Denivele.obtenir(listOf(ign, mapterhorn), lats, lons).first.nom)
    }

    @Test fun sans_reseau_l_echec_de_l_ign_passe_a_mapterhorn() {
        val ign = object : SourceRelief {
            override val nom = IgnLidar.NOM
            override fun altitudes(lats: DoubleArray, lons: DoubleArray): DoubleArray? =
                throw ErreurDenivele("IGN LiDAR HD injoignable")
        }
        val mapterhorn = source(Mapterhorn.NOM, doubleArrayOf(650.0, 20.0))
        assertEquals(Mapterhorn.NOM, Denivele.obtenir(listOf(ign, mapterhorn), lats, lons).first.nom)
    }

    @Test fun sans_aucune_source_l_erreur_dit_pourquoi() {
        try {
            Denivele.obtenir(listOf(source(IgnLidar.NOM, null), source(Mapterhorn.NOM, null)), lats, lons)
            throw AssertionError("un relief absent doit être signalé")
        } catch (e: ErreurDenivele) {
            assertTrue(e.message!!.contains(IgnLidar.NOM))
            assertTrue(e.message!!.contains(Mapterhorn.NOM))
        }
    }

    @Test fun le_profil_porte_le_nom_de_la_source_retenue() {
        val trace = listOf(doubleArrayOf(0.0, 0.0), doubleArrayOf(0.001, 0.0))
        val ign = object : SourceRelief {
            override val nom = IgnLidar.NOM
            override fun altitudes(lats: DoubleArray, lons: DoubleArray) = DoubleArray(lats.size) { 100.0 }
        }
        assertEquals(IgnLidar.NOM, Denivele.calculer(trace, listOf(ign)).modele)
    }
}
