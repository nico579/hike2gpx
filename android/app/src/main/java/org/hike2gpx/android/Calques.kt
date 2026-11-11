package org.hike2gpx.android

import android.database.sqlite.SQLiteDatabase
import java.io.ByteArrayInputStream
import java.io.File
import java.util.zip.GZIPInputStream
import kotlin.math.PI
import kotlin.math.asinh
import kotlin.math.atan
import kotlin.math.exp
import kotlin.math.floor
import kotlin.math.sinh
import kotlin.math.tan

/** Une voie OSM affichable, avec son genre (sentier, piste ou route). */
data class Voie(val genre: String, val points: List<Point>)

/** Une barrière linéaire gênant un piéton (clôture, mur, haie…). */
data class Barriere(val nature: String, val points: List<Point>)

/** Un franchissement bloquant ou à vérifier, posé sur la carte. */
data class PointFranchissement(val lat: Double, val lon: Double, val statut: String, val nature: String)

/** Un tronçon d'un fournisseur national (BD TOPO, ATKIS…). */
data class Troncon(val nature: String, val points: List<Point>, val fournisseur: String = "")

data class DonneesCalques(
    val voies: List<Voie> = emptyList(),
    val barrieres: List<Barriere> = emptyList(),
    val franchissements: List<PointFranchissement> = emptyList(),
    val troncons: List<Troncon> = emptyList(),
) {
    val vide: Boolean get() = voies.isEmpty() && barrieres.isEmpty() && franchissements.isEmpty() && troncons.isEmpty()
}

/**
 * Les calques d'un lot, lus dans ses tuiles vectorielles (calques.mbtiles),
 * comme lot.lire_calque sur le PC : les voies praticables OSM et leur genre,
 * les barrières qui gênent un piéton, les franchissements bloquants ou à
 * vérifier, et les tronçons de chaque fournisseur national retenu par le lot
 * (BD TOPO, ATKIS…), filtrés par les coches des réglages.
 *
 * Le lot lu est celui qui couvre le centre de la vue ; les tuiles du zoom 14
 * sont rangées en TMS (comme tout MBTiles) et compressées en gzip.
 */
class Calques(private val horsLigne: HorsLigne) {

    fun lire(zone: Zone, osm: Boolean, officiels: Set<String>): DonneesCalques {
        if (!osm && officiels.isEmpty()) return DonneesCalques()
        val lot = lotVisible(zone) ?: return DonneesCalques()
        val fichier = File(File(horsLigne.racine, lot.case), "calques.mbtiles")
        if (!fichier.isFile) return DonneesCalques()
        val voies = mutableListOf<Voie>()
        val barrieres = mutableListOf<Barriere>()
        val franchissements = mutableListOf<PointFranchissement>()
        val troncons = mutableListOf<Troncon>()
        val vus = mutableSetOf<String>()
        val base = try {
            SQLiteDatabase.openDatabase(fichier.path, null, SQLiteDatabase.OPEN_READONLY)
        } catch (e: Exception) {
            return DonneesCalques()
        }
        try {
            base.rawQuery("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'tiles'", null).use { c ->
                if (!c.moveToFirst()) return DonneesCalques()
            }
            for ((x, y) in tuiles(zone)) {
                val donnees = tuile(base, x, y) ?: continue
                for ((nom, objets) in donnees) {
                    when {
                        osm && nom == "voies" -> for (objet in objets) {
                            for (ligne in objet.lignes) {
                                val points = points(ligne, x, y)
                                if (points.size >= 2)
                                    voies.add(Voie(objet.attributs["genre"]?.toString() ?: "route", points))
                            }
                        }
                        osm && nom == "barrieres" -> for (objet in objets) {
                            for (ligne in objet.lignes) {
                                val points = points(ligne, x, y)
                                if (points.size >= 2)
                                    barrieres.add(Barriere(objet.attributs["nature"]?.toString() ?: "", points))
                            }
                        }
                        osm && nom == "franchissements" -> for (objet in objets) {
                            for (ligne in objet.lignes) {
                                val point = points(ligne, x, y).firstOrNull() ?: continue
                                val cle = objet.attributs["cle"]?.toString()
                                if (cle != null && !vus.add(cle)) continue
                                franchissements.add(PointFranchissement(
                                    point.lat, point.lon,
                                    objet.attributs["statut"]?.toString() ?: "uncertain",
                                    objet.attributs["nature"]?.toString() ?: "",
                                ))
                            }
                        }
                        else -> {
                            val fournisseur = fournisseurDe(nom, lot) ?: continue
                            if (fournisseur.cle !in officiels) continue
                            for (objet in objets) {
                                for (ligne in objet.lignes) {
                                    val points = points(ligne, x, y)
                                    if (points.size >= 2)
                                        troncons.add(Troncon(
                                            objet.attributs["nature"]?.toString() ?: "", points, fournisseur.cle,
                                        ))
                                }
                            }
                        }
                    }
                }
            }
        } catch (e: Exception) {
            // Une tuile abîmée ne doit pas emporter les calques déjà lus.
        } finally {
            base.close()
        }
        return DonneesCalques(voies, barrieres, franchissements, troncons)
    }

