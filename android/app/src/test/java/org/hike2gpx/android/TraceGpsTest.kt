package org.hike2gpx.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
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
}
