package org.hike2gpx.android

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.fail
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File
import java.util.zip.ZipEntry
import java.util.zip.ZipInputStream
import java.util.zip.ZipOutputStream

/** L'archive zip des cases, celle d'archive.py sur le PC. */
class ArchiveTest {
    @get:Rule val dossier = TemporaryFolder()

    /** Un appareil avec la zone E5_N40 et la carte N43E006-scan25. */
    private fun appareil(): Triple<HorsLigne, Fonds, File> {
        val h = HorsLigne(dossier.newFolder())
        val source = dossier.newFolder()
        File(source, "E5_N40.rd5").writeBytes(ByteArray(5000) { (it * 7).toByte() })
        File(source, "calques.mbtiles").writeText("tuiles")
        val fichiers = JSONArray()
        for (nom in listOf("E5_N40.rd5", "calques.mbtiles")) {
            val f = File(source, nom)
            fichiers.put(JSONObject().put("nom", nom).put("octets", f.length()).put("sha256", empreinte(f)))
        }
        File(source, "manifest.json").writeText(JSONObject().put("format", 3).put("case", "E5_N40").put("type", "osm")
            .put("zone", JSONArray(listOf(40, 5, 45, 10))).put("fichiers", fichiers).toString())
        h.installer(source)
        val fonds = Fonds(h.racine)
        fonds.dossier.mkdirs()
        val carte = File(fonds.dossier, "N43E006-scan25.mbtiles").apply { writeBytes(ByteArray(3000) { it.toByte() }) }
        return Triple(h, fonds, carte)
    }

    private fun exporter(h: HorsLigne, carte: File): ByteArray =
        ByteArrayOutputStream().also { Archive.ecrire(it, h.lots(), h, listOf(carte)) }.toByteArray()

    @Test fun exportee_puis_importee_a_l_identique_sur_un_autre_appareil() {
        val (h, _, carte) = appareil()
        val octets = exporter(h, carte)
        val noms = ZipInputStream(ByteArrayInputStream(octets)).use { z ->
            generateSequence { z.nextEntry?.name }.toList()
        }
        assertEquals("catalog.json", noms.first())
        assertEquals(setOf("E5_N40/E5_N40.rd5", "E5_N40/calques.mbtiles", "E5_N40/manifest.json",
            "fonds/N43E006-scan25.mbtiles"), noms.drop(1).toSet())

        val ami = HorsLigne(dossier.newFolder())
        val fondsAmi = Fonds(ami.racine)
        val r = Archive.importer(ByteArrayInputStream(octets), ami, fondsAmi, dossier.newFolder())
        assertEquals(listOf("E5_N40"), r.lots)
        assertEquals(listOf("N43E006-scan25"), r.fonds)
        assertEquals(listOf("E5_N40"), ami.lots().map { it.case })
        assertArrayEquals(File(h.segmentsOsm, "E5_N40.rd5").readBytes(), File(ami.segmentsOsm, "E5_N40.rd5").readBytes())
        assertArrayEquals(carte.readBytes(), File(fondsAmi.dossier, "N43E006-scan25.mbtiles").readBytes())
    }

    @Test fun un_fichier_altere_est_refuse_et_rien_ne_reste() {
        val (h, _, carte) = appareil()
        val sortie = ByteArrayOutputStream()
        // L'archive réécrite, la carte augmentée d'un octet.
        ZipInputStream(ByteArrayInputStream(exporter(h, carte))).use { entree ->
            ZipOutputStream(sortie).use { z ->
                while (true) {
                    val e = entree.nextEntry ?: break
                    val contenu = entree.readBytes()
                    z.putNextEntry(ZipEntry(e.name))
                    z.write(if (e.name.startsWith("fonds/")) contenu + 1 else contenu)
                    z.closeEntry()
                }
            }
        }
        val ami = HorsLigne(dossier.newFolder())
        val travail = dossier.newFolder()
        try {
            Archive.importer(ByteArrayInputStream(sortie.toByteArray()), ami, Fonds(ami.racine), travail)
            fail("une carte altérée ne doit pas s'installer")
        } catch (e: ErreurLot) {
            assertEquals(R.string.err_fichier_taille, e.texte)
        }
        assertEquals(emptyList<File>(), Fonds(ami.racine).installes())
        assertFalse(travail.exists())
    }

    @Test fun un_zip_sans_catalogue_en_tete_n_est_pas_une_archive() {
        val sortie = ByteArrayOutputStream()
        ZipOutputStream(sortie).use { z -> z.putNextEntry(ZipEntry("photo.jpg")); z.write(1); z.closeEntry() }
        val h = HorsLigne(dossier.newFolder())
        try {
            Archive.importer(ByteArrayInputStream(sortie.toByteArray()), h, Fonds(h.racine), dossier.newFolder())
            fail("pas de catalogue, pas d'import")
        } catch (e: ErreurDepot) {
            assertEquals(R.string.err_archive_catalogue, e.texte)
        }
    }

    @Test fun le_nom_propose_dit_la_premiere_case_et_le_nombre() {
        assertEquals("hike2gpx-N43E006-scan25.zip", Archive.nomPropose(listOf("N43E006-scan25")))
        assertEquals("hike2gpx-E5_N40-et-2.zip", Archive.nomPropose(listOf("E5_N40", "a", "b")))
    }
}
