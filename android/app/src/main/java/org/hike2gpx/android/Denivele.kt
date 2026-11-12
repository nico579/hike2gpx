package org.hike2gpx.android

import kotlin.math.abs
import kotlin.math.asin
import kotlin.math.ceil
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt
import kotlin.math.sin
import kotlin.math.sqrt

/** Un modèle de terrain : l'altitude en mètres, ou null s'il ne couvre pas le point. */
fun interface ModeleTerrain {
    fun altitude(lat: Double, lon: Double): Double?
}

/**
 * Une source d'altitudes pour tous les points d'un tracé à la fois, comme les
 * lecteurs de gpx2elev : elle rend une altitude par point, ou null si elle ne
 * les couvre pas tous. Une exception compte aussi comme un échec de la source.
 */
interface SourceRelief {
    val nom: String
    fun altitudes(lats: DoubleArray, lons: DoubleArray): DoubleArray?
}

/** Un modèle point par point vu comme une source : un seul trou suffit à l'écarter. */
fun ModeleTerrain.enSource(nom: String): SourceRelief = object : SourceRelief {
    override val nom = nom
    override fun altitudes(lats: DoubleArray, lons: DoubleArray): DoubleArray? {
        val resultat = DoubleArray(lats.size)
        for (i in lats.indices) resultat[i] = altitude(lats[i], lons[i]) ?: return null
        return resultat
    }
}

class ErreurDenivele(message: String) : Exception(message)

/** Le relief d'un parcours, calculé comme denivele.calculer sur le PC. */
data class ProfilAltimetrique(
    val monteeM: Int,
    val descenteM: Int,
    val altitudeMinM: Int,
    val altitudeMaxM: Int,
    val dureeMarcheS: Long,
    val modele: String,
    /** Le profil lissé de gpx2elev : distance en mètres, altitude en mètres. */
    val distancesM: DoubleArray = DoubleArray(0),
    val altitudesM: DoubleArray = DoubleArray(0),
)

/**
 * Le protocole de gpx2elev, recopié de denivele.py et de gpx2elev.core :
 * échantillonnage tous les 5 m, lissage gaussien de 20 m (prolongement impair
 * aux extrémités), D+/D− avec une hystérésis de 2 m, puis le modèle de Tobler
 * (v = 6 × exp(−3,5 × |pente + 0,05|) km/h) tous les 20 m.
 *
 * Les sources se prennent dans l'ordre de gpx2elev (Repository.obtain) :
 * la première qui couvre tout le tracé l'emporte, IGN LiDAR HD d'abord, puis
 * Mapterhorn. Une altitude n'est valable que finie et entre −1000 et 9000 m,
 * le critère de gpx2elev ; le « sans donnée » de l'IGN (−99999) fait passer
 * à la source suivante.
 */
object Denivele {
    const val PAS = 5.0
    const val SIGMA = 20.0
    const val HYSTERESIS = 2.0
    const val PAS_TOBLER = 20.0
    const val RAYON_TERRE = 12_742_000.0      // diamètre, comme gpx2elev

    fun calculer(coordonnees: List<DoubleArray>, modele: ModeleTerrain,
                 nomModele: String = "Mapterhorn"): ProfilAltimetrique =
        calculer(coordonnees, listOf(modele.enSource(nomModele)))

    /**
     * Les altitudes de la première source qui couvre tous les points, et
     * cette source. Sans aucune, l'erreur donne la raison de chaque échec.
     */
    fun obtenir(sources: List<SourceRelief>, lats: DoubleArray,
                lons: DoubleArray): Pair<SourceRelief, DoubleArray> {
        val echecs = mutableListOf<String>()
        for (source in sources) {
            val valeurs = try {
                source.altitudes(lats, lons)
            } catch (e: Exception) {
                echecs.add("${source.nom} : ${e.message ?: e}")
                continue
            }
            if (valeurs != null && valeurs.size == lats.size && valeurs.all(::valide))
                return source to valeurs
            echecs.add("${source.nom} : ne couvre pas tout le parcours")
        }
        throw ErreurDenivele((listOf("relief absent sur le parcours") + echecs).joinToString(" ; "))
    }

    private fun valide(altitude: Double) = altitude.isFinite() && altitude in -1000.0..9000.0

