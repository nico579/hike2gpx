package org.hike2gpx.android

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Point
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay

/**
 * Le point de la courbe du dénivelé sur la carte, comme le circleMarker du
 * profil de la page : un disque bleu cerclé de blanc, sans interaction.
 * [position] vaut null hors du geste, et rien n'est alors dessiné.
 */
class RepereProfil(context: Context) : Overlay() {
    @Volatile var position: GeoPoint? = null

    private val rayon = 7 * context.resources.displayMetrics.density
    private val disque = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = 0xff1565c0.toInt()
    }
    private val contour = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 2 * context.resources.displayMetrics.density
        color = 0xffffffff.toInt()
    }
    private val ecran = Point()

    override fun draw(canvas: Canvas, vue: MapView, ombre: Boolean) {
        if (ombre) return
        val p = position ?: return
        vue.projection.toPixels(p, ecran)
        canvas.drawCircle(ecran.x.toFloat(), ecran.y.toFloat(), rayon, disque)
        canvas.drawCircle(ecran.x.toFloat(), ecran.y.toFloat(), rayon, contour)
    }
}
