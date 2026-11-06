package org.hike2gpx.android

import android.graphics.BitmapFactory
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import kotlin.math.PI
import kotlin.math.asinh
import kotlin.math.floor
import kotlin.math.tan

/**
 * Le relief Mapterhorn, le modèle que gpx2elev préfère (en France, le MNT de
 * l'IGN tiré du LiDAR HD). Les tuiles Terrarium du zoom 12 sont rapatriées à la
 * demande dans <dossier>/gpx2elev/tiles, comme relief.py sur le PC : une tuile
 * déjà là sert aux parcours suivants, sans réseau.
 *
 * altitude() interpole bilinéairement, avec le même pixel et les mêmes bornes
 * que relief.py, pour que le téléphone et le PC lisent le même relief.
 */
class Mapterhorn(private val dossier: File) : ModeleTerrain {
    private val cache = File(dossier, "gpx2elev/tiles")
    /** Les tuiles décodées, en mémoire : un parcours les lit dans l'ordre, et
     * seules les dernières servent encore. 32 tuiles font 32 Mo. */
    private val tuiles = object : LinkedHashMap<Long, IntArray>(32, 0.75f, true) {
        override fun removeEldestEntry(entree: MutableMap.MutableEntry<Long, IntArray>): Boolean =
            size > TUILES_EN_MEMOIRE
    }
    private val absentes = HashSet<Long>()

    /** Rapatrie d'avance les tuiles que le parcours peut lire. */
    fun preparer(coordonnees: List<DoubleArray>) {
        val necessaires = linkedSetOf<Pair<Int, Int>>()
        for (c in coordonnees) {
            val (px, py) = pixel(c[1], c[0])
            val x0 = floor(px - .5).toInt()
            val y0 = floor(py - .5).toInt()
            for (dx in 0..1) for (dy in 0..1) {
                val x = Math.floorDiv(x0 + dx, TAILLE)
                val y = Math.floorDiv(y0 + dy, TAILLE)
                if (x in 0 until (1 shl ZOOM) && y in 0 until (1 shl ZOOM)) necessaires.add(x to y)
            }
        }
        if (necessaires.size > MAX_TUILES)
            throw ErreurDenivele("parcours trop long pour le relief (${necessaires.size} tuiles)")
        for ((x, y) in necessaires) tuile(x, y)
    }

    override fun altitude(lat: Double, lon: Double): Double? {
        val (px, py) = pixel(lat, lon)
        val gx = px - .5
        val gy = py - .5
        val x0 = floor(gx).toInt()
        val y0 = floor(gy).toInt()
        val fx = gx - x0
        val fy = gy - y0
        val v00 = valeur(x0, y0) ?: return null
        val v10 = valeur(x0 + 1, y0) ?: return null
        val v01 = valeur(x0, y0 + 1) ?: return null
        val v11 = valeur(x0 + 1, y0 + 1) ?: return null
        return v00 * (1 - fx) * (1 - fy) + v10 * fx * (1 - fy) + v01 * (1 - fx) * fy + v11 * fx * fy
    }

    private fun valeur(px: Int, py: Int): Double? {
        val x = Math.floorDiv(px, TAILLE)
        val y = Math.floorDiv(py, TAILLE)
        val image = tuile(x, y) ?: return null
        val p = image[Math.floorMod(py, TAILLE) * TAILLE + Math.floorMod(px, TAILLE)]
        // Terrarium (Mapzen) : altitude = R × 256 + G + B / 256 − 32768.
        return ((p shr 16 and 0xff) * 256 + (p shr 8 and 0xff) + (p and 0xff) / 256.0 - 32768)
    }

    private fun tuile(x: Int, y: Int): IntArray? {
        val cle = (x.toLong() shl 32) or (y.toLong() and 0xffffffffL)
        tuiles[cle]?.let { return it }
        if (cle in absentes) return null
        val fichier = File(cache, "mapterhorn_${ZOOM}_${x}_${y}.webp")
        val octets = if (fichier.isFile) {
            try {
                fichier.readBytes()
            } catch (e: IOException) {
                throw ErreurDenivele("tuile de relief illisible (${e.message})")
            }
        } else {
            val recus = telecharger(x, y) ?: run {
                absentes.add(cle)
                return null
            }
            try {
                cache.mkdirs()
                val partiel = File(cache, "${fichier.name}.part")
                partiel.writeBytes(recus)
                if (!partiel.renameTo(fichier)) {
                    partiel.copyTo(fichier, overwrite = true)
                    partiel.delete()
                }
            } catch (e: IOException) {
                throw ErreurDenivele("tuile de relief non enregistrée (${e.message})")
            }
            recus
        }
        val image = BitmapFactory.decodeByteArray(octets, 0, octets.size)
            ?: throw ErreurDenivele("tuile de relief illisible")
        if (image.width != TAILLE || image.height != TAILLE) {
            image.recycle()
            throw ErreurDenivele("tuile de relief de taille inattendue")
        }
        val pixels = IntArray(TAILLE * TAILLE)
        image.getPixels(pixels, 0, TAILLE, 0, 0, TAILLE, TAILLE)
        image.recycle()
        tuiles[cle] = pixels
        return pixels
    }

    private fun telecharger(x: Int, y: Int): ByteArray? {
        val connexion = URL(ADRESSE.format(ZOOM, x, y)).openConnection() as HttpURLConnection
        try {
            connexion.connectTimeout = 30_000
            connexion.readTimeout = 60_000
            connexion.instanceFollowRedirects = true
            connexion.setRequestProperty("User-Agent", "${Depot.AGENT} (relief Mapterhorn)")
            val code = connexion.responseCode
            if (code == 404) return null
            if (code != 200) throw ErreurDenivele("relief Mapterhorn : réponse HTTP $code")
            return connexion.inputStream.use { it.readBytes() }
        } catch (e: IOException) {
            throw ErreurDenivele("relief Mapterhorn injoignable (${e.message})")
        } finally {
            connexion.disconnect()
        }
    }

    companion object {
        const val ZOOM = 12
        const val TAILLE = 512
        const val MAX_TUILES = 256
        const val TUILES_EN_MEMOIRE = 32
        const val ADRESSE = "https://tiles.mapterhorn.com/%d/%d/%d.webp"
        const val ATTRIBUTION = "Mapterhorn (IGN LiDAR HD en France)"

        /** Coordonnées en pixels du zoom 12 sur tout le planisphère (relief.pixel). */
        fun pixel(lat: Double, lon: Double): Pair<Double, Double> {
            val n = (1 shl ZOOM) * TAILLE.toDouble()
            val x = (lon + 180) / 360 * n
            val y = (1 - asinh(tan(Math.toRadians(lat))) / PI) / 2 * n
            return x to y
        }
    }
}
