package org.hike2gpx.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ToucheCalqueTest {
    private val points = listOf(100f to 100f, 130f to 100f, 400f to 400f)

    @Test
    fun lePlusProcheDansLeRayonEstChoisi() {
        assertEquals(0, ToucheCalque.plusProche(points, 108f, 100f, 60f))
        assertEquals(1, ToucheCalque.plusProche(points, 120f, 100f, 60f))
    }

    @Test
    fun horsDuRayonRienNEstChoisi() {
        assertNull(ToucheCalque.plusProche(points, 250f, 250f, 60f))
        assertNull(ToucheCalque.plusProche(emptyList(), 0f, 0f, 60f))
    }
}