    fun calculer(coordonnees: List<DoubleArray>, sources: List<SourceRelief>): ProfilAltimetrique {
        if (coordonnees.size < 2) throw ErreurDenivele("tracé trop court")
        val distances = distances(coordonnees)
        val garde = mutableListOf<Int>()
        for (i in 0 until coordonnees.size - 1) if (distances[i + 1] > distances[i]) garde.add(i)
        garde.add(coordonnees.size - 1)
        if (garde.size < 2) throw ErreurDenivele("tracé sans deux positions distinctes")

        val x = DoubleArray(garde.size) { distances[garde[it]] }
        if (x.last() <= 0.0) throw ErreurDenivele("tracé sans longueur")
        val lons = DoubleArray(garde.size) { coordonnees[garde[it]][0] }
        val lats = DoubleArray(garde.size) { coordonnees[garde[it]][1] }

        val n = ceil(x.last() / PAS).toInt()
        val grille = DoubleArray(n + 1)
        for (i in 0 until n) grille[i] = i * PAS
        grille[n] = x.last()

        val latsGrille = DoubleArray(grille.size) { interpole(grille[it], x, lats) }
        val lonsGrille = DoubleArray(grille.size) { interpole(grille[it], x, lons) }
        val (source, altitudes) = obtenir(sources, latsGrille, lonsGrille)
        val lisse = gaussienne(grille, altitudes)
        val gain = totaux(lisse, ancres(lisse))
        val duree = dureeTobler(grille, lisse)
        return ProfilAltimetrique(
            monteeM = gain.first.roundToInt(),
            descenteM = gain.second.roundToInt(),
            altitudeMinM = minimum(lisse).roundToInt(),
            altitudeMaxM = maximum(lisse).roundToInt(),
            dureeMarcheS = Math.round(duree),
            modele = source.nom,
            distancesM = grille.copyOf(),
            altitudesM = lisse.copyOf(),
        )
    }

    /** Distances cumulées en mètres, formule de gpx2elev (rayon = diamètre terrestre). */
    fun distances(coordonnees: List<DoubleArray>): DoubleArray {
        val d = DoubleArray(coordonnees.size)
        for (i in 1 until coordonnees.size) {
            val lat1 = Math.toRadians(coordonnees[i - 1][1])
            val lat2 = Math.toRadians(coordonnees[i][1])
            val dlat = lat2 - lat1
            val dlon = Math.toRadians(coordonnees[i][0] - coordonnees[i - 1][0])
            val h = sin(dlat / 2) * sin(dlat / 2) + cos(lat1) * cos(lat2) * sin(dlon / 2) * sin(dlon / 2)
            d[i] = d[i - 1] + RAYON_TERRE * asin(sqrt(h.coerceIn(0.0, 1.0)))
        }
        return d
    }

    /**
     * Où poser les flèches du sens de marche, en mètres depuis le départ :
     * le calcul de preparerFleches sur la page, un écart de longueur / 9
     * (300 m au moins), la première flèche à un demi-écart du départ.
     */
    fun distancesFleches(longueurM: Double): DoubleArray {
        if (longueurM <= 0) return DoubleArray(0)
        val ecart = maxOf(300.0, longueurM / 9)
        val cibles = generateSequence(ecart / 2) { it + ecart }.takeWhile { it < longueurM - ecart / 2 }.toList()
        return if (cibles.isEmpty()) doubleArrayOf(longueurM / 2) else cibles.toDoubleArray()
    }

    /**
     * La position (longitude, latitude) à une fraction de la longueur du
     * tracé, comme positionSurProfil de la page : la fraction vient de la
     * courbe, la position est interpolée entre les points du tracé.
     */
    fun positionSurTrace(coordonnees: List<DoubleArray>, distances: DoubleArray,
                         fraction: Double): DoubleArray? {
        if (coordonnees.size < 2 || distances.size != coordonnees.size) return null
        if (!fraction.isFinite()) return null
        val total = distances.last()
        if (!total.isFinite() || total <= 0.0) return null
        val cible = fraction.coerceIn(0.0, 1.0) * total
        var debut = 1
        var fin = distances.size - 1
        while (debut < fin) {
            val milieu = (debut + fin) / 2
            if (distances[milieu] < cible) debut = milieu + 1 else fin = milieu
        }
        val ecart = distances[debut] - distances[debut - 1]
        val part = if (ecart > 0.0) (cible - distances[debut - 1]) / ecart else 0.0
        return DoubleArray(2) { i ->
            coordonnees[debut - 1][i] + part * (coordonnees[debut][i] - coordonnees[debut - 1][i])
        }
    }

    /**
     * Lissage gaussien de gpx2elev : noyau fini de rayon 4σ, prolongement
     * impair du profil aux deux bouts, puis interpolation sur les x d'origine.
     */
    fun gaussienne(x: DoubleArray, z: DoubleArray, sigma: Double = SIGMA, pas: Double = PAS): DoubleArray {
        require(x.size == z.size && x.isNotEmpty())
        require(x.indices.all { it == 0 || x[it] > x[it - 1] })
        if (x.size == 1 || sigma == 0.0) return z.copyOf()
        val longueur = x.last() - x.first()
        if (longueur <= 0.0) return z.copyOf()
        val rayon = (4 * sigma / pas + .5).toInt()
        val noyau = DoubleArray(2 * rayon + 1) { i ->
            val decalage = (i - rayon) * pas
            exp(-.5 * (decalage / sigma) * (decalage / sigma))
        }
        val somme = noyau.sum()
        for (i in noyau.indices) noyau[i] /= somme
        val dernier = ceil(longueur / pas).toInt()
        val points = 2 * rayon + dernier + 1
        val etendue = DoubleArray(points) { i ->
            val q = (i - rayon) * pas
            val periodes = floor(q / (2 * longueur))
            val reste = q - periodes * 2 * longueur
            val avant = reste <= longueur
            val reflechi = if (avant) reste else 2 * longueur - reste
            val dedans = interpole(x.first() + reflechi, x, z)
            (if (avant) dedans else 2 * z.last() - dedans) + 2 * periodes * (z.last() - z.first())
        }
        val filtre = DoubleArray(dernier + 1)
        for (i in filtre.indices) {
            var sommePonderee = 0.0
            for (k in noyau.indices) sommePonderee += etendue[i + k] * noyau[k]
            filtre[i] = sommePonderee
        }
        val grille = DoubleArray(dernier + 1) { x.first() + it * pas }
        return DoubleArray(x.size) { interpole(x[it], grille, filtre) }
    }

