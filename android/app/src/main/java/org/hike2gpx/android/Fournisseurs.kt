package org.hike2gpx.android

/**
 * Un fournisseur national de chemins, nommé comme sur le PC (providers.py) :
 * « IGN BD TOPO » pour la France, ATKIS pour l'Allemagne, etc. Le calque est
 * celui des tuiles du lot (`troncons_<calque>`) ; `court` est le nom de la
 * coche de la page Cartes. Son pays borne sa coche : un lot frontalier peut
 * contenir l'IGN et swissTLM3D, mais Genève ne montre que swissTLM3D.
 */
data class Fournisseur(val cle: String, val calque: String, val nom: String,
    val court: String = nom, val pays: String? = null)

object Fournisseurs {
    val TOUS = listOf(
        Fournisseur("ign", "bdtopo", "IGN BD TOPO", "IGN", "fr"),
        Fournisseur("atkis", "atkis", "ATKIS", pays = "de"),
        Fournisseur("zabaged", "zabaged", "ZABAGED", pays = "cz"),
        Fournisseur("swisstlm3d", "swisstlm3d", "swissTLM3D", pays = "ch"),
        Fournisseur("bdot10k_ds", "bdot10k_ds", "BDOT10k", pays = "pl"),
    )

    /** Un fournisseur du manifeste ; un futur fournisseur garde sa clé comme calque. */
    fun deCle(cle: String): Fournisseur =
        TOUS.firstOrNull { it.cle == cle } ?: Fournisseur(cle, cle, cle)

    /** Le fournisseur d'une couche `troncons_<calque>` ; inconnu, il garde son nom de calque. */
    fun deCalque(calque: String): Fournisseur =
        TOUS.firstOrNull { it.calque == calque } ?: Fournisseur(calque, calque, calque)

    /**
     * Les fournisseurs qu'un lot retient. Un lot de format 2 ne nomme pas ses
     * fournisseurs et n'a qu'une couche `troncons`, celle de la BD TOPO.
     */
    fun duLot(lot: Lot): List<Fournisseur> =
        lot.fournisseurs.map(::deCle).ifEmpty {
            if (!lot.osm && (lot.format ?: 2) < 3) listOf(deCle("ign")) else emptyList()
        }
}
