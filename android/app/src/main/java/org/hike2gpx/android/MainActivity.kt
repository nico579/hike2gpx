package org.hike2gpx.android

import android.app.Activity
import android.app.ActivityManager
import android.app.AlertDialog
import android.content.Intent
import android.net.ConnectivityManager
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.view.Gravity
import android.view.View
import android.view.WindowInsets
import android.view.WindowManager
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.Switch
import android.widget.TextView
import org.json.JSONArray
import org.osmdroid.config.Configuration
import org.osmdroid.events.MapEventsReceiver
import org.osmdroid.tileprovider.MapTileProviderBasic
import org.osmdroid.tileprovider.modules.OfflineTileProvider
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.tileprovider.tilesource.XYTileSource
import org.osmdroid.tileprovider.util.SimpleRegisterReceiver
import org.osmdroid.util.BoundingBox
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.CopyrightOverlay
import org.osmdroid.views.overlay.MapEventsOverlay
import org.osmdroid.views.overlay.Marker
import org.osmdroid.views.overlay.Polyline
import org.osmdroid.views.overlay.ScaleBarOverlay
import java.io.File
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/**
 * L'écran unique, comme la page du PC : la carte d'abord. Toucher la carte pose
 * un point ; le lot du serveur qui couvre le parcours se télécharge de lui-même,
 * puis l'itinéraire se calcule hors ligne dès qu'il y a deux points. Le fond se
 * choisit parmi les fonds en ligne et ceux qu'un PC partage ; les lots et les
 * sources sont dans les réglages.
 */
class MainActivity : Activity() {
    private lateinit var reglages: Reglages
    private lateinit var horsLigne: HorsLigne
    private lateinit var fonds: Fonds
    private lateinit var routeur: Routeur
    private lateinit var carte: MapView
    private lateinit var etat: TextView
    private lateinit var progression: ProgressBar
    private lateinit var arreter: Button
    private val points = mutableListOf<Point>()
    private val reperes = mutableListOf<Marker>()
    private var trace: Polyline? = null
    private var dernier: Resultat? = null
    private var catalogues: List<Pair<Source, Catalogue>> = emptyList()
    private var offres: List<Offre> = emptyList()
    /** case -> instant (SystemClock) d'un échec ou d'un refus : pas de nouvel essai automatique avant une heure. */
    private val exclues = mutableMapOf<String, Long>()
    /** Les cases retirées à la main : elles ne reviennent pas toutes seules pendant la séance (comme le PC). */
    private val retirees = mutableSetOf<String>()
    /** Un point posé pendant une tâche : on reprend à sa fin. */
    private var aReprendre = false
    private var fenetreReglages: LinearLayout? = null

    override fun onCreate(etatSauve: Bundle?) {
        super.onCreate(etatSauve)
        Configuration.getInstance().userAgentValue = "${Depot.AGENT} (+https://github.com/nico579/hike2gpx)"
        Configuration.getInstance().osmdroidBasePath = File(cacheDir, "osmdroid")
        Configuration.getInstance().osmdroidTileCache = File(cacheDir, "osmdroid/tiles")
        reglages = Reglages(this)
        horsLigne = HorsLigne(filesDir)
        fonds = Fonds(horsLigne.racine)
        routeur = Routeur(Reglages.profils(this))
        construire()
        appliquerFond(reglages.fond)
        lireLien(intent)
        actualiser()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        lireLien(intent)
    }

    // ------------------------------------------------------------------ écran

