package org.hike2gpx.android

import android.app.Activity
import android.app.ActivityManager
import android.app.AlertDialog
import android.content.Intent
import android.os.Bundle
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.Switch
import android.widget.TextView
import org.json.JSONArray
import org.osmdroid.config.Configuration
import org.osmdroid.events.MapEventsReceiver
import org.osmdroid.util.BoundingBox
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.CopyrightOverlay
import org.osmdroid.views.overlay.MapEventsOverlay
import org.osmdroid.views.overlay.Polyline
import java.io.File
import java.util.Locale
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/**
 * L'écran unique : les lots du dépôt (GitHub et les PC ajoutés), leur
 * téléchargement, et le calcul hors ligne d'un itinéraire sur un lot installé.
 */
class MainActivity : Activity() {
    private lateinit var reglages: Reglages
    private lateinit var horsLigne: HorsLigne
    private lateinit var routeur: Routeur
    private lateinit var etat: TextView
    private lateinit var progression: ProgressBar
    private lateinit var arreter: Button
    private lateinit var listeLots: LinearLayout
    private lateinit var listeSources: LinearLayout
    private lateinit var depart: EditText
    private lateinit var arrivee: EditText
    private lateinit var strict: Switch
    private lateinit var officiels: Switch
    private lateinit var carte: MapView
    private var trace: Polyline? = null
    private var dernier: Resultat? = null
    private var departSuivant = true
    private var offres: List<Offre> = emptyList()

    override fun onCreate(etatSauve: Bundle?) {
        super.onCreate(etatSauve)
        Configuration.getInstance().userAgentValue = "${Depot.AGENT} (+https://github.com/nico579/hike2gpx)"
        Configuration.getInstance().osmdroidBasePath = File(cacheDir, "osmdroid")
        Configuration.getInstance().osmdroidTileCache = File(cacheDir, "osmdroid/tiles")
        reglages = Reglages(this)
        horsLigne = HorsLigne(filesDir)
        routeur = Routeur(Reglages.profils(this))
        construire()
        afficherSources()
        afficherLots()
        lireLien(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        lireLien(intent)
    }

    // ------------------------------------------------------------------ écran

    private fun construire() {
        val colonne = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val marge = dp(12)
        colonne.setPadding(marge, marge, marge, marge)
        setContentView(ScrollView(this).apply { addView(colonne) })
        colonne.addView(TextView(this).apply { text = getString(R.string.app_name); textSize = 24f })
        etat = TextView(this).apply { setText(R.string.etat_pret) }
        colonne.addView(etat)
        progression = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 1000; visibility = View.GONE
        }
        colonne.addView(progression)
        arreter = bouton(colonne, R.string.arreter).apply { visibility = View.GONE }

        titre(colonne, R.string.titre_lots)
        bouton(colonne, R.string.actualiser).setOnClickListener { actualiser() }
        listeLots = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        colonne.addView(listeLots)

        titre(colonne, R.string.titre_sources)
        listeSources = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        colonne.addView(listeSources)
        bouton(colonne, R.string.coller_lien).setOnClickListener { collerLien() }

        titre(colonne, R.string.titre_itineraire)
        depart = champ(colonne, R.string.depart, "43.458, 6.045")
        arrivee = champ(colonne, R.string.arrivee, "43.465, 6.055")
        strict = Switch(this).apply { setText(R.string.strict) }
        colonne.addView(strict)
        officiels = Switch(this).apply { setText(R.string.officiels); isChecked = true }
        colonne.addView(officiels)
        bouton(colonne, R.string.calculer).setOnClickListener { calculer() }
        bouton(colonne, R.string.annuler_calcul).setOnClickListener { routeur.annuler() }
        bouton(colonne, R.string.exporter).setOnClickListener { exporter() }

        carte = MapView(this).apply {
            setMultiTouchControls(true)
            controller.setZoom(13.0)
            controller.setCenter(GeoPoint(43.458, 6.045))
            overlays.add(CopyrightOverlay(this@MainActivity))
            overlays.add(MapEventsOverlay(object : MapEventsReceiver {
                override fun singleTapConfirmedHelper(p: GeoPoint): Boolean {
                    (if (departSuivant) depart else arrivee)
                        .setText(String.format(Locale.US, "%.6f, %.6f", p.latitude, p.longitude))
                    departSuivant = !departSuivant
                    return true
                }
                override fun longPressHelper(p: GeoPoint) = false
            }))
        }
        colonne.addView(carte, LinearLayout.LayoutParams(-1, dp(350)))
    }

    private fun afficherSources() {
        listeSources.removeAllViews()
        listeSources.addView(TextView(this).apply { setText(R.string.source_github) })
        for (pc in reglages.pcs()) {
            val ligne = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            ligne.addView(TextView(this).apply { text = pc.libelle }, LinearLayout.LayoutParams(0, -2, 1f))
            ligne.addView(Button(this).apply {
                setText(R.string.oublier)
                setOnClickListener { reglages.oublierPc(pc); afficherSources() }
            })
            listeSources.addView(ligne)
        }
        listeSources.addView(TextView(this).apply { setText(R.string.aide_qr) })
    }

