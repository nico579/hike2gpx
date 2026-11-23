package org.hike2gpx.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Le GPX de fin d'enregistrement : les altitudes du relief remplacent celles du
 * GPS, la description porte le dénivelé, et le fichier se relit tel qu'il a été
 * écrit. Les sources sont synthétiques : aucun réseau, aucune tuile.
 */
class GpxTest {

    /** Un relief en pente régulière : 100 m à l'origine, 10 m de plus par millième de longitude. */
    private val relief = object : SourceRelief {
        override val nom = "Relief d'essai"
        override fun altitudes(lats: DoubleArray, lons: DoubleArray): DoubleArray =
            DoubleArray(lons.size) { 100.0 + lons[it] * 1_000.0 }
    }

    private val absente = object : SourceRelief {
        override val nom = "Absente"
        override fun altitudes(lats: DoubleArray, lons: DoubleArray): DoubleArray? = null
    }

    private fun trace() = listOf(
        PointTrace(0.0, 0.0, 999.0, 1_700_000_000_000L),
        PointTrace(0.0, 0.01, 999.0, 1_700_000_060_000L),
    )

    @Test fun l_enrichissement_remplace_les_altitudes_et_donne_le_profil() {
        val points = trace()
        val (enrichis, profil) = Gpx.enrichir(points, listOf(relief))
        assertEquals("Relief d'essai", profil.modele)
        assertEquals(10, profil.monteeM)
        assertEquals(0, profil.descenteM)
        assertEquals(100, profil.altitudeMinM)
        assertEquals(110, profil.altitudeMaxM)
        // Les altitudes du GPS laissent la place à celles du relief, point par point.
        assertEquals(100.0, enrichis.first().altitude!!, 1e-6)
        assertEquals(110.0, enrichis.last().altitude!!, 1e-6)
        assertEquals(points.map { it.instant }, enrichis.map { it.instant })
    }

    @Test fun la_premiere_source_qui_couvre_tout_le_trace_l_emporte() {
        val (_, profil) = Gpx.enrichir(trace(), listOf(absente, relief))
        assertEquals("Relief d'essai", profil.modele)
    }

    @Test fun sans_relief_complet_l_enrichissement_est_refuse() {
        try {
            Gpx.enrichir(trace(), listOf(absente))
            throw AssertionError("un relief absent doit être signalé")
        } catch (e: ErreurDenivele) {
            assertTrue(e.message!!.contains("Absente"))
        }
    }

    @Test fun le_gpx_relu_garde_les_points_la_description_et_les_heures() {
        val points = trace()
        val texte = Gpx.ecrireTrace(points, "trace-20260101-120000", "D+ 10 m / D− 0 m")
        assertTrue(texte.contains("<desc>D+ 10 m / D− 0 m</desc>"))
        val relus = Gpx.lireTrace(texte)
        assertEquals(2, relus.size)
        assertEquals(points[0].lat, relus[0].lat, 0.0)
        assertEquals(points[0].lon, relus[0].lon, 0.0)
        assertEquals(points[0].altitude!!, relus[0].altitude!!, 1e-9)
        assertEquals(points[0].instant, relus[0].instant)
        assertEquals(points[1].instant, relus[1].instant)
    }

    @Test fun le_gpx_ecrit_echappe_le_nom_et_la_description() {
        val texte = Gpx.ecrireTrace(trace(), "trace <&>", "D+ 10 m < D− 0 m & plus")
        assertTrue(texte.contains("<name>trace &lt;&amp;&gt;</name>"))
        assertTrue(texte.contains("<desc>D+ 10 m &lt; D− 0 m &amp; plus</desc>"))
    }

    @Test fun les_segments_ecrits_se_relisent() {
        // Un KML importé devient un GPX d'un trkseg par segment, que lireTrace relit.
        val segments = listOf(
            listOf(0.0 to 0.0, 0.0 to 0.01),
            listOf(1.0 to 1.0, 1.0 to 1.01),
        )
        val texte = Gpx.ecrireSegments(segments, "importe-essai")
        assertTrue(texte.contains("<name>importe-essai</name>"))
        assertEquals(2, Regex("<trkseg>").findAll(texte).count())
        val relus = Gpx.lireTrace(texte)
        assertEquals(4, relus.size)
        assertEquals(0.0, relus[0].lat, 0.0)
        assertEquals(0.01, relus[1].lon, 0.0)
        assertEquals(1.0, relus[2].lat, 0.0)
        assertEquals(1.01, relus[3].lon, 0.0)
        assertNull(relus[0].altitude)
        assertEquals(0L, relus[0].instant)
    }
}
