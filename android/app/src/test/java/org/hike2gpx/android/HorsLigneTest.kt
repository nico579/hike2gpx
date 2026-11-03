package org.hike2gpx.android

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.io.StringReader
import java.util.zip.GZIPOutputStream

class HorsLigneTest {
    @get:Rule val dossier = TemporaryFolder()

    private val franchissements = """[
        {"cle": "a", "statut": "uncertain", "lat": 43.46, "lon": 6.05, "voies": [1],
         "coupes": [[[6.0500001, 43.4600001], [6.0500002, 43.4600002]]]},
        {"cle": "b", "statut": "blocked", "lat": 43.461, "lon": 6.051, "nature": "Portail",
         "coupes": [[[6.051, 43.461], [6.0511, 43.4611]], [[6.0512, 43.4612], [6.0513, 43.4613]]]},
        {"cle": "c", "statut": "blocked", "lat": 44.9, "lon": 9.9, "coupes": [[[9.9, 44.9], [9.91, 44.91]]]}]"""

    /** Un lot complet dans un dossier de téléchargement, avec son manifeste. */
    private fun lot(type: String = "enrichi", altere: Boolean = false): File {
        val source = dossier.newFolder()
        File(source, "E5_N40.rd5").writeBytes(ByteArray(1000) { it.toByte() })
        GZIPOutputStream(File(source, "franchissements.json.gz").outputStream()).use { it.write(franchissements.toByteArray()) }
        File(source, "calques.mbtiles").writeText("tuiles")
        val fichiers = JSONArray()
        for (nom in listOf("E5_N40.rd5", "franchissements.json.gz", "calques.mbtiles")) {
            val f = File(source, nom)
            fichiers.put(JSONObject().put("nom", nom).put("octets", f.length()).put("sha256", empreinte(f)))
        }
        File(source, "manifest.json").writeText(JSONObject().put("format", 3).put("case", "E5_N40").put("type", type)
            .put("zone", JSONArray(listOf(40, 5, 45, 10))).put("emprise_enrichie", JSONArray(listOf(43, 5, 44, 7)))
            .put("sources", JSONObject().put("osm", "2026-10-26T21:24:46Z")).put("fichiers", fichiers).toString())
        if (altere) File(source, "calques.mbtiles").writeText("tuileS")
        return source
    }

    @Test fun installe_et_range_comme_le_pc() {
        val h = HorsLigne(dossier.newFolder())
        val installe = h.installer(lot())
        assertEquals("E5_N40", installe.case)
        assertTrue(File(h.segments, "E5_N40.rd5").isFile)
        assertTrue(File(h.racine, "E5_N40/manifest.json").isFile)
        assertTrue(File(h.racine, "E5_N40/franchissements.json.gz").isFile)
        assertTrue(File(h.racine, "E5_N40/calques.mbtiles").isFile)
        assertFalse(File(h.racine, "E5_N40/E5_N40.rd5").exists())
        assertEquals(listOf("E5_N40"), h.lots().map { it.case })
    }

    @Test fun lot_osm_dans_ses_propres_segments() {
        val h = HorsLigne(dossier.newFolder())
        h.installer(lot("enrichi"))
        h.installer(lot("osm"))
        assertTrue(File(h.segmentsOsm, "E5_N40.rd5").isFile)
        assertFalse(File(h.segments, "E5_N40.rd5").exists())     // l'ancienne RD5 enrichie ne sert plus
    }

    @Test fun refuse_un_fichier_altere() {
        val h = HorsLigne(dossier.newFolder())
        try {
            h.installer(lot(altere = true)); fail()
        } catch (e: ErreurLot) {
            assertTrue(e.message!!.contains("calques.mbtiles"))
        }
        assertTrue(h.lots().isEmpty())
    }

    @Test fun lot_couvrant_selon_son_genre() {
        val h = HorsLigne(dossier.newFolder())
        h.installer(lot("enrichi"))
        assertEquals("E5_N40", h.lotCouvrant(Zone(43.4, 6.0, 43.5, 6.1))?.case)
        assertNull(h.lotCouvrant(Zone(42.0, 6.0, 42.1, 6.1)))           // hors de l'emprise enrichie
        h.installer(lot("osm"))
        assertEquals("E5_N40", h.lotCouvrant(Zone(42.0, 6.0, 42.1, 6.1))?.case)   // un lot OSM couvre sa zone
    }

    @Test fun franchissements_de_la_zone() {
        val h = HorsLigne(dossier.newFolder())
        val installe = h.installer(lot())
        val liste = h.franchissements(installe, Zone(43.4, 6.0, 43.5, 6.1))
        assertEquals(listOf("uncertain", "blocked"), liste.map { it.statut })
        assertEquals(2, liste[1].coupes.size)
    }

    @Test fun polylines_comme_brouter_requete() {
        val liste = HorsLigne.lireFranchissements(StringReader(franchissements), Zone(43.0, 6.0, 44.0, 7.0))
        // Les coupes pondérées d'abord, les interdites en dernier (audit B10).
        assertEquals("6.0500001,43.4600001,6.0500002,43.4600002,300|" +
            "6.0510000,43.4610000,6.0511000,43.4611000|6.0512000,43.4612000,6.0513000,43.4613000",
            HorsLigne.polylines(liste, strict = false))
        // En mode strict, tout est interdit : plus aucun poids.
        assertEquals("6.0500001,43.4600001,6.0500002,43.4600002|" +
            "6.0510000,43.4610000,6.0511000,43.4611000|6.0512000,43.4612000,6.0513000,43.4613000",
            HorsLigne.polylines(liste, strict = true))
        assertEquals("", HorsLigne.polylines(emptyList(), strict = false))
    }

    @Test fun zone_autour_des_points() {
        val z = Zone.autour(listOf(Point(43.458, 6.045), Point(43.465, 6.055)))
        assertEquals(43.448, z.sud, 1e-9)
        assertEquals(43.475, z.nord, 1e-9)
        assertTrue(z.ouest < 6.045 - 0.01 && z.est > 6.055 + 0.01)
    }

    @Test fun controle_des_coupes_traversees() {
        val trace = JSONArray("[[6.0, 43.0], [6.002, 43.0]]")
        val coupe = Franchissement(43.0, 6.001, "blocked", listOf(listOf(doubleArrayOf(6.001, 42.999), doubleArrayOf(6.001, 43.001))))
        val aVerifier = coupe.copy(statut = "uncertain")
        assertEquals(coupe, Itineraire.traverses(trace, listOf(coupe), strict = false))
        assertNull(Itineraire.traverses(trace, listOf(aVerifier), strict = false))
        assertEquals(aVerifier, Itineraire.traverses(trace, listOf(aVerifier), strict = true))
        assertTrue(Itineraire.contient(Zone(42.0, 5.0, 44.0, 7.0), Itineraire.etendue(trace)))
        assertFalse(Itineraire.contient(Zone(43.0, 5.0, 44.0, 7.0), Itineraire.etendue(trace)))
    }

    @Test fun gpx() {
        val gpx = Gpx.ecrire(JSONArray("[[6.0, 43.0, 120.5], [6.1, 43.1]]"))
        assertTrue(gpx.contains("<trkpt lat=\"43.0\" lon=\"6.0\"><ele>120.5</ele></trkpt>"))
        assertTrue(gpx.contains("<trkpt lat=\"43.1\" lon=\"6.1\"></trkpt>"))
    }
}
