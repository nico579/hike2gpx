package org.hike2gpx.android

import org.junit.Assert.assertEquals
import org.junit.Test
import java.io.File

/**
 * Le pays du centre de la carte commande la carte nationale, comme sur le PC :
 * l'IGN en France, swisstopo en Suisse, et aucune carte française de l'autre
 * côté de la frontière. Les contours lus sont ceux de l'APK.
 */
class PaysTest {

    private val pays = Pays(File("src/main/assets/pays.txt").readText())

    private fun verifier(lat: Double, lon: Double, attendu: String) =
        assertEquals("($lat, $lon)", attendu, pays.de(lat, lon))

    @Test fun chaque_carte_nationale_a_son_pays() {
        verifier(48.8566, 2.3522, "fr")       // Paris
        verifier(46.2044, 6.1432, "ch")       // Genève
        verifier(47.5596, 7.5886, "ch")       // Bâle
        verifier(47.9948, 7.8498, "de")       // Fribourg-en-Brisgau
        verifier(47.8095, 13.055, "at")       // Salzbourg
        verifier(50.0755, 14.4378, "cz")      // Prague
        verifier(40.4168, -3.7038, "es")      // Madrid
        verifier(49.6117, 6.13, "lu")         // Luxembourg
        verifier(52.3676, 4.9041, "nl")       // Amsterdam
        verifier(59.9139, 10.7522, "no")      // Oslo
        verifier(39.7392, -104.9903, "us")    // Denver
        verifier(52.2297, 21.0122, "pl")      // Varsovie
    }

    @Test fun la_frontiere_suit_la_carte_et_non_la_region() {
        verifier(46.238, 6.109, "ch")         // Genève, rive gauche
        verifier(46.195, 6.235, "fr")         // Saint-Julien, juste à côté
        verifier(47.594, 7.62, "de")          // Weil am Rhein, face à Bâle
        verifier(43.6047, 1.4442, "fr")       // Toulouse
        verifier(42.6977, 2.8954, "fr")       // Perpignan
    }

    @Test fun ailleurs_la_carte_reste_sur_osm() {
        verifier(41.9028, 12.4964, Pays.AUTRE)   // Rome
        verifier(50.8503, 4.3517, Pays.AUTRE)    // Bruxelles
        verifier(64.1466, -21.9426, Pays.AUTRE)  // Reykjavik
        verifier(46.948, 7.4474, "ch")           // Berne
    }
}
