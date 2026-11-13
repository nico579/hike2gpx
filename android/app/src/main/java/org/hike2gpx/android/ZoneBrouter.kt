package org.hike2gpx.android

import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.io.RandomAccessFile
import java.net.HttpURLConnection
import java.net.URL
import java.nio.ByteBuffer
import java.util.zip.CRC32
import kotlin.math.abs
import kotlin.math.floor

/**
 * La zone de routage de base d'une case, prise sur brouter.de quand le
 * serveur de hike2gpx n'en publie pas (le Canada, l'Asie…) : la RD5 que
 * l'application BRouter télécharge elle-même, et dont part aussi le lot OSM
 * du PC (fabrication.fabriquer). Le calcul d'itinéraire marche alors partout.
 *
 * Le téléphone n'en fabrique pas le reste, les chemins dessinés sur la carte
 * et l'analyse des franchissements : il faudrait l'extrait OSM de la région,
 * des Go, et des heures de calcul. Le PC prépare ce lot complet et le partage.
 *
 * La RD5 devient un lot « osm » ordinaire, avec son manifeste, installé par
 * HorsLigne.installer comme un lot du serveur.
 */
object ZoneBrouter {
    const val SEGMENTS = "https://brouter.de/brouter/segments4/"
    private const val DELAI_MS = 30_000

    /** La case de 5° d'un point, au nom de BRouter : E5_N40, W115_N50. */
    fun caseDe(lat: Double, lon: Double): String {
        val la = (floor(lat / 5) * 5).toInt()
        val lo = (floor(lon / 5) * 5).toInt()
        return "${if (lo < 0) "W" else "E"}${abs(lo)}_${if (la < 0) "S" else "N"}${abs(la)}"
    }

    /** La boîte [sud, ouest, nord, est] d'une case. */
    fun boite(case: String): List<Double> {
        val m = Regex("([EW])(\\d{1,3})_([NS])(\\d{1,2})").matchEntire(case)
            ?: throw IllegalArgumentException(case)
        val lo = m.groupValues[2].toDouble() * (if (m.groupValues[1] == "W") -1 else 1)
        val la = m.groupValues[4].toDouble() * (if (m.groupValues[3] == "S") -1 else 1)
        return listOf(la, lo, la + 5, lo + 5)
    }

    /** La taille de la RD5 sur brouter.de, ou null si elle n'existe pas (la mer) ou sans réseau. */
    fun taille(case: String): Long? = try {
        val c = URL("$SEGMENTS$case.rd5").openConnection() as HttpURLConnection
        c.requestMethod = "HEAD"
        c.connectTimeout = DELAI_MS
        c.readTimeout = DELAI_MS
        try {
            if (c.responseCode == 200) c.contentLengthLong.takeIf { it > 0 } else null
        } finally {
            c.disconnect()
        }
    } catch (e: IOException) {
        null
    }

    /**
     * La RD5 dans travail, reprise après une coupure (Range), vérifiée comme
     * le fait BRouter, puis son manifeste : le dossier est prêt pour
     * HorsLigne.installer. suivi(faits, total) en octets.
     */
    fun telecharger(case: String, travail: File, suivi: (Long, Long) -> Unit = { _, _ -> },
                    continuer: () -> Boolean = { true }): File {
        travail.mkdirs()
        val rd5 = File(travail, "$case.rd5")
        val total = taille(case) ?: throw ErreurDepot(R.string.err_brouter_absent, listOf(case))
        if (travail.usableSpace < total - (if (rd5.exists()) rd5.length() else 0) + Depot.MARGE_DISQUE)
            throw ErreurDepot(R.string.err_place, listOf(total / 1_000_000 + 1))
        if (rd5.exists() && rd5.length() > total) rd5.delete()
        while (rd5.length() < total) {
            val deja = if (rd5.exists()) rd5.length() else 0L
            val c = URL("$SEGMENTS$case.rd5").openConnection() as HttpURLConnection
            c.connectTimeout = DELAI_MS
            c.readTimeout = DELAI_MS
            if (deja > 0) c.setRequestProperty("Range", "bytes=$deja-")
            try {
                val reprise = deja > 0 && c.responseCode == 206
                if (!reprise && c.responseCode != 200)
                    throw ErreurDepot(R.string.err_brouter_absent, listOf(case))
                var faits = if (reprise) deja else 0L
                c.inputStream.use { entree ->
                    java.io.FileOutputStream(rd5, reprise).use { sortie ->
                        val bloc = ByteArray(1 shl 16)
                        while (true) {
                            if (!continuer()) throw Abandon()
                            val n = entree.read(bloc)
                            if (n < 0) break
                            sortie.write(bloc, 0, n)
                            faits += n
                            suivi(faits, total)
                        }
                    }
                }
                if (faits < total) throw IOException("transfert coupé à $faits / $total octets")
            } finally {
                c.disconnect()
            }
        }
        if (!rd5Entier(rd5)) {
            rd5.delete()
            throw ErreurDepot(R.string.err_brouter_altere, listOf(case))
        }
        val manifeste = JSONObject()
            .put("format", 3).put("case", case).put("type", "osm")
            .put("zone", JSONArray(boite(case)))
            .put("sources", JSONObject().put("rd5", "brouter.de"))
            .put("fichiers", JSONArray().put(JSONObject().put("nom", rd5.name).put("octets", rd5.length())
                .put("sha256", empreinte(rd5))))
        File(travail, "manifest.json").writeText(manifeste.toString())
        return travail
    }

    /**
     * Une RD5 complète, selon la règle de BRouter lui-même (PhysicalFile,
     * 1.7.10), comme brouter.rd5_entier sur le PC : ses 200 premiers octets
     * indexent ses 25 sous-tuiles, la dernière entrée marque la fin des
     * données ; le fichier s'arrête là (ancien format), ou porte un pied d'au
     * moins 112 octets avec le CRC de cet en-tête. Un transfert coupé y échoue.
     */
    fun rd5Entier(fichier: File): Boolean = try {
        RandomAccessFile(fichier, "r").use { f ->
            val taille = f.length()
            if (taille < 200) return false
            val entete = ByteArray(200)
            f.readFully(entete)
            val fin = ByteBuffer.wrap(entete, 24 * 8, 8).long and 0xFFFFFFFFFFFFL
            if (taille == fin) return true
            if (taille - fin < 112) return false
            f.seek(fin + 8)
            val crc = f.readInt().toLong() and 0xFFFFFFFFL
            // Le CRC32 de BRouter (btools.util.Crc32) ne s'inverse pas à la fin
            // comme celui de zlib ; « ^ 2 » marque le nouveau format.
            val attendu = CRC32().apply { update(entete) }.value xor 0xFFFFFFFFL
            crc == attendu || crc == (attendu xor 2L)
        }
    } catch (e: IOException) {
        false
    }
}
