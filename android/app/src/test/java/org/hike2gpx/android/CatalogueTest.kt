package org.hike2gpx.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.time.Instant

class CatalogueTest {
    /** Le catalogue publié sur GitHub le 28 octobre 2026, tel quel. */
    private val github = """
        {"format": 1, "genere": "2026-10-28T01:15:06Z", "lots": [{
          "case": "E5_N40", "type": "enrichi", "format": 3, "fournisseurs": ["ign"],
          "zone": [40, 5, 45, 10], "emprise_enrichie": [40, 5, 45, 10],
          "sources": {"osm": "2026-10-26T21:24:46Z", "bdtopo": "2026-09-15", "relief": "Mapterhorn, zoom 12"},
          "octets": 247368844,
          "fichiers": [
            {"nom": "E5_N40.rd5", "octets": 75768822, "sha256": "98d335ee3caec9adbad1ce6577f3cee128ffd4e385779712a09436d83a620d36", "url": "E5_N40.E5_N40.rd5"},
            {"nom": "franchissements.json.gz", "octets": 3146993, "sha256": "38290ddb01e15626b6f0e5f02387fa72a95fb4bf8f1f25ec04c1bc99a33bc25b", "url": "E5_N40.franchissements.json.gz"},
            {"nom": "calques.mbtiles", "octets": 168452096, "sha256": "abbacbc446a8b9c69984ace9549c8197bca74cc6d7c2c2a6c013383a1a051747", "url": "E5_N40.calques.mbtiles"},
            {"nom": "manifest.json", "octets": 933, "sha256": "d21d7e3c7c90ef60aae0a7934f3d1c359255dd0f52145513479cdeda865ec603", "url": "E5_N40.manifest.json"}]}]}
    """.trimIndent()

    @Test fun lit_le_catalogue_de_github() {
        val c = Catalogue.lire(github)
        assertEquals(1, c.lots.size)
        val lot = c.lots[0]
        assertEquals("E5_N40", lot.case)
        assertEquals(listOf(40.0, 5.0, 45.0, 10.0), lot.couverture)
        assertEquals(247368844L, lot.octets)
        assertEquals(4, lot.fichiers.size)
        assertEquals("E5_N40.E5_N40.rd5", lot.fichiers[0].url)
        assertEquals(Instant.parse("2026-10-26T21:24:46Z"), lot.editionOsm)
        assertEquals("2026-09-15", lot.sources["bdtopo"])
        assertTrue(c.fonds.isEmpty())
    }

    @Test fun lit_les_fonds_d_un_pc() {
        val c = Catalogue.lire("""{"format": 1, "lots": [], "fonds": [{"nom": "france.mbtiles", "zone": [41, -5, 51, 10],
            "zoom": 14, "source": "OpenFreeMap", "octets": 12, "sha256": "${"a".repeat(64)}", "url": "fonds/france.mbtiles"}]}""")
        assertEquals(1, c.fonds.size)
        assertEquals("france.mbtiles", c.fonds[0].nom)
        assertEquals("14", c.fonds[0].zoom)
        assertEquals("fonds/france.mbtiles", c.fonds[0].url)
    }

    @Test fun refuse_un_autre_format() {
        for (texte in listOf("""{"format": 2, "lots": []}""", """{"format": 1}""", "pas du json", "[]")) {
            try {
                Catalogue.lire(texte)
                fail(texte)
            } catch (e: ErreurDepot) {
            }
        }
    }

    @Test fun jamais_de_chemin_venu_du_catalogue() {
        assertEquals("E5_N40.rd5", Catalogue.nomSur("../../E5_N40.rd5"))
        assertEquals("x.rd5", Catalogue.nomSur("a\\b\\x.rd5"))
        for (nom in listOf("", "a/..", "/")) {
            try {
                Catalogue.nomSur(nom); fail(nom)
            } catch (e: ErreurDepot) {
            }
        }
    }

    @Test fun refuse_une_case_ou_une_empreinte_invalide() {
        val mauvais = listOf(github.replace("\"E5_N40\", \"type\"", "\"../x\", \"type\""),
            github.replace("98d335ee", "XYZ"))
        for (texte in mauvais) {
            try {
                Catalogue.lire(texte); fail()
            } catch (e: ErreurDepot) {
            }
        }
    }

    @Test fun dates_au_jour_ou_absentes() {
        assertEquals(Instant.parse("2026-09-15T00:00:00Z"), date("2026-09-15"))
        assertNull(date(null))
        assertNull(date("Mapterhorn"))
    }
}
