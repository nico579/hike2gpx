package org.hike2gpx.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.exp

/**
 * Le protocole de gpx2elev, recopié de denivele.py : échantillonnage à 5 m,
 * lissage gaussien de 20 m, hystérésis de 2 m, puis Tobler tous les 20 m.
 * Les profils d'essai sont synthétiques : aucun réseau, aucune tuile.
 */
class DeniveleTest {

    private val base = 100.0
    private val longueurDeg = 0.01          // 1 111,95 m à l'équateur

    private fun trace(lonFin: Double = longueurDeg) =
        listOf(doubleArrayOf(0.0, 0.0), doubleArrayOf(lonFin, 0.0))

    /** Une pente régulière : 100 m de montée sur la longueur d'essai. */
    private fun pente(delta: Double = 100.0) = ModeleTerrain { _, lon -> base + lon / longueurDeg * delta }

    @Test fun les_distances_suivent_la_formule_de_gpx2elev() {
        val d = Denivele.distances(listOf(doubleArrayOf(6.0, 0.0), doubleArrayOf(6.0, 0.001)))
        assertEquals(0.0, d[0], 0.0)
        assertEquals(Denivele.RAYON_TERRE * Math.toRadians(0.001) / 2, d[1], 1e-6)
    }

    @Test fun les_fleches_se_posent_comme_sur_la_page() {
        // 9 km : un écart de 1 km, la première à 500 m, aucune sur l'arrivée.
        assertEquals(listOf(500.0, 1500.0, 2500.0, 3500.0, 4500.0, 5500.0, 6500.0, 7500.0),
            Denivele.distancesFleches(9000.0).toList())
        // 1 km : l'écart plancher de 300 m.
        assertEquals(listOf(150.0, 450.0, 750.0), Denivele.distancesFleches(1000.0).toList())
        // Trop court pour l'écart : une flèche au milieu ; sans longueur, aucune.
        assertEquals(listOf(100.0), Denivele.distancesFleches(200.0).toList())
        assertEquals(emptyList<Double>(), Denivele.distancesFleches(0.0).toList())
    }

    @Test fun un_terrain_plat_n_a_ni_montee_ni_descente() {
        val profil = Denivele.calculer(trace(), pente(0.0))
        assertEquals(0, profil.monteeM)
        assertEquals(0, profil.descenteM)
        assertEquals(100, profil.altitudeMinM)
        assertEquals(100, profil.altitudeMaxM)
        // Tobler à pente nulle : v = 6 × exp(−3,5 × 0,05).
        val attendu = longueurDeg * Denivele.RAYON_TERRE * Math.toRadians(1.0) / 2
        assertEquals(Math.round(attendu * 3.6 / (6 * exp(-3.5 * 0.05))).toLong(), profil.dureeMarcheS)
    }

    @Test fun une_montee_reguliere_donne_son_denivele() {
        val profil = Denivele.calculer(trace(), pente())
        assertEquals(100, profil.monteeM)
        assertEquals(0, profil.descenteM)
        assertEquals(100, profil.altitudeMinM)
        assertEquals(200, profil.altitudeMaxM)
        assertEquals(1089L, profil.dureeMarcheS)        // même valeur que gpx2elev sur ce profil
        assertEquals("Mapterhorn", profil.modele)
        // Le profil lissé garde la courbe à dessiner : une altitude par distance, de bout en bout.
        assertEquals(profil.distancesM.size, profil.altitudesM.size)
        assertTrue(profil.distancesM.size > 200)
        assertEquals(0.0, profil.distancesM.first(), 0.0)
        assertEquals(1111.95, profil.distancesM.last(), 0.5)
        assertEquals(100.0, profil.altitudesM.first(), 0.5)
        assertEquals(200.0, profil.altitudesM.last(), 0.5)
    }

    @Test fun la_descente_se_compte_dans_l_autre_sens() {
        val profil = Denivele.calculer(trace(), pente(-60.0))
        assertEquals(0, profil.monteeM)
        assertEquals(60, profil.descenteM)
        assertEquals(40, profil.altitudeMinM)
        assertEquals(100, profil.altitudeMaxM)
        assertEquals(676L, profil.dureeMarcheS)
    }