    /**
     * Le fournisseur d'une couche de tronçons. Un lot de format 2 n'a que
     * `troncons`, celle de son unique fournisseur (la BD TOPO) ; un lot de
     * format 3 nomme chaque couche `troncons_<calque>`.
     */
    private fun fournisseurDe(nom: String, lot: Lot): Fournisseur? = when {
        nom == "troncons" -> Fournisseurs.duLot(lot).firstOrNull()
        nom.startsWith("troncons_") -> Fournisseurs.deCalque(nom.removePrefix("troncons_"))
        else -> null
    }

    /**
     * Les fournisseurs nationaux du lot qui couvre la vue : seuls ceux-là ont
     * leur coche de superposition, comme la page, qui ne la montre que si les
     * chemins du pays sont là. Un lot frontalier en contient souvent plusieurs,
     * mais la coche ne suit que le pays affiché : à Genève, swissTLM3D, pas
     * l'IGN. Sans lot de la zone, seule la coche OSM reste.
     */
    fun fournisseursVisibles(zone: Zone, pays: String): List<Fournisseur> =
        lotVisible(zone)?.let { Fournisseurs.duLot(it) }.orEmpty()
            .filter { it.pays == null || it.pays == pays }
            .distinctBy { it.cle }.sortedBy { it.nom }

    /** Le lot qui couvre le centre de la vue, l'enrichi d'abord à égalité (comme lot_couvrant). */
    private fun lotVisible(zone: Zone): Lot? {
        val lat = (zone.sud + zone.nord) / 2
        val lon = (zone.ouest + zone.est) / 2
        val lots = horsLigne.lots().filter {
            File(File(horsLigne.racine, it.case), "calques.mbtiles").isFile && it.couverture != null
        }
        fun contient(lot: Lot): Boolean = lot.couverture!!.let { c -> lat in c[0]..c[2] && lon in c[1]..c[3] }
        fun touche(lot: Lot): Boolean = lot.couverture!!.let { c ->
            zone.sud <= c[2] && zone.nord >= c[0] && zone.ouest <= c[3] && zone.est >= c[1]
        }
        return lots.filter(::contient).minByOrNull { if (it.osm) 1 else 0 }
            ?: lots.filter(::touche).minByOrNull { if (it.osm) 1 else 0 }
    }

    private fun tuile(base: SQLiteDatabase, x: Int, y: Int): Map<String, List<Mvt.Objet>>? {
        val tms = (1 shl ZOOM) - 1 - y
        val octets = base.rawQuery(
            "SELECT tile_data FROM tiles WHERE zoom_level = ? AND tile_column = ? AND tile_row = ?",
            arrayOf(ZOOM.toString(), x.toString(), tms.toString()),
        ).use { c ->
            if (c.moveToFirst()) c.getBlob(0) else null
        } ?: return null
        val brut = if (octets.size >= 2 && octets[0] == 0x1f.toByte() && octets[1] == 0x8b.toByte())
            GZIPInputStream(ByteArrayInputStream(octets)).use { it.readBytes() } else octets
        return Mvt.decoder(brut)
    }

    /** Les tuiles du zoom 14 qui touchent la vue, au plus MAX_TUILES. */
    private fun tuiles(zone: Zone): List<Pair<Int, Int>> {
        val x0 = xDeLon(zone.ouest.coerceIn(-180.0, 179.999))
        val x1 = xDeLon(zone.est.coerceIn(-180.0, 179.999))
        val y0 = yDeLat(zone.nord.coerceIn(-85.0, 85.0))
        val y1 = yDeLat(zone.sud.coerceIn(-85.0, 85.0))
        val liste = mutableListOf<Pair<Int, Int>>()
        for (x in x0..x1) for (y in y0..y1) {
            liste.add(x to y)
            if (liste.size >= MAX_TUILES) return liste
        }
        return liste
    }

    private fun points(ligne: List<DoubleArray>, x: Int, y: Int): List<Point> {
        val (sud, ouest, nord, est) = bornes(x, y)
        val my0 = mercatorY(sud)
        val my1 = mercatorY(nord)
        return ligne.map { p ->
            val lon = ouest + p[0] / ETENDUE * (est - ouest)
            val my = my1 - p[1] / ETENDUE * (my1 - my0)
            val lat = Math.toDegrees(2 * atan(exp(my / RAYON)) - PI / 2)
            Point(lat, lon)
        }
    }

    companion object {
        const val ZOOM = 14
        const val ETENDUE = 4096
        const val RAYON = 6378137.0
        const val MAX_TUILES = 256

        /** Les bornes (sud, ouest, nord, est) d'une tuile XYZ du zoom 14. */
        fun bornes(x: Int, y: Int): Zone {
            val n = 1 shl ZOOM
            val ouest = x.toDouble() / n * 360 - 180
            val est = (x + 1).toDouble() / n * 360 - 180
            val sud = Math.toDegrees(atan(sinh(PI * (1 - 2.0 * (y + 1) / n))))
            val nord = Math.toDegrees(atan(sinh(PI * (1 - 2.0 * y / n))))
            return Zone(sud, ouest, nord, est)
        }

        fun xDeLon(lon: Double): Int =
            floor((lon + 180) / 360 * (1 shl ZOOM)).toInt().coerceIn(0, (1 shl ZOOM) - 1)

        fun yDeLat(lat: Double): Int =
            floor((1 - asinh(tan(Math.toRadians(lat))) / PI) / 2 * (1 shl ZOOM)).toInt()
                .coerceIn(0, (1 shl ZOOM) - 1)

        fun mercatorY(lat: Double): Double = RAYON * kotlin.math.ln(tan(PI / 4 + Math.toRadians(lat) / 2))
    }
}
