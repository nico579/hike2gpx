package org.hike2gpx.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class TracesImporteesTest {
    private val kml = """<?xml version="1.0" encoding="UTF-8"?>
        <kml xmlns="http://www.opengis.net/kml/2.2"><Document>
          <Style id="14"><LineStyle><color>ff5622e5</color><width>5</width></LineStyle></Style>
          <Placemark><name>2020-12-13_La Roquebrussanne_8.7km_D+350m_2h18</name><styleUrl>#14</styleUrl>
            <ExtendedData>
              <Data name="modele"><value>&quot;IGN LiDAR HD&quot;</value></Data>
              <Data name="denivele_exact"><value>{&quot;Dplus_m&quot;: 349.8, &quot;Dmoins_m&quot;: 349.9}</value></Data>
            </ExtendedData>
            <MultiGeometry><LineString><coordinates>6.00,43.30,0 6.01,43.30,0 6.01,43.31,0</coordinates></LineString></MultiGeometry>
          </Placemark>
        </Document></kml>"""

    @Test
    fun unKmlDeGpx2dashDonneSaTraceSaCouleurEtSesInfos() {
        val traces = TracesImportees.lire(kml, "traces.kml")
        assertEquals(1, traces.size)
        val t = traces[0]
        assertEquals(3, t.segments[0].size)
        assertEquals(43.30 to 6.00, t.segments[0][0])
        assertEquals(0xffe52256.toInt(), t.couleur)
        assertEquals(5f, t.epaisseur)
        assertEquals(Triple(350, 350, "IGN LiDAR HD"), TracesImportees.denivele(t))
    }

    @Test
    fun leNomDeGpx2dashDonneDateDistanceDenivelEtDuree() {
        val n = TracesImportees.lireNom("2020-12-13_LA ROQUEBRUSSANNE_8.7KM_D+350M_2H18")
        assertEquals(NomTrace("LA ROQUEBRUSSANNE", "2020-12-13", 8.7, 350, 138), n)
        assertEquals("Tourris10 Le Revest-les-Eaux",
            TracesImportees.lireNom("2015-04-24_Tourris10_Le Revest-les-Eaux_11.5km_D+514m_2h21").titre)
        assertEquals(NomTrace("Sortie du dimanche"), TracesImportees.lireNom("Sortie du dimanche"))
        assertEquals(NomTrace("La Roquebrussanne", "2026-04-27", 17.8, 690, 229, "12 h 14"),
            TracesImportees.lireNom("2026-04-27_12-14 La Roquebrussanne_17.8km_D+690m_3h49"))
    }

    @Test
    fun unGpxDonneUneTraceAuNomDuFichier() {
        val gpx = """<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1"><trk><trkseg>
            <trkpt lat="43.3" lon="6.0"/><trkpt lat="43.31" lon="6.01"/></trkseg></trk></gpx>"""
        val traces = TracesImportees.lire(gpx, "boucle.gpx")
        assertEquals("boucle", traces.single().nom)
        assertNull(traces.single().couleur)
        val metres = TracesImportees.longueur(traces.single().segments)
        assertTrue("environ 1,36 km : $metres", metres in 1300.0..1420.0)
    }

    @Test
    fun uneCouleurIllisibleDonneNull() {
        assertNull(TracesImportees.couleurKml("rouge"))
    }
}