    /** Les lots installés et, après une actualisation, ceux du dépôt. */
    private fun afficherLots() {
        listeLots.removeAllViews()
        val installes = horsLigne.lots().associateBy { it.case }
        for (offre in offres) {
            val lot = offre.lot
            val present = installes[lot.case]
            val aJour = present != null && !plusRecent(lot, present)
            val ligne = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            ligne.addView(TextView(this).apply {
                text = getString(R.string.ligne_lot, lot.case, description(lot), lot.octets / 1_000_000,
                    offre.source.libelle)
            }, LinearLayout.LayoutParams(0, -2, 1f))
            ligne.addView(Button(this).apply {
                setText(when { aJour -> R.string.a_jour; present != null -> R.string.mettre_a_jour; else -> R.string.telecharger })
                isEnabled = !aJour
                setOnClickListener { telecharger(offre) }
            })
            listeLots.addView(ligne)
        }
        for (lot in installes.values.filter { l -> offres.none { it.lot.case == l.case } }) {
            val ligne = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            ligne.addView(TextView(this).apply { text = getString(R.string.ligne_installe, lot.case, description(lot)) },
                LinearLayout.LayoutParams(0, -2, 1f))
            listeLots.addView(ligne)
        }
        if (offres.isEmpty() && installes.isEmpty())
            listeLots.addView(TextView(this).apply { setText(R.string.aucun_lot) })
    }

    private fun description(lot: Lot): String {
        val genre = if (lot.osm) "OSM" else "enrichi ${lot.fournisseurs.joinToString("+")}"
        val sources = lot.sources.filterKeys { it != "relief" }.entries.joinToString(", ") { "${it.key} ${it.value.take(10)}" }
        return "$genre · $sources"
    }

    // ------------------------------------------------------------------ dépôt

    private fun actualiser() = tache(R.string.etat_catalogue) {
        val lus = mutableListOf<Pair<Source, Catalogue>>()
        val echecs = mutableListOf<String>()
        for (source in reglages.sources()) {
            try {
                lus.add(source to Depot().lireCatalogue(source))
            } catch (e: ErreurDepot) {
                echecs.add(e.message ?: source.libelle)    // un PC éteint n'empêche pas GitHub
            }
        }
        val choix = choisir(lus)
        runOnUiThread { offres = choix; afficherLots() }
        if (echecs.isEmpty()) getString(R.string.etat_catalogue_lu, choix.size)
        else echecs.joinToString("\n")
    }