    private fun construire() {
        val racine = FrameLayout(this)
        val vue = reglages.vue
        carte = MapView(this).apply {
            setMultiTouchControls(true)
            controller.setZoom(vue.third)
            controller.setCenter(GeoPoint(vue.first, vue.second))
            overlays.add(CopyrightOverlay(this@MainActivity))
            overlays.add(ScaleBarOverlay(this).apply { setAlignBottom(true); setScaleBarOffset(dp(8), dp(64)) })
            overlays.add(MapEventsOverlay(object : MapEventsReceiver {
                override fun singleTapConfirmedHelper(p: GeoPoint): Boolean {
                    ajouterPoint(Point(p.latitude, p.longitude)); return true
                }
                override fun longPressHelper(p: GeoPoint) = false
            }))
        }
        racine.addView(carte, FrameLayout.LayoutParams(-1, -1))

        val marge = dp(8)
        val haut = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(VOILE) }
        etat = TextView(this).apply { setText(R.string.etat_pret); setTextColor(0xff202020.toInt()) }
        haut.addView(etat)
        progression = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 1000; visibility = View.GONE
        }
        haut.addView(progression)
        arreter = Button(this).apply { setText(R.string.arreter); visibility = View.GONE }
        haut.addView(arreter, LinearLayout.LayoutParams(-2, -2))
        racine.addView(haut, FrameLayout.LayoutParams(-1, -2, Gravity.TOP))

        val bas = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setBackgroundColor(VOILE) }
        for ((texte, action) in listOf<Pair<Int, () -> Unit>>(
            R.string.fond to ::choisirFond,
            R.string.retour to ::retirerPoint,
            R.string.effacer to ::effacer,
            R.string.exporter to ::exporter,
            R.string.reglages to ::ouvrirReglages,
        )) {
            bas.addView(Button(this).apply {
                setText(texte); textSize = 13f; isAllCaps = false; setOnClickListener { action() }
            }, LinearLayout.LayoutParams(0, -2, 1f))
        }
        racine.addView(bas, FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM))

        // Android 15 dessine l'application sous les barres du système : les bandeaux s'en écartent.
        racine.setOnApplyWindowInsetsListener { _, insets ->
            val (dessus, dessous) = if (Build.VERSION.SDK_INT >= 30)
                insets.getInsets(WindowInsets.Type.systemBars()).let { it.top to it.bottom }
            else @Suppress("DEPRECATION") (insets.systemWindowInsetTop to insets.systemWindowInsetBottom)
            haut.setPadding(marge, marge + dessus, marge, marge)
            bas.setPadding(marge / 2, marge / 2, marge / 2, marge / 2 + dessous)
            insets
        }
        setContentView(racine)
    }

    // ------------------------------------------------------------------ points et calcul

    private fun ajouterPoint(p: Point) {
        points.add(p)
        dessinerPoints()
        if (points.size == 1) etat.setText(R.string.etat_depart_pose)
        avancer()
    }

    private fun retirerPoint() {
        if (points.isEmpty()) return
        points.removeAt(points.size - 1)
        dessinerPoints()
        if (points.size < 2) effacerTrace() else avancer()
    }

    private fun effacer() {
        points.clear()
        dessinerPoints()
        effacerTrace()
        etat.setText(R.string.etat_pret)
    }

    private fun dessinerPoints() {
        reperes.forEach { carte.overlays.remove(it) }
        reperes.clear()
        points.forEachIndexed { i, p ->
            reperes.add(Marker(carte).apply {
                position = GeoPoint(p.lat, p.lon)
                setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_BOTTOM)
                title = when {
                    i == 0 -> getString(R.string.depart)
                    i == points.size - 1 -> getString(R.string.arrivee)
                    else -> getString(R.string.etape, i)
                }
                setInfoWindow(null)
            })
        }
        carte.overlays.addAll(reperes)
        carte.invalidate()
    }

    private fun effacerTrace() {
        trace?.let { carte.overlays.remove(it) }
        trace = null
        dernier = null
        carte.invalidate()
    }

    /**
     * La suite logique après chaque point ou chaque tâche : le lot qui manque
     * pour la zone d'abord, puis le calcul s'il y a deux points.
     */
    private fun avancer() {
        aReprendre = false
        if (points.isEmpty()) return
        if (enCours.get()) {
            aReprendre = true; return
        }
        val maintenant = SystemClock.elapsedRealtime()
        val exclu = exclues.filterValues { maintenant - it < REESSAI_MS }.keys + retirees
        val aFaire = lotsATelecharger(offres, horsLigne.lots(), Zone.autour(points), exclu)
        if (aFaire.isNotEmpty()) {
            telechargerAuto(aFaire.first()); return
        }
        if (points.size >= 2) calculer()
    }

    private fun calculer() {
        val etapes = points.toList()
        val memoire = (getSystemService(ACTIVITY_SERVICE) as ActivityManager).memoryClass
        tache(R.string.etat_calcul, false, { _ ->
            val resultat = Itineraire(horsLigne, routeur).calculer(etapes, reglages.strict, reglages.officiels, memoire)
            runOnUiThread { if (etapes == points) { dernier = resultat; montrer(resultat.coordonnees) } }
            val proprietes = resultat.feature.optJSONObject("properties")
            getString(R.string.etat_itineraire, resultat.lot.case,
                (proprietes?.optString("track-length")?.toDoubleOrNull() ?: 0.0) / 1000)
        })
    }

    private fun montrer(coordonnees: JSONArray) {
        trace?.let { carte.overlays.remove(it) }
        val geo = List(coordonnees.length()) {
            coordonnees.getJSONArray(it).let { p -> GeoPoint(p.getDouble(1), p.getDouble(0)) }
        }
        trace = Polyline(carte).apply {
            setPoints(geo)
            outlinePaint.color = 0xff175dcb.toInt()
            outlinePaint.strokeWidth = 8f
        }
        carte.overlays.add(1, trace)        // sous les touches et les repères
        // Recadré seulement si le tracé sort de la vue : un point ajouté ne fait pas sauter la carte.
        val boite = BoundingBox.fromGeoPoints(geo)
        val vue = carte.boundingBox
        if (!vue.contains(GeoPoint(boite.latNorth, boite.lonWest)) || !vue.contains(GeoPoint(boite.latSouth, boite.lonEast)))
            carte.zoomToBoundingBox(boite, true, dp(48))
        carte.invalidate()
    }

    // ------------------------------------------------------------------ lots

    /** Les catalogues de toutes les sources ; un PC éteint n'empêche pas GitHub. */
    private fun actualiser() = tache(R.string.etat_catalogue, false, { _ ->
        val lus = mutableListOf<Pair<Source, Catalogue>>()
        val echecs = mutableListOf<String>()
        for (source in reglages.sources()) {
            try {
                lus.add(source to Depot().lireCatalogue(source))
            } catch (e: ErreurDepot) {
                echecs.add(e.message ?: source.libelle)
            }
        }
        val choix = choisir(lus)
        runOnUiThread { catalogues = lus; offres = choix; remplirReglages() }
        when {
            echecs.isNotEmpty() -> echecs.joinToString("\n")
            points.isEmpty() -> getString(R.string.etat_pret)
            else -> getString(R.string.etat_catalogue_lu, choix.size)
        }
    }, ensuite = { avancer() })

    /** Le lot qui manque pour le parcours : de lui-même sur le Wi-Fi, sur demande sur un réseau facturé. */
    private fun telechargerAuto(offre: Offre) {
        val reseau = getSystemService(ConnectivityManager::class.java)
        if (reseau.activeNetwork == null) {
            if (points.size >= 2) calculer()
            return
        }
        if (!reseau.isActiveNetworkMetered) {
            telecharger(offre); return
        }
        AlertDialog.Builder(this)
            .setTitle(offre.lot.case)
            .setMessage(getString(R.string.confirmer_donnees_mobiles, offre.lot.case, offre.lot.octets / 1_000_000,
                offre.source.libelle))
            .setPositiveButton(R.string.telecharger) { _, _ -> telecharger(offre) }
            .setNegativeButton(R.string.plus_tard) { _, _ ->
                exclues[offre.lot.case] = SystemClock.elapsedRealtime()
                avancer()
            }
            .setCancelable(false)
            .show()
    }

    private fun telecharger(offre: Offre) {
        val lot = offre.lot
        tache(R.string.etat_telechargement, true, { continuer ->
            runOnUiThread { etat.text = getString(R.string.etat_telechargement_lot, lot.case, lot.octets / 1_000_000) }
            val travail = File(File(filesDir, "telechargements"), lot.case)
            Depot().telecharger(lot, offre.source, travail, { faits, total ->
                runOnUiThread { progression.progress = (1000 * faits / maxOf(total, 1)).toInt() }
            }, continuer)
            runOnUiThread { progression.isIndeterminate = true }
            val installe = horsLigne.installer(travail)
            travail.deleteRecursively()
            retirees.remove(installe.case)
            getString(R.string.etat_installe, installe.case)
        }, ensuite = { reussi ->
            if (!reussi) exclues[lot.case] = SystemClock.elapsedRealtime()
            remplirReglages()
            avancer()
        })
    }

    private fun supprimerLot(lot: Lot) {
        AlertDialog.Builder(this)
            .setTitle(lot.case)
            .setMessage(R.string.confirmer_suppression)
            .setPositiveButton(R.string.supprimer) { _, _ ->
                if (enCours.get()) {
                    etat.setText(R.string.etat_occupe); return@setPositiveButton
                }
                routeur.annuler()
                val octets = horsLigne.supprimer(lot.case)
                retirees.add(lot.case)
                etat.text = getString(R.string.etat_supprime, lot.case, octets / 1_000_000)
                remplirReglages()
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    // ------------------------------------------------------------------ fonds de carte

    /** Les fonds en ligne, les fonds hors ligne installés, et ceux que les PC proposent. */
    private fun choisirFond() {
        val choix = mutableListOf<Pair<String, () -> Unit>>()
        choix.add(getString(R.string.fond_osm) to { appliquerFond("osm") })
        choix.add(getString(R.string.fond_topo) to { appliquerFond("topo") })
        for ((source, fichiers) in fonds.parSource()) {
            choix.add(getString(R.string.fond_hors_ligne, Fonds.titre(source), fichiers.size,
                fichiers.sumOf { it.length() } / 1_000_000) to { appliquerFond(source) })
        }
        val proposes = fondsProposes(catalogues, fonds.installes().map { it.nameWithoutExtension }.toSet())
        for ((source, fond) in proposes) {
            choix.add(getString(R.string.fond_a_telecharger, Fonds.titre(fond.source), fond.nom, fond.octets / 1_000_000,
                source.libelle) to { telechargerFond(source, fond) })
        }
        if (reglages.pcs().isEmpty()) choix.add(getString(R.string.fond_sans_pc) to { collerLien() })
        else if (proposes.isEmpty()) choix.add(getString(R.string.fond_relire) to { actualiser() })
        AlertDialog.Builder(this)
            .setTitle(R.string.titre_fond)
            .setItems(choix.map { it.first }.toTypedArray()) { _, i -> choix[i].second() }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun telechargerFond(source: Source, fond: Fond) {
        AlertDialog.Builder(this)
            .setTitle(fond.nom)
            .setMessage(getString(R.string.confirmer_telechargement, fond.octets / 1_000_000, source.libelle))
            .setPositiveButton(R.string.telecharger) { _, _ ->
                tache(R.string.etat_telechargement, true, { continuer ->
                    val travail = File(filesDir, "telechargements")
                    val recu = Depot().telechargerFond(fond, source, travail, { faits, total ->
                        runOnUiThread { progression.progress = (1000 * faits / maxOf(total, 1)).toInt() }
                    }, continuer)
                    fonds.installer(recu, fond)
                    getString(R.string.etat_fond_installe, fond.nom)
                }, ensuite = { reussi -> if (reussi) appliquerFond(Fonds.source(fond.nom)) })
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    /**
     * Le fond de la carte. Un fond hors ligne réunit tous les MBTiles de sa
     * source ; osmdroid agrandit au-delà de leur zoom le plus fin, comme la page
     * (maxNativeZoom), et ne demande rien au réseau.
     */
    private fun appliquerFond(cle: String) {
        val fichiers = fonds.parSource()[cle]
        when {
            fichiers != null -> {
                carte.setTileProvider(OfflineTileProvider(SimpleRegisterReceiver(this), fichiers.toTypedArray()))
                carte.setTileSource(XYTileSource("hors-ligne-$cle", 0, 19, 256, "", arrayOf<String>(), "© ${Fonds.titre(cle)}"))
            }
            else -> {
                carte.setTileProvider(MapTileProviderBasic(applicationContext))
                carte.setTileSource(if (cle == "topo") TileSourceFactory.OpenTopo else TileSourceFactory.MAPNIK)
            }
        }
        reglages.fond = if (fichiers != null || cle == "topo") cle else "osm"
        carte.invalidate()
    }

    // ------------------------------------------------------------------ réglages

    private fun ouvrirReglages() {
        val colonne = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setPadding(dp(16), dp(8), dp(16), dp(8))
        }
        fenetreReglages = colonne
        remplirReglages()
        AlertDialog.Builder(this)
            .setView(ScrollView(this).apply { addView(colonne) })
            .setPositiveButton(R.string.fermer, null)
            .setOnDismissListener { fenetreReglages = null }
            .show()
    }

    /** Le contenu des réglages, refait après chaque changement des lots ou des sources. */
    private fun remplirReglages() {
        val colonne = fenetreReglages ?: return
        colonne.removeAllViews()
        titre(colonne, R.string.titre_itineraire)
        colonne.addView(Switch(this).apply {
            setText(R.string.strict); isChecked = reglages.strict
            setOnCheckedChangeListener { _, v -> reglages.strict = v }
        })
        colonne.addView(Switch(this).apply {
            setText(R.string.officiels); isChecked = reglages.officiels
            setOnCheckedChangeListener { _, v -> reglages.officiels = v }
        })

        titre(colonne, R.string.titre_lots)
        val installes = horsLigne.lots()
        for (lot in installes) {
            val offre = offres.firstOrNull { it.lot.case == lot.case }
            val ligne = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            ligne.addView(TextView(this).apply {
                text = getString(R.string.ligne_installe, lot.case, description(lot), lot.octets / 1_000_000)
            }, LinearLayout.LayoutParams(0, -2, 1f))
            if (offre != null && plusRecent(offre.lot, lot))
                ligne.addView(Button(this).apply { setText(R.string.mettre_a_jour); setOnClickListener { telecharger(offre) } })
            ligne.addView(Button(this).apply { setText(R.string.supprimer); setOnClickListener { supprimerLot(lot) } })
            colonne.addView(ligne)
        }
        if (installes.isEmpty()) colonne.addView(TextView(this).apply { setText(R.string.aucun_lot) })
        val absents = offres.filter { o -> installes.none { it.case == o.lot.case } }
        if (absents.isNotEmpty()) {
            colonne.addView(TextView(this).apply {
                text = getString(R.string.au_catalogue, absents.joinToString(", ") { "${it.lot.case} (${it.lot.octets / 1_000_000} Mo)" })
            })
        }
        colonne.addView(Button(this).apply { setText(R.string.actualiser); setOnClickListener { actualiser() } })

        titre(colonne, R.string.titre_fonds)
        val installesFonds = fonds.installes()
        for (f in installesFonds) {
            val ligne = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            ligne.addView(TextView(this).apply { text = getString(R.string.ligne_fond, f.nameWithoutExtension, f.length() / 1_000_000) },
                LinearLayout.LayoutParams(0, -2, 1f))
            ligne.addView(Button(this).apply {
                setText(R.string.supprimer)
                setOnClickListener {
                    val source = Fonds.source(f.nameWithoutExtension)
                    if (reglages.fond == source) appliquerFond("osm")
                    f.delete()
                    remplirReglages()
                }
            })
            colonne.addView(ligne)
        }
        if (installesFonds.isEmpty()) colonne.addView(TextView(this).apply { setText(R.string.aucun_fond) })

        titre(colonne, R.string.titre_sources)
        colonne.addView(TextView(this).apply { setText(R.string.source_github) })
        for (pc in reglages.pcs()) {
            val ligne = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            ligne.addView(TextView(this).apply { text = pc.libelle }, LinearLayout.LayoutParams(0, -2, 1f))
            ligne.addView(Button(this).apply {
                setText(R.string.oublier)
                setOnClickListener { reglages.oublierPc(pc); remplirReglages() }
            })
            colonne.addView(ligne)
        }
        colonne.addView(TextView(this).apply { setText(R.string.aide_qr) })
        colonne.addView(Button(this).apply { setText(R.string.coller_lien); setOnClickListener { collerLien() } })
    }

    private fun description(lot: Lot): String =
        if (lot.osm) "OSM" else "enrichi ${lot.fournisseurs.joinToString("+")}"

    // ------------------------------------------------------------------ PC

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
            .setMessage(R.string.aide_qr)
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
                remplirReglages()
                actualiser()
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    // ------------------------------------------------------------------ export

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

    // ------------------------------------------------------------------ tâches

    /**
     * Une tâche de fond, une à la fois, avec son état dans le bandeau. Une
     * tâche interruptible reçoit continuer(), que le bouton « Arrêter » rend
     * faux. ensuite(réussie) s'exécute à l'écran une fois la tâche finie.
     */
    private fun tache(message: Int, interruptible: Boolean, travail: (() -> Boolean) -> String,
                      ensuite: ((Boolean) -> Unit)? = null) {
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
            var reussie = false
            val texte = try {
                travail { !arret.get() }.also { reussie = true }
            } catch (e: Abandon) {
                getString(R.string.etat_interrompu)
            } catch (e: Exception) {
                e.message ?: e.toString()
            } finally {
                enCours.set(false)
            }
            runOnUiThread {
                if (isDestroyed) return@runOnUiThread
                etat.text = texte
                progression.visibility = View.GONE
                arreter.visibility = View.GONE
                window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                val reprendre = aReprendre
                ensuite?.invoke(reussie)
                if (reprendre && !enCours.get()) avancer()
            }
        }
    }

    // ------------------------------------------------------------------ outils

    private fun dp(n: Int) = (n * resources.displayMetrics.density).toInt()

    private fun titre(parent: LinearLayout, texte: Int) =
        parent.addView(TextView(this).apply { setText(texte); textSize = 18f; setPadding(0, dp(16), 0, dp(4)) })

    override fun onResume() {
        super.onResume(); carte.onResume()
    }

    override fun onPause() {
        reglages.vue = Triple(carte.mapCenter.latitude, carte.mapCenter.longitude, carte.zoomLevelDouble)
        carte.onPause(); super.onPause()
    }

    override fun onDestroy() {
        routeur.annuler()
        carte.onDetach()
        super.onDestroy()
    }

    companion object {
        private const val EXPORT = 1
        private const val REESSAI_MS = 3_600_000L
        private const val VOILE = 0xe6ffffff.toInt()
        // Au niveau du processus : un téléchargement survit à l'écran qui l'a lancé.
        private val EXECUTEUR = Executors.newSingleThreadExecutor()
        private val enCours = AtomicBoolean(false)
    }
}
