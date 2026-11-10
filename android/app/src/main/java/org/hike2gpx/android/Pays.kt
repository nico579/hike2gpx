package org.hike2gpx.android

import android.content.res.AssetManager

/**
 * Le pays d'un point, pour choisir la carte nationale comme la page du PC :
 * le fond suit le centre de la carte, y compris après un déplacement manuel.
 * Les contours sont ceux de Natural Earth 1:50m, simplifiés à quelques
 * centaines de mètres (assets/pays.txt), pour les pays dont la page a une
 * carte nationale ; ailleurs, « autre », et la carte reste sur OSM.
 */
class Pays private constructor(private val contours: List<Contour>) {
    constructor(assets: AssetManager) :
        this(analyse(assets.open(FICHIER).bufferedReader().use { it.readText() }))

    /** Les mêmes contours lus d'un texte, pour les tests. */
    internal constructor(texte: String) : this(analyse(texte))

    private class Contour(val code: String, val anneaux: List<DoubleArray>) {
        val boite: DoubleArray = boite(anneaux)
    }

    /** Le code du pays (« fr », « ch »…), ou « autre ». */
    fun de(latitude: Double, longitude: Double): String =
        contours.firstOrNull { c ->
            latitude >= c.boite[1] && latitude <= c.boite[3] &&
                longitude >= c.boite[0] && longitude <= c.boite[2] &&
                contient(c.anneaux, latitude, longitude)
        }?.code ?: AUTRE

    companion object {
        const val AUTRE = "autre"
        private const val FICHIER = "pays.txt"

        /**
         * Une ligne par pays : le code, puis chaque anneau (un polygone, ses
         * trous) séparé par « | », chaque point « lon,lat » séparé par une
         * espace. Les lignes qui commencent par # sont des commentaires.
         */
        private fun analyse(texte: String): List<Contour> =
            texte.lineSequence()
                .map(String::trim)
                .filter { it.isNotEmpty() && !it.startsWith("#") }
                .map { ligne ->
                    val morceaux = ligne.split('|')
                    Contour(morceaux[0], morceaux.drop(1).map { anneau ->
                        anneau.split(' ')
                            .filter(String::isNotEmpty)
                            .flatMap { point -> point.split(',').map(String::toDouble) }
                            .toDoubleArray()
                    })
                }
                .toList()

        /** [ouest, sud, est, nord] des anneaux d'un pays. */
        private fun boite(anneaux: List<DoubleArray>): DoubleArray {
            var ouest = 180.0
            var sud = 90.0
            var est = -180.0
            var nord = -90.0
            for (anneau in anneaux) {
                var i = 0
                while (i < anneau.size) {
                    ouest = minOf(ouest, anneau[i])
                    est = maxOf(est, anneau[i])
                    sud = minOf(sud, anneau[i + 1])
                    nord = maxOf(nord, anneau[i + 1])
                    i += 2
                }
            }
            return doubleArrayOf(ouest, sud, est, nord)
        }

        /** Règle pair-impair sur tous les anneaux, trous compris, comme geofabrik._dans. */
        private fun contient(anneaux: List<DoubleArray>, lat: Double, lon: Double): Boolean {
            var dedans = false
            for (anneau in anneaux) {
                val n = anneau.size / 2
                var j = n - 1
                for (i in 0 until n) {
                    val xi = anneau[2 * i]
                    val yi = anneau[2 * i + 1]
                    val xj = anneau[2 * j]
                    val yj = anneau[2 * j + 1]
                    if ((yi > lat) != (yj > lat) && lon < (xj - xi) * (lat - yi) / (yj - yi) + xi)
                        dedans = !dedans
                    j = i
                }
            }
            return dedans
        }
    }
}
