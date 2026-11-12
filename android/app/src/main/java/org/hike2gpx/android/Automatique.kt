package org.hike2gpx.android

import java.io.File

/**
 * Ce qui se télécharge de soi-même, comme sur le PC (application._lots_a_telecharger) :
 * le lot du serveur de chaque case que touche un parcours, quand il manque sur
 * le téléphone ou que le dépôt en a un plus récent. Une case refusée ou en
 * échec n'est pas reprise tant qu'elle figure dans exclues.
 */
fun lotsATelecharger(offres: List<Offre>, installes: List<Lot>, zone: Zone, exclues: Set<String>): List<Offre> {
    val parCase = installes.associateBy { it.case }
    return offres.filter { offre ->
        val lot = offre.lot
        val couverture = lot.couverture
        val present = parCase[lot.case]
        lot.case !in exclues && couverture != null && zone.touche(couverture) &&
            (present == null || plusRecent(lot, present))
    }
}

/**
 * L'offre du lot qui couvre le centre de la vue, s'il manque ou si le
 * catalogue en a un plus récent ; null sinon. C'est le lot que lit le calque
 * de la carte : afficher un calque est un usage réel de la région, comme sur
 * le PC (`application._lot_automatique` appelé par `calque_osm`).
 */
fun offreAuCentre(offres: List<Offre>, installes: List<Lot>, zone: Zone, exclues: Set<String>): Offre? {
    val lat = (zone.sud + zone.nord) / 2
    val lon = (zone.ouest + zone.est) / 2
    val parCase = installes.associateBy { it.case }
    return offres.filter { offre ->
        val couverture = offre.lot.couverture
        offre.lot.case !in exclues && couverture != null &&
            lat in couverture[0]..couverture[2] && lon in couverture[1]..couverture[3] &&
            (parCase[offre.lot.case]?.let { plusRecent(offre.lot, it) } ?: true)
    }.minByOrNull { if (it.lot.osm) 1 else 0 }
}

/** La zone de routage installée qui couvre ce point, ou null : sans elle, le téléphone ne peut pas calculer ici. */
fun lotAuPoint(installes: List<Lot>, lat: Double, lon: Double): Lot? = installes.firstOrNull { lot ->
    lot.couverture?.let { c -> lat in c[0]..c[2] && lon in c[1]..c[3] } == true
}

/** La zone a-t-elle une partie commune avec la boîte [sud, ouest, nord, est] ? (hors_ligne.touche) */
fun Zone.touche(boite: List<Double>): Boolean =
    sud < boite[2] && boite[0] < nord && ouest < boite[3] && boite[1] < est

/**
 * Les fonds de carte d'un PC (les listes « fonds » et « cartes » de son
 * catalogue), rangés comme sur le PC (hors_ligne.dossier_fonds) :
 *
 *   hors-ligne/fonds/E5_N40-scan25.mbtiles, E5_N40-scan25-vue-3fa2c1.mbtiles,
 *   E5_N40-osm.map
 *
 * Le nom suit le contrat du partage (docs/architecture/partage-telephone.md) :
 * <case>-<source>, et -vue-<empreinte> pour une vue ; la source se lit donc
 * dans le nom, sans ouvrir le fichier. Un .map est une carte vectorielle
 * Mapsforge, un .mbtiles un fond en images.
 */
class Fonds(horsLigne: File) {
    val dossier = File(horsLigne, "fonds")

    fun installes(): List<File> =
        (dossier.listFiles() ?: emptyArray())
            .filter { it.isFile && (it.name.endsWith(".mbtiles") || it.name.endsWith(".map")) }
            .sortedBy { it.name }

    /** Les fonds installés, groupés par source : un seul fond affiché par source, toutes cases confondues. */
    fun parSource(): Map<String, List<File>> = installes().groupBy { source(it.nameWithoutExtension) }

    /** Range un fond téléchargé, déjà vérifié par son SHA-256. */
    fun installer(telecharge: File, fond: Fond): File {
        dossier.mkdirs()
        val cible = File(dossier, "${Catalogue.nomSur(fond.nom)}${fond.extension}")
        cible.delete()
        if (!telecharge.renameTo(cible)) {
            telecharge.copyTo(cible, overwrite = true)
            telecharge.delete()
        }
        return cible
    }

    companion object {
        /** La clé d'un fond reçu d'un PC, distincte de la carte en ligne du même nom. */
        fun cle(source: String): String = PREFIXE + source

        /** La source d'un fond reçu d'un PC, ou null pour une carte en ligne. */
        fun sourceDeCle(cle: String): String? =
            if (cle.startsWith(PREFIXE)) cle.removePrefix(PREFIXE).takeIf { it.isNotEmpty() } else null

        private const val PREFIXE = "pc:"

        /** E5_N40-scan25-vue-3fa2c1 -> scan25 ; un nom hors contrat est sa propre source. */
        fun source(nom: String): String = nom.split('-').getOrNull(1)?.takeIf { it.isNotEmpty() } ?: nom

        /** Le nom lisible d'une source de fond, comme la page du PC. */
        fun titre(source: String): String = TITRES[source] ?: source

        private val TITRES = mapOf(
            "osm" to "OpenStreetMap",
            "scan25" to "SCAN 25 (IGN)",
            "plan" to "Plan IGN",
            "allemagne" to "TopPlusOpen (BKG)",
            "espagne" to "MTN (IGN España)",
            "norvege" to "Toporaster (Kartverket)",
            "paysBas" to "BRT Achtergrondkaart (PDOK)",
        )
    }
}

/**
 * Les fonds que proposent les PC et qui manquent sur le téléphone, un par nom
 * (le premier PC qui le sert). Fonds en images (« fonds ») et cartes
 * vectorielles (« cartes ») se mélangent ici : le nom et l'URL disent le
 * format au moment du téléchargement. Un fond ne vient jamais de GitHub : une
 * publication n'a ni « fonds » ni « cartes ».
 */
fun fondsProposes(catalogues: List<Pair<Source, Catalogue>>, installes: Set<String>): List<Pair<Source, Fond>> {
    val vus = LinkedHashMap<String, Pair<Source, Fond>>()
    for ((source, catalogue) in catalogues)
        for (fond in catalogue.fonds + catalogue.cartes)
            if (fond.nom !in installes && fond.nom !in vus) vus[fond.nom] = source to fond
    return vus.values.sortedBy { it.second.nom }
}
