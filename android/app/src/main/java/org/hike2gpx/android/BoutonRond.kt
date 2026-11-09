package org.hike2gpx.android

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.view.View
import kotlin.math.min

/**
 * Un bouton rond posé sur la carte, comme ceux de Locus Map : sombre pour
 * recentrer sur le GPS, vert pour démarrer une trace, rouge avec un carré
 * pendant l'enregistrement. Les icônes sont dessinées, sans image à charger.
 */
class BoutonRond(context: Context, val genre: Genre) : View(context) {
    enum class Genre { POSITION, TRACE, MENU }

    /** Pour le bouton de trace : vrai quand un enregistrement est en cours. */
    var enregistre = false
        set(v) {
            field = v
            invalidate()
        }

    private val densite = context.resources.displayMetrics.density
    private val fond = Paint(Paint.ANTI_ALIAS_FLAG)
    private val trait = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeWidth = 2.2f * densite
        color = 0xffffffff.toInt()
    }
    private val plein = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = 0xffffffff.toInt()
    }
    private val triangle = Path()

    init {
        isClickable = true
        isFocusable = true
    }

    override fun drawableStateChanged() {
        super.drawableStateChanged()
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        val cx = width / 2f
        val cy = height / 2f
        val rayon = min(width, height) / 2f - 2 * densite
        fond.style = Paint.Style.FILL
        fond.color = when {
            genre == Genre.TRACE && enregistre -> 0xffd32f2f.toInt()
            genre == Genre.TRACE -> 0xff689f38.toInt()
            // Semi-transparents comme les commandes de Locus Map : la carte
            // reste lisible dessous.
            else -> 0xaa263238.toInt()
        }
        if (isPressed) fond.color = (fond.color and 0x00ffffff) or 0xbb000000.toInt()
        canvas.drawCircle(cx, cy, rayon, fond)
        when (genre) {
            Genre.POSITION -> dessinerCroix(canvas, cx, cy, rayon)
            Genre.TRACE -> if (enregistre) dessinerCarre(canvas, cx, cy, rayon)
            else dessinerTriangle(canvas, cx, cy, rayon)
            Genre.MENU -> dessinerMenu(canvas, cx, cy, rayon)
        }
    }

    /** Les trois traits du menu, comme le bouton de Locus Map. */
    private fun dessinerMenu(canvas: Canvas, cx: Float, cy: Float, rayon: Float) {
        val demi = rayon * 0.44f
        val ecart = rayon * 0.22f
        for (i in -1..1) {
            val y = cy + i * ecart
            canvas.drawLine(cx - demi, y, cx + demi, y, trait)
        }
    }

    /** La croix de recentrage : un cercle, un point central et quatre traits. */
    private fun dessinerCroix(canvas: Canvas, cx: Float, cy: Float, rayon: Float) {
        canvas.drawCircle(cx, cy, rayon * 0.34f, trait)
        canvas.drawCircle(cx, cy, rayon * 0.09f, plein)
        val debut = rayon * 0.52f
        val fin = rayon * 0.72f
        canvas.drawLine(cx, cy - debut, cx, cy - fin, trait)
        canvas.drawLine(cx, cy + debut, cx, cy + fin, trait)
        canvas.drawLine(cx - debut, cy, cx - fin, cy, trait)
        canvas.drawLine(cx + debut, cy, cx + fin, cy, trait)
    }

    /** Le triangle « lecture » de Locus, tourné vers la droite. */
    private fun dessinerTriangle(canvas: Canvas, cx: Float, cy: Float, rayon: Float) {
        triangle.reset()
        triangle.moveTo(cx - rayon * 0.22f, cy - rayon * 0.32f)
        triangle.lineTo(cx - rayon * 0.22f, cy + rayon * 0.32f)
        triangle.lineTo(cx + rayon * 0.34f, cy)
        triangle.close()
        canvas.drawPath(triangle, plein)
    }

    /** Le carré d'arrêt, pendant l'enregistrement. */
    private fun dessinerCarre(canvas: Canvas, cx: Float, cy: Float, rayon: Float) {
        val cote = rayon * 0.52f
        canvas.drawRoundRect(RectF(cx - cote / 2, cy - cote / 2, cx + cote / 2, cy + cote / 2),
            2 * densite, 2 * densite, plein)
    }
}