    @Test fun sans_relief_le_calcul_est_refuse() {
        val vide = ModeleTerrain { _, _ -> null }
        try {
            Denivele.calculer(trace(), vide)
            throw AssertionError("un relief absent doit être signalé")
        } catch (e: ErreurDenivele) {
            assertTrue(e.message!!.contains("relief"))
        }
    }

    @Test fun un_trace_d_un_seul_point_est_refuse() {
        try {
            Denivele.calculer(listOf(doubleArrayOf(6.0, 43.0)), pente())
            throw AssertionError("un tracé trop court doit être signalé")
        } catch (e: ErreurDenivele) {
            assertTrue(e.message!!.contains("court"))
        }
    }

    @Test fun la_gaussienne_laisse_un_profil_constant() {
        val x = DoubleArray(21) { it * 5.0 }
        val z = DoubleArray(x.size) { 250.0 }
        val lisse = Denivele.gaussienne(x, z)
        assertTrue(lisse.all { Math.abs(it - 250.0) < 1e-9 })
    }

    @Test fun la_gaussienne_conserve_une_pente_droite() {
        val x = DoubleArray(21) { it * 5.0 }
        val z = DoubleArray(x.size) { 10.0 + it * 2.0 }
        val lisse = Denivele.gaussienne(x, z)
        for (i in x.indices) assertEquals(z[i], lisse[i], 1e-9)
    }

    @Test fun l_hysteresis_retient_les_sommets_et_les_creux() {
        val z = doubleArrayOf(0.0, 0.0, 0.0, 5.0, 5.0, 5.0, 5.0, 0.0, 0.0, 0.0)
        val ancres = Denivele.ancres(z)
        assertEquals(listOf(0, 2, 6, 9), ancres.toList())
        assertEquals(5.0 to 5.0, Denivele.totaux(z, ancres))
    }

    @Test fun la_duree_tobler_est_celle_du_profil_plat() {
        val x = DoubleArray(201) { it * 5.0 }
        val z = DoubleArray(x.size) { 800.0 }
        val attendu = 1000.0 * 3.6 / (6 * exp(-3.5 * 0.05))
        assertEquals(attendu, Denivele.dureeTobler(x, z), 1e-6)
    }

    @Test fun la_position_sur_le_trace_suit_la_fraction() {
        // Un tracé en L : plein est, puis plein nord, deux tronçons égaux.
        val coords = listOf(doubleArrayOf(0.0, 0.0), doubleArrayOf(0.01, 0.0), doubleArrayOf(0.01, 0.01))
        val d = Denivele.distances(coords)
        val depart = Denivele.positionSurTrace(coords, d, 0.0)!!
        assertEquals(0.0, depart[0], 1e-9)
        assertEquals(0.0, depart[1], 1e-9)
        val fin = Denivele.positionSurTrace(coords, d, 1.0)!!
        assertEquals(0.01, fin[0], 1e-9)
        assertEquals(0.01, fin[1], 1e-9)
        // À mi-longueur, le coin du tracé.
        val milieu = Denivele.positionSurTrace(coords, d, 0.5)!!
        assertEquals(0.01, milieu[0], 1e-9)
        assertEquals(0.0, milieu[1], 1e-9)
        // La fraction est bornée, et un tracé sans longueur ne donne rien.
        val avant = Denivele.positionSurTrace(coords, d, -1.0)!!
        assertEquals(0.0, avant[0], 1e-9)
        assertEquals(null, Denivele.positionSurTrace(listOf(doubleArrayOf(0.0, 0.0)), DoubleArray(1), 0.5))
    }

    @Test fun l_interpolation_est_lineaire_et_bornee() {
        val x = doubleArrayOf(0.0, 10.0)
        val y = doubleArrayOf(100.0, 200.0)
        assertEquals(150.0, Denivele.interpole(5.0, x, y), 0.0)
        assertEquals(100.0, Denivele.interpole(-3.0, x, y), 0.0)
        assertEquals(200.0, Denivele.interpole(30.0, x, y), 0.0)
        assertNotNull(Denivele.interpole(0.0, x, y))
    }
}
