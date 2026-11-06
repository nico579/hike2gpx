package org.hike2gpx.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException

/**
 * La recherche de ville de la page : communes françaises d'abord, Nominatim
 * pour le reste du monde, et les coordonnées acceptées comme saisie. Les
 * réponses sont des textes figés : aucun réseau pendant les tests.
 */
class CommunesTest {

    private val communes = """
        [
          {"nom":"Grasse","code":"06069",
           "centre":{"type":"Point","coordinates":[6.9225,43.6584]},
           "departement":{"nom":"Alpes-Maritimes"}},
          {"nom":"Grasse","code":"06070",
           "centre":{"type":"Point","coordinates":[6.9,43.6]},
           "departement":{"nom":"Var"}}
        ]
    """.trimIndent()

    private val monde = """
        [
          {"name":"Madrid","lat":"40.4168","lon":"-3.7038",
           "address":{"state":"Madrid","country":"Espagne","country_code":"es"}},
          {"name":"Barcelone","lat":"41.3825","lon":"2.1769",
           "address":{"state":"Catalogne","country":"Espagne","country_code":"es"}}
        ]
    """.trimIndent()

    @Test fun les_coordonnees_de_la_page_sont_reconnues() {
        assertEquals(43.285 to 6.04, Communes.lireCoordonnees("43.285, 6.040"))
        assertEquals(43.285 to 6.04, Communes.lireCoordonnees("43,285;6,040"))
        assertEquals(43.285 to 6.04, Communes.lireCoordonnees("43.285 6.040"))
        assertEquals(null, Communes.lireCoordonnees("Grasse"))
        assertEquals(null, Communes.lireCoordonnees("91, 0"))
        assertEquals(null, Communes.lireCoordonnees("0, 181"))
        assertEquals(null, Communes.lireCoordonnees("1,2,3"))
    }

    @Test fun les_communes_francaises_donnent_leur_departement() {
        val villes = Communes.communesFrancaises(communes)
        assertEquals(2, villes.size)
        assertEquals("Grasse", villes[0].nom)
        assertEquals("Alpes-Maritimes", villes[0].detail)
        assertEquals(43.6584, villes[0].lat, 0.0)
        assertEquals(6.9225, villes[0].lon, 0.0)
    }

    @Test fun nominatim_donne_la_region_et_le_pays() {
        val villes = Communes.lieuxDuMonde(monde)
        assertEquals(2, villes.size)
        assertEquals("Madrid", villes[0].nom)
        assertEquals("Madrid, Espagne", villes[0].detail)
        assertEquals(40.4168, villes[0].lat, 0.0)
        assertEquals(-3.7038, villes[0].lon, 0.0)
    }

    @Test fun la_france_repond_avant_le_reste_du_monde() {
        val appels = mutableListOf<String>()
        val villes = Communes.chercher("Grasse") { url ->
            appels.add(url)
            if (url.startsWith(Communes.API_COMMUNES)) communes else monde
        }
        assertEquals(1, appels.size)
        assertTrue(appels[0].startsWith(Communes.API_COMMUNES))
        assertEquals("Grasse", villes[0].nom)
    }

    @Test fun si_la_france_echoue_le_monde_prend_le_relais() {
        val appels = mutableListOf<String>()
        val villes = Communes.chercher("Madrid") { url ->
            appels.add(url)
            if (url.startsWith(Communes.API_COMMUNES)) throw IOException("service indisponible")
            monde
        }
        assertEquals(2, appels.size)
        assertTrue(appels[1].startsWith(Communes.API_NOMINATIM))
        assertEquals("Madrid", villes[0].nom)
        assertEquals("Madrid, Espagne", villes[0].detail)
    }

    @Test fun la_correspondance_exacte_passe_devant() {
        val exacte = """
            [{"nom":"Grasse-la-Bastide","centre":{"coordinates":[6.0,43.0]},"departement":{"nom":"Var"}},
             {"nom":"Grasse","centre":{"coordinates":[6.9,43.6]},"departement":{"nom":"Alpes-Maritimes"}}]
        """.trimIndent()
        assertEquals("Grasse-la-Bastide", Communes.communesFrancaises(exacte)[0].nom)
        assertEquals("Grasse", Communes.chercher("Grasse") { exacte }.first().nom)
    }

    @Test fun une_recherche_trop_courte_est_refusee() {
        try {
            Communes.chercher("M") { communes }
            throw AssertionError("une recherche d'un caractère doit être refusée")
        } catch (e: ErreurRecherche) {
            assertTrue(e.message!!.contains("deux"))
        }
    }
}
