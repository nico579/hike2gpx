package org.hike2gpx.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Le détail d'un GPX, quel qu'il soit : la distance, la durée des heures pour
 * une trace GPS (sinon celle de marche de Tobler), et le dénivelé du relief ou,
 * à défaut, des altitudes du fichier. Les sources sont synthétiques : aucun
 * réseau, aucune tuile.
 */
class DetailTraceTest {

    /** Un relief en pente régulière : 100 m à l'origine, 10 m de plus par millième de longitude. */
    private val relief = object : SourceRelief {
        override val nom = "Relief d'essai"
        override fun altitudes(lats: DoubleArray, lons: DoubleArray): DoubleArray =
            DoubleArray(lons.size) { 100.0 + lons[it] * 1_000.0 }
    }

    /** Deux points à 0,01° l'un de l'autre, soit 1 111,95 m à l'équateur. */
    private fun trace(heures: Boolean = true) = listOf(
        PointTrace(0.0, 0.0, null, if (heures) 1_700_000_000_000L else 0L),
        PointTrace(0.0, 0.01, null, if (heures) 1_700_000_060_000L else 0L),
    )

    @Test fun une_trace_horodatee_garde_sa_duree_de_parcours() {
        val detail = DetailTrace.calculer(trace(), listOf(relief), "fichier")
        assertTrue(detail.dureeReelle)
        // La durée est en secondes, comme le champ : 60 s entre les deux points.
        assertEquals(60L, detail.dureeS)
        assertEquals(1_111.95, detail.distanceM, 0.5)
        assertEquals("Relief d'essai", detail.modele)
    }

    @Test fun un_itineraire_sans_heures_prete_la_duree_de_marche() {
        val detail = DetailTrace.calculer(trace(heures = false), listOf(relief), "fichier")
        assertFalse(detail.dureeReelle)
        assertTrue((detail.dureeS ?: 0L) > 0L)
    }

    @Test fun sans_relief_les_altitudes_du_fichier_donnent_le_denivele() {
        val points = listOf(
            PointTrace(0.0, 0.0, 100.0, 0L),
            PointTrace(0.0, 0.005, 110.0, 0L),
            PointTrace(0.0, 0.01, 120.0, 0L),
        )
        val detail = DetailTrace.calculer(points, emptyList(), "altitudes du fichier")
        assertTrue(detail.denivele)
        assertEquals(20, detail.monteeM)
        assertEquals(0, detail.descenteM)
        assertEquals(100, detail.altitudeMinM)
        assertEquals(120, detail.altitudeMaxM)
        assertEquals("altitudes du fichier", detail.modele)
    }

    @Test fun sans_relief_ni_altitudes_le_denivele_reste_inconnu() {
        val detail = DetailTrace.calculer(trace(), emptyList(), "fichier")
        assertFalse(detail.denivele)
        assertNull(detail.monteeM)
        assertNull(detail.descenteM)
        assertNull(detail.modele)
    }

    @Test fun hors_reseau_une_altitude_manquante_est_comblee() {
        // La position du milieu n'a pas d'altitude : la droite entre 100 et 120
        // donne 110, et le dénivelé se calcule quand même, lissé comme le relief.
        val points = listOf(
            PointTrace(0.0, 0.0, 100.0, 0L),
            PointTrace(0.0, 0.005, null, 0L),
            PointTrace(0.0, 0.01, 120.0, 0L),
        )
        val detail = DetailTrace.calculer(points, emptyList(), "altitudes du fichier")
        assertTrue(detail.denivele)
        assertEquals(20, detail.monteeM)
        assertEquals(0, detail.descenteM)
        assertEquals(100, detail.altitudeMinM)
        assertEquals(120, detail.altitudeMaxM)
    }

    @Test fun les_trous_d_altitude_se_comblent_aux_extremites() {
        assertEquals(listOf(5.0, 10.0, 15.0, 20.0, 25.0),
            Denivele.completer(listOf(5.0, null, 15.0, null, 25.0))!!.toList())
        assertEquals(listOf(5.0, 5.0, 5.0),
            Denivele.completer(listOf(null, 5.0, null))!!.toList())
        assertNull(Denivele.completer(listOf(null, null)))
    }

    @Test fun les_segments_d_une_trace_importee_s_additionnent() {
        // Deux segments d'environ 1,1 km : un KML en a souvent plusieurs.
        val segments = listOf(
            listOf(0.0 to 0.0, 0.0 to 0.01),
            listOf(1.0 to 1.0, 1.0 to 1.01),
        )
        val detail = DetailTrace.calculerSegments(segments, listOf(relief), "fichier")
        assertEquals(4, detail.points)
        assertEquals(2_223.9, detail.distanceM, 1.0)
        assertTrue(detail.denivele)
        assertEquals(20, detail.monteeM)
        assertEquals(0, detail.descenteM)
        // La durée est celle de Tobler, segment par segment : aucune heure dans un KML.
        assertFalse(detail.dureeReelle)
        assertTrue((detail.dureeS ?: 0L) > 0L)
    }

    @Test fun un_segment_trop_court_est_ignore() {
        val detail = DetailTrace.calculerSegments(
            listOf(listOf(0.0 to 0.0, 0.0 to 0.01), listOf(1.0 to 1.0)), listOf(relief), "fichier")
        assertEquals(2, detail.points)
    }
}
