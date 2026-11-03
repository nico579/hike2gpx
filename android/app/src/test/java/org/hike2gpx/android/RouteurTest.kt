package org.hike2gpx.android

import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

/**
 * Essai du vrai BRouter, compilé avec l'application, sur une RD5 du PC. Une
 * RD5 pèse des dizaines de Mo : elle n'est pas dans le dépôt, l'essai ne tourne
 * que si une variable d'environnement donne son dossier, par exemple
 *
 *   HIKE2GPX_SEGMENTS_OSM=%LOCALAPPDATA%\hike2gpx-data\brouter\segments4   (RD5 officielle E5_N40)
 *   HIKE2GPX_SEGMENTS_ENRICHIS=…\hors-ligne\segments                        (RD5 enrichie E5_N40)
 */
class RouteurTest {
    private val profils = File("src/main/assets/brouter")
    private val points = listOf(Point(43.458, 6.045), Point(43.465, 6.055))

    private fun essai(variable: String, enrichi: Boolean) {
        val segments = System.getenv(variable)?.let(::File)
        assumeTrue("$variable non définie", segments != null && File(segments, "E5_N40.rd5").isFile)
        val routeur = Routeur(profils)
        val libre = routeur.calculer(segments!!, enrichi, points, "")
        val coords = libre.getJSONObject("geometry").getJSONArray("coordinates")
        assertTrue(coords.length() > 2)
        // Le départ enfermé dans un carré de coupes interdites : plus d'itinéraire.
        val enclos = "6.042,43.455,6.048,43.455,6.048,43.461,6.042,43.461,6.042,43.455"
        try {
            routeur.calculer(segments, enrichi, points, enclos)
            throw AssertionError("le mur a été traversé")
        } catch (e: ErreurCalcul) {
        }
    }

    @Test fun calcule_sur_une_rd5_officielle() = essai("HIKE2GPX_SEGMENTS_OSM", enrichi = false)

    @Test fun calcule_sur_une_rd5_enrichie() = essai("HIKE2GPX_SEGMENTS_ENRICHIS", enrichi = true)
}
