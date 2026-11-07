package org.hike2gpx.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Le filtre de trace de Locus Map et le GPX produit : des points figés, sans
 * GPS ni réseau. La distance est celle de la Terre moyenne (haversine).
 */
class TraceGpsTest {

    @Test fun le_premier_point_ne_respecte_que_la_precision() {
        val trace = TraceGps()
        assertFalse(trace.ajouter(43.0, 6.0, null, 0L, 150.0))
        assertTrue(trace.ajouter(43.0, 6.0, null, 0L, 10.0))
        assertEquals(1, trace.taille)
    }

    @Test fun la_distance_et_la_duree_doivent_toutes_deux_etre_atteintes() {
        val trace = TraceGps(distanceMin = 10.0, dureeMin = 10_000L, precisionMax = 100.0)
        assertTrue(trace.ajouter(43.0, 6.0, null, 0L, 5.0))
        // 111 m, mais 5 s seulement : trop tôt.
        assertFalse(trace.ajouter(43.001, 6.0, null, 5_000L, 5.0))
        // 20 s, mais 4 m seulement : trop près.
        assertFalse(trace.ajouter(43.0, 6.00005, null, 20_000L, 5.0))
        // Les deux conditions réunies.
        assertTrue(trace.ajouter(43.001, 6.0, null, 20_000L, 5.0))
        assertEquals(2, trace.taille)
    }

    @Test fun un_gps_trop_imprecis_est_ecarte() {
        val trace = TraceGps(precisionMax = 100.0)
        assertFalse(trace.ajouter(43.0, 6.0, null, 0L, 120.0))
        assertTrue(trace.ajouter(43.0, 6.0, null, 0L, 100.0))
        // Sans précision annoncée, le point passe (comme Locus).
        assertTrue(trace.ajouter(43.001, 6.0, null, 20_000L, null))
    }

    @Test fun les_coordonnees_invalides_sont_refusees() {
        val trace = TraceGps()
        assertFalse(trace.ajouter(91.0, 6.0, null, 0L, 5.0))
        assertFalse(trace.ajouter(43.0, 181.0, null, 0L, 5.0))
        assertFalse(trace.ajouter(Double.NaN, 6.0, null, 0L, 5.0))
        assertEquals(0, trace.taille)
    }

    @Test fun la_distance_et_la_duree_se_calculent_sur_les_points_retenus() {
        val trace = TraceGps(distanceMin = 10.0, dureeMin = 0L)
        trace.ajouter(43.0, 6.0, 100.0, 1_000L, 5.0)
        trace.ajouter(43.001, 6.0, 101.0, 21_000L, 5.0)
        assertEquals(111.2, trace.distance, 0.5)
        assertEquals(20_000L, trace.duree)
        assertEquals(111_195.0, distanceMetres(43.0, 6.0, 44.0, 6.0), 50.0)
    }

    @Test fun le_geojson_garde_lordre_lon_lat_alt() {
        val trace = TraceGps()
        trace.ajouter(43.5, 6.25, 120.0, 0L, 5.0)
        val point = trace.geojson().getJSONArray(0)
        assertEquals(6.25, point.getDouble(0), 0.0)
        assertEquals(43.5, point.getDouble(1), 0.0)
        assertEquals(120.0, point.getDouble(2), 0.0)
    }

    @Test fun le_gpx_garde_lheure_et_laltitude() {
        val gpx = Gpx.ecrireTrace(listOf(PointTrace(43.0, 6.0, 120.5, 0L)), "essai")
        assertTrue(gpx.contains("<name>essai</name>"))
        assertTrue(gpx.contains("<trkpt lat=\"43.0\" lon=\"6.0\">"))
        assertTrue(gpx.contains("<ele>120.5</ele>"))
        assertTrue(gpx.contains("<time>1970-01-01T00:00:00Z</time>"))
        // Sans altitude, pas de balise vide.
        assertFalse(Gpx.ecrireTrace(listOf(PointTrace(43.0, 6.0, null, 0L)))
            .contains("<ele>"))
    }

    @Test fun les_reglages_sappliquent_a_une_trace_en_cours() {
        val trace = TraceGps(distanceMin = 10.0, dureeMin = 10_000L, precisionMax = 100.0)
        trace.ajouter(43.0, 6.0, null, 0L, 5.0)
        trace.distanceMin = 200.0
        assertFalse(trace.ajouter(43.001, 6.0, null, 20_000L, 5.0))
        trace.distanceMin = 10.0
        trace.dureeMin = 0L
        assertTrue(trace.ajouter(43.001, 6.0, null, 20_000L, 5.0))
    }

    @Test fun un_gpx_de_lhistorique_se_relit_a_lidentique() {
        val points = listOf(
            PointTrace(43.0, 6.0, 120.5, 1_000L),
            PointTrace(43.001, 6.002, null, 21_000L),
        )
        val texte = Gpx.ecrireTrace(points, "aller", "D+ 10 m / D− 5 m (gpx2elev)")
        assertTrue(texte.contains("<desc>D+ 10 m / D− 5 m (gpx2elev)</desc>"))
        val relus = Gpx.lireTrace(texte)
        assertEquals(2, relus.size)
        assertEquals(43.0, relus[0].lat, 0.0)
        assertEquals(6.0, relus[0].lon, 0.0)
        assertEquals(120.5, relus[0].altitude!!, 0.0)
        assertEquals(1_000L, relus[0].instant)
        // Sans altitude, le point relu n'en invente pas.
        assertTrue(relus[1].altitude == null)
        assertEquals(21_000L, relus[1].instant)
    }

    @Test fun enrichir_remplace_laltitude_gps_par_le_relief() {
        // Un relief qui monte de 1 m par 0,001° de longitude : 100 m sur 0,1°.
        val relief = ModeleTerrain { _, lon -> 100.0 + (lon - 6.0) * 1_000.0 }
        val points = listOf(
            PointTrace(43.0, 6.0, 999.0, 0L),
            PointTrace(43.0, 6.1, 999.0, 3_600_000L),
        )
        val (enrichis, profil) = Gpx.enrichir(points, relief)
        assertEquals(2, enrichis.size)
        assertEquals(100.0, enrichis[0].altitude!!, 0.5)
        assertEquals(200.0, enrichis[1].altitude!!, 0.5)
        assertEquals(6.0, enrichis[0].lon, 0.0)
        assertEquals(0L, enrichis[0].instant)
        // Le profil gpx2elev suit le relief, pas les altitudes GPS.
        assertTrue(profil.monteeM > 90)
        assertTrue(profil.altitudeMaxM > profil.altitudeMinM)
    }

    @Test fun enrichir_echoue_si_le_relief_ne_couvre_pas_le_trace() {
        val points = listOf(
            PointTrace(43.0, 6.0, 100.0, 0L),
            PointTrace(43.0, 6.1, 100.0, 1_000L),
        )
        val erreur = assertThrows(ErreurDenivele::class.java) {
            Gpx.enrichir(points, ModeleTerrain { _, _ -> null })
        }
        assertNotNull(erreur)
        // Un tracé d'un seul point ne peut pas non plus être enrichi.
        assertThrows(ErreurDenivele::class.java) {
            Gpx.enrichir(points.take(1), ModeleTerrain { _, _ -> 100.0 })
        }
    }
}
