package org.hike2gpx.android

// généré par tools/generer_legende.py depuis hike2gpx/assets/legende.json : ne pas modifier à la main

enum class FormeLegende { TRAIT, TIRETS, PASTILLE }

/**
 * Une ligne de la légende. [texte] est la chaîne de ressource ; elle prend le nom du
 * réseau du pays (IGN, ATKIS…) en %1$s quand son identifiant est « chemins_officiels ».
 */
data class EntreeLegende(
    val id: String,
    val forme: FormeLegende,
    val couleur: Int,
    val contour: Int?,
    val epaisseur: Float,
    val texte: Int,
)

object LegendeGeneree {
    val ENTREES = listOf(
        EntreeLegende("osm", FormeLegende.TIRETS, 0xff7b1fa2.toInt(), null, 3f, R.string.legende_osm),
        EntreeLegende("chemins_officiels", FormeLegende.TIRETS, 0xff00897b.toInt(), null, 3f, R.string.legende_chemins_officiels),
        EntreeLegende("itineraire", FormeLegende.TRAIT, 0xff1565c0.toInt(), null, 4f, R.string.legende_itineraire),
        EntreeLegende("barriere", FormeLegende.TRAIT, 0xffe53935.toInt(), null, 3f, R.string.legende_barriere),
        EntreeLegende("bloque", FormeLegende.PASTILLE, 0xffd32f2f.toInt(), null, 0f, R.string.legende_bloque),
        EntreeLegende("verifier", FormeLegende.PASTILLE, 0xffef6c00.toInt(), null, 0f, R.string.legende_verifier),
        EntreeLegende("jonction", FormeLegende.PASTILLE, 0xfffdd835.toInt(), 0xff4e342e.toInt(), 0f, R.string.legende_jonction),
    )
}
