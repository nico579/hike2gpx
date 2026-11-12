package org.hike2gpx.android

import kotlin.math.hypot

/** Le choix du point touché parmi ceux d'un calque, sans dépendre de la carte (donc testable). */
object ToucheCalque {
    /** L'indice du point le plus proche de (x, y) à moins de [rayon] pixels, ou null. */
    fun plusProche(points: List<Pair<Float, Float>>, x: Float, y: Float, rayon: Float): Int? {
        var meilleur: Int? = null
        var distance = rayon
        for ((i, p) in points.withIndex()) {
            val d = hypot(p.first - x, p.second - y)
            if (d <= distance) {
                distance = d
                meilleur = i
            }
        }
        return meilleur
    }
}
