package org.hike2gpx.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.nio.ByteBuffer
import java.util.zip.CRC32

/** La zone de base de brouter.de, là où le serveur de hike2gpx n'a rien (Nico, 2026-11-13 : « si je vais au Canada »). */
class ZoneBrouterTest {
    @get:Rule val dossier = TemporaryFolder()

    @Test fun les_cases_portent_le_nom_de_brouter() {
        assertEquals("E5_N40", ZoneBrouter.caseDe(43.3, 6.0))
        assertEquals("W120_N50", ZoneBrouter.caseDe(51.18, -115.57))       // Banff (-120 à -115)
        assertEquals("W115_N50", ZoneBrouter.caseDe(51.05, -114.07))       // Calgary
        assertEquals("W75_N45", ZoneBrouter.caseDe(45.5, -73.6))           // Montréal
        assertEquals("E150_S35", ZoneBrouter.caseDe(-33.9, 151.2))         // Sydney
        assertEquals(listOf(50.0, -115.0, 55.0, -110.0), ZoneBrouter.boite("W115_N50"))
    }

    /** Une RD5 minimale : 25 entrées de 8 octets, la dernière pointant la fin des données, puis un pied et son CRC. */
    private fun rd5(donnees: Int, pied: Boolean, crcFaux: Boolean = false): File {
        val fin = 200L + donnees
        val entete = ByteBuffer.allocate(200).apply { for (i in 0 until 25) putLong(if (i == 24) fin else 200L + i) }.array()
        val crc = (CRC32().apply { update(entete) }.value xor 0xFFFFFFFFL) xor 2L
        val f = dossier.newFile()
        f.outputStream().use { o ->
            o.write(entete)
            o.write(ByteArray(donnees))
            if (pied) {
                o.write(ByteArray(8))
                o.write(ByteBuffer.allocate(4).putInt((if (crcFaux) crc + 1 else crc).toInt()).array())
                o.write(ByteArray(100))
            }
        }
        return f
    }

    @Test fun une_rd5_entiere_est_reconnue_et_une_coupee_refusee() {
        assertTrue("ancien format : le fichier s'arrête à la fin des données", ZoneBrouter.rd5Entier(rd5(500, pied = false)))
        assertTrue("nouveau format : le pied et son CRC", ZoneBrouter.rd5Entier(rd5(500, pied = true)))
        assertFalse("CRC faux", ZoneBrouter.rd5Entier(rd5(500, pied = true, crcFaux = true)))
        val coupee = rd5(500, pied = true)
        coupee.writeBytes(coupee.readBytes().copyOf(400))
        assertFalse("transfert coupé", ZoneBrouter.rd5Entier(coupee))
    }
}
