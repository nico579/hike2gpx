package org.hike2gpx.android

import android.content.Context
import android.graphics.Canvas
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.Path
import android.view.MotionEvent
import android.view.View
import java.util.Locale
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.roundToInt

/**
 * La courbe du dénivelé, comme le profil de la page : la distance en
 * abscisse, l'altitude lissée en ordonnée, l'aire sous la courbe en bleu
 * clair, trois repères horizontaux et les bornes d'altitude. Le profil est
 * celui de Denivele.calculer, déjà échantillonné et lissé ; cette vue ne
 * calcule rien.
 *
 * Comme sur la page, poser le doigt sur la courbe montre le point du tracé
 * correspondant : un curseur vertical, la distance et l'altitude sous le
 * doigt, et la position remontée par [onPosition] pour que la carte la
 * dessine. Lever le doigt efface tout.
 */
class CourbeDenivele(context: Context) : View(context) {
    var profil: ProfilAltimetrique? = null
        set(valeur) {
            field = valeur
            if (curseur != null) {
                curseur = null
                onPosition?.invoke(null)
            }
            invalidate()
        }

    /** La fraction du profil sous le doigt, ou null quand le doigt se lève. */
    var onPosition: ((Double?) -> Unit)? = null

    private var curseur: Int? = null

    private val densite = context.resources.displayMetrics.density
    private val grille = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = densite
        color = 0xffe4edf5.toInt()
        pathEffect = DashPathEffect(floatArrayOf(3 * densite, 5 * densite), 0f)
    }
    private val aire = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = 0x80d9e8fa.toInt()
    }
    private val ligne = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 2.5f * densite
        color = 0xff2870cb.toInt()
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }
    private val guide = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 1.2f * densite
        color = 0xff315f91.toInt()
        pathEffect = DashPathEffect(floatArrayOf(3 * densite, 3 * densite), 0f)
    }
    private val pastille = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = 0xffffffff.toInt()
    }
    private val bordure = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 2 * densite
        color = 0xff2367d1.toInt()
    }
    private val texte = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textSize = 10 * densite
        color = 0xff667f96.toInt()
    }

    /** Les bornes du dessin, partagées par le tracé et le curseur. */
    private class Cadre(
        val gauche: Float,
        val droite: Float,
        val haut: Float,
        val bas: Float,
        val basAlt: Double,
        val etendue: Double,
        val debut: Double,
        val longueur: Double,
    ) {
        fun x(distance: Double) = gauche + (droite - gauche) * ((distance - debut) / longueur).toFloat()
        fun y(altitude: Double) = bas - (bas - haut) * ((altitude - basAlt) / etendue).toFloat()
    }

    private fun cadre(): Cadre? {
        val p = profil ?: return null
        if (p.distancesM.size < 2 || p.altitudesM.size != p.distancesM.size) return null
        val gauche = 10 * densite
        val droite = width - 10 * densite
        val haut = 14 * densite
        val bas = height - 16 * densite
        if (droite <= gauche || bas <= haut) return null

        // Des bornes arrondies à 20 m, comme les repères du profil de la page.
        val minimum = p.altitudesM.min()
        val maximum = p.altitudesM.max()
        val basAlt = floor(minimum / 20.0) * 20.0
        val hautAlt = ceil(maximum / 20.0) * 20.0
        val etendue = max(hautAlt - basAlt, 20.0)
        val debut = p.distancesM.first()
        val longueur = p.distancesM.last() - debut
        if (longueur <= 0.0) return null
        return Cadre(gauche, droite, haut, bas, basAlt, etendue, debut, longueur)
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val p = profil ?: return
        val c = cadre() ?: return

        for (i in 0..2) {
            val y = c.haut + (c.bas - c.haut) * i / 2
            canvas.drawLine(c.gauche, y, c.droite, y, grille)
        }

        val chemin = Path()
        val aireChemin = Path()
        val pas = max(1, p.distancesM.size / 800)
        var premier = true
        var i = 0
        while (i < p.distancesM.size) {
            val x = c.x(p.distancesM[i])
            val y = c.y(p.altitudesM[i])
            if (premier) {
                chemin.moveTo(x, y)
                aireChemin.moveTo(x, c.bas)
                aireChemin.lineTo(x, y)
                premier = false
            } else {
                chemin.lineTo(x, y)
                aireChemin.lineTo(x, y)
            }
            i += pas
        }
        // Le dernier point du profil, même s'il tombe entre deux pas.
        val fin = p.distancesM.size - 1
        if (fin % pas != 0) {
            chemin.lineTo(c.droite, c.y(p.altitudesM[fin]))
            aireChemin.lineTo(c.droite, c.y(p.altitudesM[fin]))
        }
        aireChemin.lineTo(c.droite, c.bas)
        aireChemin.close()
        canvas.drawPath(aireChemin, aire)
        canvas.drawPath(chemin, ligne)

        texte.textAlign = Paint.Align.LEFT
        canvas.drawText("${ceil(p.altitudesM.max() / 20.0).toInt() * 20} m",
            c.gauche, c.haut - 4 * densite, texte)
        canvas.drawText("${floor(p.altitudesM.min() / 20.0).toInt() * 20} m",
            c.gauche, c.bas + 11 * densite, texte)
        texte.textAlign = Paint.Align.RIGHT
        canvas.drawText(String.format(Locale.getDefault(), "%.1f km", c.longueur / 1000),
            c.droite, c.bas + 11 * densite, texte)

        // Le curseur de la page : un trait vertical, la pastille sur la courbe
        // et la distance et l'altitude sous le doigt.
        val index = curseur ?: return
        if (index !in p.distancesM.indices) return
        val x = c.x(p.distancesM[index])
        val y = c.y(p.altitudesM[index])
        canvas.drawLine(x, c.haut, x, c.bas, guide)
        canvas.drawCircle(x, y, 4 * densite, pastille)
        canvas.drawCircle(x, y, 4 * densite, bordure)
        canvas.drawText(String.format(Locale.getDefault(), "%.2f km · %d m",
                (p.distancesM[index] - c.debut) / 1000, p.altitudesM[index].roundToInt()),
            c.droite, c.haut - 4 * densite, texte)
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        val p = profil ?: return false
        val c = cadre() ?: return false
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN, MotionEvent.ACTION_MOVE -> {
                // Le doigt sur la courbe explore le profil ; la carte, dessous,
                // ne doit ni bouger ni recevoir la fin du geste.
                parent?.requestDisallowInterceptTouchEvent(true)
                val index = indexA(event.x, c, p) ?: return false
                if (index != curseur) {
                    curseur = index
                    invalidate()
                }
                onPosition?.invoke(p.distancesM[index] / p.distancesM.last())
                return true
            }
            MotionEvent.ACTION_UP -> {
                performClick()
                lever()
                return true
            }
            MotionEvent.ACTION_CANCEL -> {
                lever()
                return true
            }
        }
        return super.onTouchEvent(event)
    }

    override fun performClick(): Boolean = super.performClick()

    /** L'index du profil le plus proche de l'abscisse touchée. */
    private fun indexA(x: Float, c: Cadre, p: ProfilAltimetrique): Int? {
        val fraction = ((x - c.gauche) / (c.droite - c.gauche)).coerceIn(0f, 1f).toDouble()
        val cible = c.debut + fraction * c.longueur
        var bas = 0
        var haut = p.distancesM.size - 1
        while (haut - bas > 1) {
            val milieu = (bas + haut) / 2
            if (p.distancesM[milieu] <= cible) bas = milieu else haut = milieu
        }
        return if (cible - p.distancesM[bas] <= p.distancesM[haut] - cible) bas else haut
    }

    private fun lever() {
        if (curseur == null) return
        curseur = null
        invalidate()
        onPosition?.invoke(null)
    }
}
