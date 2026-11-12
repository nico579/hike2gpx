package org.hike2gpx.android

import android.content.Context
import android.graphics.Canvas
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.Path
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay

/**
 * Dessine les calques d'un lot sous le tracé, avec les styles de la page :
 * sentiers OSM en tirets violets, pistes pleines, routes fines et transparentes,
 * barrières rouges, franchissements en pastilles (rouge bloquant, orange à
 * vérifier), chemins non raccordés en pastilles jaunes cerclées de brun,
 * tronçons BD TOPO en tirets turquoise.
 */
class CalquesOverlay(context: Context) : Overlay() {
    @Volatile var donnees = DonneesCalques()

    private val densite = context.resources.displayMetrics.density
    private val trait = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }
    private val pastille = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL }
    private val contour = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 2 * densite
        color = 0xffffffff.toInt()
    }
    private val point = android.graphics.Point()

    /**
     * Le franchissement le plus proche d'un toucher, s'il tombe dans la zone
     * tactile (bien plus large que la pastille : un doigt n'est pas une souris).
     */
    fun franchissementToucheA(vue: MapView, p: GeoPoint): PointFranchissement? {
        val liste = donnees.franchissements
        if (liste.isEmpty()) return null
        val toucher = vue.projection.toPixels(p, null)
        val pixels = liste.map { f ->
            val q = vue.projection.toPixels(GeoPoint(f.lat, f.lon), null)
            q.x.toFloat() to q.y.toFloat()
        }
        return ToucheCalque.plusProche(pixels, toucher.x.toFloat(), toucher.y.toFloat(), RAYON_TACTILE_DP * densite)
            ?.let { liste[it] }
    }

    override fun draw(canvas: Canvas, vue: MapView, ombre: Boolean) {
        if (ombre || donnees.vide) return
        for (troncon in donnees.troncons) {
            val nature = troncon.nature
            when {
                nature in NATURES_SENTIER -> tracer(canvas, vue, troncon.points, COULEUR_OFFICIEL, 3f, floatArrayOf(4f, 4f))
                nature == "Route empierrée" -> tracer(canvas, vue, troncon.points, COULEUR_OFFICIEL, 3f, null)
                else -> tracer(canvas, vue, troncon.points, COULEUR_OFFICIEL, 2f, null, 115)
            }
        }
        for (voie in donnees.voies) {
            when (voie.genre) {
                "sentier" -> tracer(canvas, vue, voie.points, COULEUR_OSM, 3f, floatArrayOf(6f, 4f))
                "piste" -> tracer(canvas, vue, voie.points, COULEUR_OSM, 3f, null)
                else -> tracer(canvas, vue, voie.points, COULEUR_OSM, 2f, null, 115)
            }
        }
        for (barriere in donnees.barrieres)
            tracer(canvas, vue, barriere.points, COULEUR_BARRIERE, 3f, null)
        for (f in donnees.franchissements) {
            vue.projection.toPixels(GeoPoint(f.lat, f.lon), point)
            pastille.color = if (f.statut == "blocked") COULEUR_BLOQUE else COULEUR_A_VERIFIER
            canvas.drawCircle(point.x.toFloat(), point.y.toFloat(), 6 * densite, pastille)
            canvas.drawCircle(point.x.toFloat(), point.y.toFloat(), 6 * densite, contour)
        }
        for (j in donnees.jonctions) {
            vue.projection.toPixels(GeoPoint(j.lat, j.lon), point)
            pastille.color = COULEUR_JONCTION
            canvas.drawCircle(point.x.toFloat(), point.y.toFloat(), 6 * densite, pastille)
            contour.color = CONTOUR_JONCTION
            canvas.drawCircle(point.x.toFloat(), point.y.toFloat(), 6 * densite, contour)
            contour.color = 0xffffffff.toInt()
        }
    }

    private fun tracer(canvas: Canvas, vue: MapView, points: List<Point>, couleur: Int,
                       epaisseur: Float, tirets: FloatArray?, alpha: Int = 255) {
        if (points.size < 2) return
        val chemin = Path()
        var premier = true
        for (p in points) {
            vue.projection.toPixels(GeoPoint(p.lat, p.lon), point)
            if (premier) {
                chemin.moveTo(point.x.toFloat(), point.y.toFloat())
                premier = false
            } else {
                chemin.lineTo(point.x.toFloat(), point.y.toFloat())
            }
        }
        trait.color = couleur
        trait.alpha = alpha
        trait.strokeWidth = epaisseur * densite
        trait.pathEffect = tirets?.let { DashPathEffect(FloatArray(it.size) { i -> it[i] * densite }, 0f) }
        canvas.drawPath(chemin, trait)
    }

    companion object {
        const val COULEUR_OSM = 0xff7b1fa2.toInt()
        const val COULEUR_BARRIERE = 0xffe53935.toInt()
        /** Zone tactile d'une pastille de franchissement, en dp. */
        const val RAYON_TACTILE_DP = 24f
        const val COULEUR_OFFICIEL = 0xff00897b.toInt()
        const val COULEUR_BLOQUE = 0xffd32f2f.toInt()
        const val COULEUR_A_VERIFIER = 0xffef6c00.toInt()
        // Les chemins non raccordés, comme sur la page du PC.
        const val COULEUR_JONCTION = 0xfffdd835.toInt()
        const val CONTOUR_JONCTION = 0xff4e342e.toInt()
        val NATURES_SENTIER = setOf("Sentier", "Chemin", "Escalier")
    }
}