    private fun telecharger(offre: Offre) {
        val lot = offre.lot
        AlertDialog.Builder(this)
            .setTitle(lot.case)
            .setMessage(getString(R.string.confirmer_telechargement, lot.octets / 1_000_000, offre.source.libelle))
            .setPositiveButton(R.string.telecharger) { _, _ ->
                tacheInterruptible(R.string.etat_telechargement) { continuer ->
                    val travail = File(File(filesDir, "telechargements"), lot.case)
                    Depot().telecharger(lot, offre.source, travail, { faits, total ->
                        runOnUiThread { progression.progress = (1000 * faits / maxOf(total, 1)).toInt() }
                    }, continuer)
                    runOnUiThread { progression.isIndeterminate = true }
                    val installe = horsLigne.installer(travail)
                    travail.deleteRecursively()
                    runOnUiThread { afficherLots() }
                    getString(R.string.etat_installe, installe.case)
                }
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    /** Un lien hike2gpx://depot reçu du QR code d'un PC (lu par l'appareil photo). */
    private fun lireLien(intent: Intent?) {
        val lien = intent?.data?.toString() ?: return
        if (!lien.startsWith("hike2gpx:")) return
        try {
            ajouterPc(LienDepot.lire(lien))
        } catch (e: ErreurDepot) {
            etat.text = e.message
        }
    }

    private fun collerLien() {
        val champ = EditText(this).apply { hint = "hike2gpx://depot?url=…&jeton=…"; setSingleLine(true) }
        AlertDialog.Builder(this)
            .setTitle(R.string.coller_lien)
            .setView(champ)
            .setPositiveButton(android.R.string.ok) { _, _ ->
                try {
                    ajouterPc(LienDepot.lire(champ.text.toString()))
                } catch (e: ErreurDepot) {
                    etat.text = e.message
                }
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    /** Toujours confirmé : une page web pourrait ouvrir un tel lien à l'insu de l'utilisateur. */
    private fun ajouterPc(source: Source) {
        AlertDialog.Builder(this)
            .setTitle(R.string.ajouter_pc)
            .setMessage(getString(R.string.confirmer_pc, source.catalogue))
            .setPositiveButton(android.R.string.ok) { _, _ ->
                reglages.ajouterPc(source)
                afficherSources()
                actualiser()
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    // ------------------------------------------------------------------ itinéraire

    private fun calculer() {
        val points = try {
            listOf(point(depart.text.toString()), point(arrivee.text.toString()))
        } catch (e: Exception) {
            etat.setText(R.string.points_invalides)
            return
        }
        val modeStrict = strict.isChecked
        val avecOfficiels = officiels.isChecked
        val memoire = (getSystemService(ACTIVITY_SERVICE) as ActivityManager).memoryClass
        tache(R.string.etat_calcul) {
            val resultat = Itineraire(horsLigne, routeur).calculer(points, modeStrict, avecOfficiels, memoire)
            runOnUiThread { dernier = resultat; montrer(resultat.coordonnees) }
            val proprietes = resultat.feature.optJSONObject("properties")
            getString(R.string.etat_itineraire, resultat.lot.case,
                (proprietes?.optString("track-length")?.toDoubleOrNull() ?: 0.0) / 1000)
        }
    }

    private fun montrer(coordonnees: JSONArray) {
        trace?.let { carte.overlays.remove(it) }
        val points = List(coordonnees.length()) {
            coordonnees.getJSONArray(it).let { p -> GeoPoint(p.getDouble(1), p.getDouble(0)) }
        }
        trace = Polyline(carte).apply {
            setPoints(points)
            outlinePaint.color = 0xff175dcb.toInt()
            outlinePaint.strokeWidth = 8f
        }
        carte.overlays.add(trace)
        carte.zoomToBoundingBox(BoundingBox.fromGeoPoints(points), true, 40)
        carte.invalidate()
    }

    private fun exporter() {
        if (dernier == null) {
            etat.setText(R.string.rien_a_exporter); return
        }
        startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "application/gpx+xml"
            putExtra(Intent.EXTRA_TITLE, "hike2gpx.gpx")
        }, EXPORT)
    }

    @Deprecated("Activity de la plateforme : pas d'AndroidX dans cette application.")
    override fun onActivityResult(requete: Int, resultat: Int, donnees: Intent?) {
        super.onActivityResult(requete, resultat, donnees)
        val coordonnees = dernier?.coordonnees ?: return
        val adresse = donnees?.data ?: return
        if (requete != EXPORT || resultat != RESULT_OK) return
        try {
            contentResolver.openOutputStream(adresse)?.use { it.write(Gpx.ecrire(coordonnees).toByteArray()) }
            etat.setText(R.string.export_fait)
        } catch (e: Exception) {
            etat.text = e.message
        }
    }

    // ------------------------------------------------------------------ outils

    /**
     * Une tâche de fond, une à la fois, avec son état à l'écran. Les tâches
     * interruptibles reçoivent continuer(), que le bouton « Arrêter » rend faux.
     */
    private fun tacheInterruptible(message: Int, travail: (() -> Boolean) -> String) = tache(message, true, travail)

    private fun tache(message: Int, travail: () -> String) = tache(message, false) { travail() }

    private fun tache(message: Int, interruptible: Boolean, travail: (() -> Boolean) -> String) {
        if (enCours.getAndSet(true)) {
            etat.setText(R.string.etat_occupe); return
        }
        val arret = AtomicBoolean(false)
        etat.setText(message)
        progression.progress = 0
        progression.isIndeterminate = !interruptible
        progression.visibility = View.VISIBLE
        arreter.visibility = if (interruptible) View.VISIBLE else View.GONE
        arreter.setOnClickListener { arret.set(true) }
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        EXECUTEUR.execute {
            val texte = try {
                travail { !arret.get() }
            } catch (e: Abandon) {
                getString(R.string.etat_interrompu)
            } catch (e: Exception) {
                e.message ?: e.toString()
            } finally {
                enCours.set(false)
            }
            runOnUiThread {
                etat.text = texte
                progression.visibility = View.GONE
                arreter.visibility = View.GONE
                window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            }
        }
    }

    private fun point(texte: String): Point {
        val v = texte.trim().split(Regex("[,; ]+")).map { it.toDouble() }
        require(v.size == 2)
        return Point(v[0], v[1])
    }

    private fun dp(n: Int) = (n * resources.displayMetrics.density).toInt()

    private fun titre(parent: LinearLayout, texte: Int) =
        parent.addView(TextView(this).apply { setText(texte); textSize = 18f; setPadding(0, dp(16), 0, dp(4)) })

    private fun bouton(parent: LinearLayout, texte: Int) = Button(this).apply { setText(texte); parent.addView(this) }

    private fun champ(parent: LinearLayout, libelle: Int, exemple: String): EditText {
        parent.addView(TextView(this).apply { setText(libelle) })
        return EditText(this).apply { setSingleLine(true); hint = exemple; parent.addView(this) }
    }

    override fun onResume() {
        super.onResume(); carte.onResume()
    }

    override fun onPause() {
        carte.onPause(); super.onPause()
    }

    override fun onDestroy() {
        routeur.annuler()
        carte.onDetach()
        super.onDestroy()
    }

    companion object {
        private const val EXPORT = 1
        // Au niveau du processus : un téléchargement survit à l'écran qui l'a lancé.
        private val EXECUTEUR = Executors.newSingleThreadExecutor()
        private val enCours = AtomicBoolean(false)
    }
}
