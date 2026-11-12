package org.hike2gpx.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ZoomCalquesTest {
    @Test fun le_zoom_des_calques_reste_entre_les_bornes_du_lot_et_de_la_carte() {
        // Le lot n'a pas de tuile sous le zoom 14, et la carte ne descend pas au-delà de 19.
        assertEquals(14, borneZoomCalques(1))
        assertEquals(14, borneZoomCalques(0))
        assertEquals(16, borneZoomCalques(16))
        assertEquals(19, borneZoomCalques(116))
    }

    @Test fun le_defaut_du_telephone_est_dans_les_bornes_et_plus_haut_que_celui_du_pc() {
        // Le PC garde 14 (grand écran) ; le téléphone, 2,5 km de vue, moins de lignes à tracer.
        assertTrue(ZOOM_CALQUES_DEFAUT in ZOOM_CALQUES_MIN..ZOOM_CALQUES_MAX)
        assertTrue(ZOOM_CALQUES_DEFAUT > ZOOM_CALQUES_MIN)
    }
}
