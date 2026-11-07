package org.hike2gpx.android

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Point
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay

/**
 * La position du GPS, comme le point bleu de Locus Map : un halo translucide
 * à la taille de la précision annoncée, puis un disque bleu cerclé de blanc.
 * [position] vaut null tant qu'aucun point n'est connu.
 */
class PositionOverlay(context: Context) : Overlay() {
    @Volatile var position: GeoPoint? = null
    @Volatile var precision: Float = 0f

    private val densite = context.resources.displayMetrics.density
    private val rayonPoint = 7 * densite
    private val halo = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = 0x331565c0
    }
    private val disque = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = 0xff1565c0.toInt()
    }
    private val contour = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 2 * densite
        color = 0xffffffff.toInt()
    }
    private val ecran = Point()

    override fun draw(canvas: Canvas, vue: MapView, ombre: Boolean) {
        if (ombre) return
        val p = position ?: return
        vue.projection.toPixels(p, ecran)
        val x = ecran.x.toFloat()
        val y = ecran.y.toFloat()
        if (precision > 0f) {
            val rayon = vue.projection.metersToEquatorPixels(precision)
            canvas.drawCircle(x, y, rayon, halo)
        }
        canvas.drawCircle(x, y, rayonPoint, disque)
        canvas.drawCircle(x, y, rayonPoint, contour)
    }
}
