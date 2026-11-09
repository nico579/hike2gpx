package org.hike2gpx.android

import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

/**
 * Le journal de la trace : chaque point retenu y est écrit aussitôt, pour
 * qu'un processus tué en randonnée ne perde pas la trace.
 */
class EnregistrementGpsTest {
    @get:Rule val dossier = TemporaryFolder()

    @After fun arreter() {
        EnregistrementGps.arreter()
    }

    private fun demarrer(): File {
        val gpx = File(dossier.root, "trace-20261109-080000.gpx")
        EnregistrementGps.demarrer(TraceGps(distanceMin = 0.0, dureeMin = 0L), gpx)
        return gpx
    }

    @Test fun chaque_point_retenu_entre_dans_le_journal() {
        val gpx = demarrer()
        assertTrue(EnregistrementGps.ajouter(43.30, 5.70, 650.5, 1_000L, 5.0))
        assertTrue(EnregistrementGps.ajouter(43.31, 5.71, null, 2_000L, 5.0))
        // Refusé par le filtre de précision : il n'entre pas au journal.
        assertFalse(EnregistrementGps.ajouter(43.32, 5.72, null, 3_000L, 500.0))
        val points = EnregistrementGps.lireJournal(EnregistrementGps.journalDe(gpx))
        assertEquals(listOf(PointTrace(43.30, 5.70, 650.5, 1_000L), PointTrace(43.31, 5.71, null, 2_000L)), points)
    }

    @Test fun les_ecrans_abonnes_sont_prevenus() {
        demarrer()
        var appels = 0
        val observateur = { appels += 1 }
        EnregistrementGps.abonner(observateur)
        EnregistrementGps.ajouter(43.30, 5.70, null, 1_000L, null)
        EnregistrementGps.desabonner(observateur)
        EnregistrementGps.ajouter(43.31, 5.71, null, 2_000L, null)
        assertEquals(1, appels)
    }

    @Test fun une_derniere_ligne_coupee_est_ignoree() {
        val journal = File(dossier.root, "trace.gpx.journal")
        journal.writeText("43.3;5.7;650.0;1000\n43.31;5.71;;2000\n43.3")
        assertEquals(2, EnregistrementGps.lireJournal(journal).size)
    }

    @Test fun une_trace_interrompue_redevient_un_gpx() {
        val gpx = demarrer()
        EnregistrementGps.ajouter(43.30, 5.70, 650.0, 1_000L, null)
        EnregistrementGps.ajouter(43.31, 5.71, 655.0, 2_000L, null)
        // Pendant l'enregistrement, rien ne se récupère : le journal est vivant.
        assertTrue(EnregistrementGps.recuperer(dossier.root).isEmpty())
        // Le processus meurt : la trace en mémoire disparaît, le journal reste.
        EnregistrementGps.arreter()
        val refaits = EnregistrementGps.recuperer(dossier.root)
        assertEquals(listOf(gpx), refaits)
        assertFalse(EnregistrementGps.journalDe(gpx).exists())
        val relus = Gpx.lireTrace(gpx.readText())
        assertEquals(2, relus.size)
        assertEquals(655.0, relus[1].altitude!!, 1e-9)
    }

    @Test fun un_arret_normal_efface_le_journal() {
        val gpx = demarrer()
        EnregistrementGps.ajouter(43.30, 5.70, null, 1_000L, null)
        EnregistrementGps.arreter()
        EnregistrementGps.terminer(gpx)
        assertFalse(EnregistrementGps.journalDe(gpx).exists())
        assertTrue(EnregistrementGps.recuperer(dossier.root).isEmpty())
    }

    @Test fun un_journal_vide_s_efface_sans_gpx() {
        val gpx = demarrer()
        EnregistrementGps.arreter()
        assertTrue(EnregistrementGps.recuperer(dossier.root).isEmpty())
        assertFalse(EnregistrementGps.journalDe(gpx).exists())
        assertFalse(gpx.exists())
        assertNull(EnregistrementGps.trace)
    }
}
