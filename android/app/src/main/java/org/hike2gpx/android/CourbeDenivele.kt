package org.hike2gpx.android

import android.content.Context
import android.graphics.Canvas
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.Path
import android.view.View
import java.util.Locale
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.max

/**
 * La courbe du dénivelé, comme le profil de la page : la distance en
 * abscisse, l'altitude lissée en ordonnée, l'aire sous la courbe en bleu
 * clair, trois repères horizontaux et les bornes d'altitude. Le profil est
 * celui de Denivele.calculer, déjà échantillonné et lissé ; cette vue ne
 * calcule rien.
 */
class CourbeDenivele(context: Context) : View(context) {
    var profil: ProfilAltimetrique? = null
        set(valeur) {
            field = valeur
            invalidate()
        }

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
    private val texte = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textSize = 10 * densite
        color = 0xff667f96.toInt()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val p = profil ?: return
        if (p.distancesM.size < 2 || p.altitudesM.size != p.distancesM.size) return
        val gauche = 10 * densite
        val droite = width - 10 * densite
        val haut = 14 * densite
        val bas = height - 16 * densite
        if (droite <= gauche || bas <= haut) return

        // Des bornes arrondies à 20 m, comme les repères du profil de la page.
        val minimum = p.altitudesM.min()
        val maximum = p.altitudesM.max()
        val basAlt = floor(minimum / 20.0) * 20.0
        val hautAlt = ceil(maximum / 20.0) * 20.0
        val etendue = max(hautAlt - basAlt, 20.0)
        val debut = p.distancesM.first()
        val longueur = p.distancesM.last() - debut
        if (longueur <= 0.0) return

        for (i in 0..2) {
            val y = haut + (bas - haut) * i / 2
            canvas.drawLine(gauche, y, droite, y, grille)
        }

        val chemin = Path()
        val aireChemin = Path()
        val pas = max(1, p.distancesM.size / 800)
        var premier = true
        var i = 0
        while (i < p.distancesM.size) {
            val x = gauche + (droite - gauche) * ((p.distancesM[i] - debut) / longueur).toFloat()
            val y = bas - (bas - haut) * ((p.altitudesM[i] - basAlt) / etendue).toFloat()
            if (premier) {
                chemin.moveTo(x, y)
                aireChemin.moveTo(x, bas)
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
            val x = droite
            val y = bas - (bas - haut) * ((p.altitudesM[fin] - basAlt) / etendue).toFloat()
            chemin.lineTo(x, y)
            aireChemin.lineTo(x, y)
        }
        aireChemin.lineTo(droite, bas)
        aireChemin.close()
        canvas.drawPath(aireChemin, aire)
        canvas.drawPath(chemin, ligne)

        texte.textAlign = Paint.Align.LEFT
        canvas.drawText("${hautAlt.toInt()} m", gauche, haut - 4 * densite, texte)
        canvas.drawText("${basAlt.toInt()} m", gauche, bas + 11 * densite, texte)
        texte.textAlign = Paint.Align.RIGHT
        canvas.drawText(String.format(Locale.getDefault(), "%.1f km", longueur / 1000),
            droite, bas + 11 * densite, texte)
    }
}