    /** Les sommets et creux retenus par l'hystérésis de 2 m (gpx2elev.anchors). */
    fun ancres(z: DoubleArray, seuil: Double = HYSTERESIS): IntArray {
        require(z.isNotEmpty())
        if (seuil == 0.0) return IntArray(z.size) { it }
        val resultat = mutableListOf(0)
        var bas = 0
        var haut = 0
        var extreme = 0
        var sens = 0
        for (i in 1 until z.size) {
            if (sens == 0) {
                if (z[i] <= z[bas]) bas = i
                if (z[i] >= z[haut]) haut = i
                if (z[i] - z[bas] >= seuil) {
                    if (resultat.last() != bas) resultat.add(bas)
                    sens = 1; extreme = i
                } else if (z[haut] - z[i] >= seuil) {
                    if (resultat.last() != haut) resultat.add(haut)
                    sens = -1; extreme = i
                }
            } else if (sens == 1) {
                if (z[i] >= z[extreme]) extreme = i
                else if (z[extreme] - z[i] >= seuil) {
                    if (resultat.last() != extreme) resultat.add(extreme)
                    sens = -1; extreme = i
                }
            } else {
                if (z[i] <= z[extreme]) extreme = i
                else if (z[i] - z[extreme] >= seuil) {
                    if (resultat.last() != extreme) resultat.add(extreme)
                    sens = 1; extreme = i
                }
            }
        }
        if (sens != 0 && resultat.last() != extreme) resultat.add(extreme)
        if (resultat.last() != z.size - 1) resultat.add(z.size - 1)
        return resultat.toIntArray()
    }

    /** Montée et descente entre les points retenus, en mètres. */
    fun totaux(z: DoubleArray, indices: IntArray): Pair<Double, Double> {
        var montee = 0.0
        var descente = 0.0
        for (i in 1 until indices.size) {
            val delta = z[indices[i]] - z[indices[i - 1]]
            if (delta > 0) montee += delta else descente -= delta
        }
        return montee to descente
    }

    /**
     * Le modèle de Tobler de denivele.duree_tobler : le profil lissé est
     * rééchantillonné tous les 20 m dans le sens du parcours, puis les durées
     * de chaque tronçon s'additionnent, sans pause.
     */
    fun dureeTobler(x: DoubleArray, z: DoubleArray, pas: Double = PAS_TOBLER): Double {
        if (x.size < 2) return 0.0
        val distances = mutableListOf(x[0])
        val altitudes = mutableListOf(z[0])
        var cible = x[0] + pas
        var precedent = 0
        for (courant in 1 until x.size) {
            if (x[courant] <= x[precedent]) continue
            while (cible <= x[courant]) {
                val fraction = (cible - x[precedent]) / (x[courant] - x[precedent])
                distances.add(cible)
                altitudes.add(z[precedent] + fraction * (z[courant] - z[precedent]))
                cible += pas
            }
            precedent = courant
        }
        if (distances.last() < x[precedent]) {
            distances.add(x[precedent])
            altitudes.add(z[precedent])
        }
        var secondes = 0.0
        for (i in 1 until distances.size) {
            val pente = (altitudes[i] - altitudes[i - 1]) / (distances[i] - distances[i - 1])
            val vitesse = 6 * exp(-3.5 * abs(pente + 0.05))
            secondes += (distances[i] - distances[i - 1]) * 3.6 / vitesse
        }
        return secondes
    }

    /** np.interp : linéaire entre les points, constant au-delà des bornes. */
    fun interpole(valeur: Double, x: DoubleArray, y: DoubleArray): Double {
        if (valeur <= x[0]) return y[0]
        if (valeur >= x.last()) return y.last()
        var bas = 0
        var haut = x.size - 1
        while (haut - bas > 1) {
            val milieu = (bas + haut) / 2
            if (x[milieu] <= valeur) bas = milieu else haut = milieu
        }
        val fraction = (valeur - x[bas]) / (x[haut] - x[bas])
        return y[bas] + fraction * (y[haut] - y[bas])
    }

    private fun minimum(z: DoubleArray): Double = z.reduce { a, b -> min(a, b) }
    private fun maximum(z: DoubleArray): Double = z.reduce { a, b -> max(a, b) }
}
