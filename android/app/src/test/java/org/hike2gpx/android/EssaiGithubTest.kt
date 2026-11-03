package org.hike2gpx.android

import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

/**
 * De bout en bout contre le vrai dépôt GitHub : catalogue, téléchargement du
 * lot E5_N40 interrompu puis repris, installation, itinéraire hors ligne. Le
 * lot pèse 250 Mo : l'essai ne tourne que si HIKE2GPX_ESSAI_GITHUB donne un
 * dossier de travail, gardé d'une fois sur l'autre (la reprise y sert aussi).
 */
class EssaiGithubTest {
    @Test fun lot_de_github_jusqu_a_l_itineraire() {
        val dossier = System.getenv("HIKE2GPX_ESSAI_GITHUB")?.let(::File)
        assumeTrue("HIKE2GPX_ESSAI_GITHUB non définie", dossier != null)
        val depot = Depot()
        val lot = depot.lireCatalogue(Source.GITHUB).lots.first { it.case == "E5_N40" }
        val travail = File(dossier, "telechargements/E5_N40")
        val horsLigne = HorsLigne(dossier!!)
        if (horsLigne.lots().none { it.case == lot.case && it.sources == lot.sources }) {
            // Une coupure volontaire après 5 Mo, puis la reprise.
            var recus = 0L
            try {
                depot.telecharger(lot, Source.GITHUB, travail, { faits, _ -> recus = faits }, { recus < 5_000_000 })
                if (travail.listFiles()!!.sumOf { it.length() } < lot.octets) fail("pas d'interruption")
            } catch (e: Abandon) {
            }
            depot.telecharger(lot, Source.GITHUB, travail)
            horsLigne.installer(travail)
            travail.deleteRecursively()
        }
        val routeur = Routeur(File("src/main/assets/brouter"))
        val resultat = Itineraire(horsLigne, routeur)
            .calculer(listOf(Point(43.458, 6.045), Point(43.465, 6.055)), strict = false, officiels = true, memoireMo = 256)
        println("Itinéraire : ${resultat.coordonnees.length()} points, ${resultat.franchissements.size} franchissements, " +
            "${resultat.feature.getJSONObject("properties").optString("track-length")} m")
        assertTrue(resultat.coordonnees.length() > 2)
        val sansOfficiels = Itineraire(horsLigne, routeur)
            .calculer(listOf(Point(43.458, 6.045), Point(43.465, 6.055)), strict = true, officiels = false, memoireMo = 256)
        assertTrue(sansOfficiels.coordonnees.length() > 2)
    }
}
