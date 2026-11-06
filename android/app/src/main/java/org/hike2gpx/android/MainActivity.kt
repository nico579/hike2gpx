package org.hike2gpx.android

import android.app.Activity
import android.app.ActivityManager
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Canvas
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.net.ConnectivityManager
import android.net.Uri
import android.provider.Settings
import android.text.InputType
import android.text.format.Formatter
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.database.sqlite.SQLiteDatabase
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.WindowInsets
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast
import com.google.zxing.integration.android.IntentIntegrator
import org.json.JSONArray
import org.osmdroid.config.Configuration
import org.osmdroid.events.MapListener
import org.osmdroid.events.ScrollEvent
import org.osmdroid.events.ZoomEvent
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
import java.util.Locale
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
    private lateinit var calques: Calques
    private lateinit var relief: Mapterhorn
    private lateinit var overlayCalques: CalquesOverlay
    private lateinit var carte: MapView
    private lateinit var etat: TextView
    private lateinit var progression: ProgressBar
    private lateinit var arreter: Button
    private var champVille: EditText? = null
    private var boutonVille: Button? = null
    private var sequenceVille = 0
    private var legende: LinearLayout? = null
    private var courbe: CourbeDenivele? = null
    private var repereProfil: RepereProfil? = null
    private var coordonneesProfil: List<DoubleArray> = emptyList()
    private var distancesProfil: DoubleArray = DoubleArray(0)
    private var echelle: ScaleBarOverlay? = null
    private var droits: CopyrightOverlay? = null
    private val points = mutableListOf<Point>()
    private val reperes = mutableListOf<Marker>()
    private var trace: Polyline? = null
    private var dernier: Resultat? = null
    /** Les catalogues des PC, pour leurs fonds seulement ; null tant qu'ils n'ont pas été lus. */
    private var cataloguesPc: List<Pair<Source, Catalogue>>? = null
    private var offres: List<Offre> = emptyList()
    /** case -> instant (SystemClock) d'un échec ou d'un refus : pas de nouvel essai automatique avant une heure. */
    private val exclues = mutableMapOf<String, Long>()
    /** Les cases retirées à la main : elles ne reviennent pas toutes seules pendant la séance (comme le PC). */
    private val retirees = mutableSetOf<String>()
    /** Un point posé pendant une tâche : on reprend à sa fin. */
    private var aReprendre = false
    /** Case dont le téléchargement automatique est proposé ou en cours. */
    private var autoLotDemande: String? = null
    private var fenetreReglages: LinearLayout? = null
    /** L'APK de mise à jour vérifié, qui attend l'installateur (ou l'autorisation d'installer). */
    private var apkEnAttente: File? = null
    private var attenteAutorisation = false
    private var bilanItineraire = ""
    /** Une lecture de calques à la fois ; une demande pendant ce temps est rejouée à la fin. */
    private val calquesOccupe = AtomicBoolean(false)
    private var calquesARefaire = false
    private var sequenceCalques = 0
    /** Un cochage attend la lecture en cours pour dire si la vue a des chemins. */
    private var calqueCoche = false
    private val planificateur = Handler(Looper.getMainLooper())
    /** Un calcul de relief plus récent remplace celui qui tourne encore. */
    private var sequenceDenivele = 0

    override fun onCreate(etatSauve: Bundle?) {
        super.onCreate(etatSauve)
        Configuration.getInstance().userAgentValue = "${Depot.AGENT} (+https://github.com/nico579/hike2gpx)"
        Configuration.getInstance().osmdroidBasePath = File(cacheDir, "osmdroid")
        Configuration.getInstance().osmdroidTileCache = File(cacheDir, "osmdroid/tiles")
        reglages = Reglages(this)
        horsLigne = HorsLigne(filesDir)
        fonds = Fonds(horsLigne.racine)
        routeur = Routeur(Reglages.profils(this))
        calques = Calques(horsLigne)
        relief = Mapterhorn(filesDir)
        construire()
        appliquerFond(reglages.fond)
        lireLien(intent)
        actualiser()
        verifierMajAuLancement()
        planifierCalques()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        lireLien(intent)
    }

    // ------------------------------------------------------------------ écran

    private fun construire() {
        val racine = FrameLayout(this)
        val vue = reglages.vue
        overlayCalques = CalquesOverlay(this)
        carte = MapView(this).apply {
            setMultiTouchControls(true)
            controller.setZoom(vue.third)
            controller.setCenter(GeoPoint(vue.first, vue.second))
            // Les calques du lot restent sous le tracé et sous les repères.
            overlays.add(0, overlayCalques)
            // Le point de la courbe se dessine juste au-dessus du tracé.
            repereProfil = RepereProfil(this@MainActivity).also { overlays.add(1, it) }
            // Au-dessus de la barre de boutons : l'attribution du fond doit rester lisible.
            droits = CopyrightOverlay(this@MainActivity).apply { setOffset(dp(8), dp(64)) }
            overlays.add(droits)
            echelle = ScaleBarOverlay(this).apply { setAlignBottom(true); setScaleBarOffset(dp(8), dp(84)) }
            overlays.add(echelle)
            overlays.add(MapEventsOverlay(object : MapEventsReceiver {
                override fun singleTapConfirmedHelper(p: GeoPoint): Boolean {
                    ajouterPoint(Point(p.latitude, p.longitude)); return true
                }
                override fun longPressHelper(p: GeoPoint) = false
            }))
            addMapListener(object : MapListener {
                override fun onScroll(event: ScrollEvent): Boolean {
                    planifierCalques(); return false
                }

                override fun onZoom(event: ZoomEvent): Boolean {
                    planifierCalques(); return false
                }
            })
        }
        racine.addView(carte, FrameLayout.LayoutParams(-1, -1))

        val marge = dp(8)
        // Marges posées d'emblée : avant Android 15, l'écran ne passe pas sous
        // les barres du système et le rappel des marges ci-dessous peut ne pas venir.
        val haut = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setBackgroundColor(VOILE); setPadding(marge, marge, marge, marge)
        }
        etat = TextView(this).apply { setText(R.string.etat_pret); setTextColor(0xff202020.toInt()) }
        val recherche = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
        }
        champVille = EditText(this).apply {
            hint = getString(R.string.recherche_placeholder)
            textSize = 14f
            isSingleLine = true
            inputType = InputType.TYPE_CLASS_TEXT
            imeOptions = EditorInfo.IME_ACTION_SEARCH
            setOnEditorActionListener { _, actionId, event ->
                val valide = actionId == EditorInfo.IME_ACTION_SEARCH ||
                    (event != null && event.keyCode == KeyEvent.KEYCODE_ENTER &&
                        event.action == KeyEvent.ACTION_DOWN)
                if (valide) chercherVille()
                valide
            }
        }
        recherche.addView(champVille, LinearLayout.LayoutParams(0, -2, 1f))
        boutonVille = Button(this).apply {
            setText(R.string.recherche_bouton); textSize = 12f; isAllCaps = false
            minWidth = 0; minimumWidth = 0
            setPadding(dp(12), paddingTop, dp(12), paddingBottom)
            setOnClickListener { chercherVille() }
        }
        recherche.addView(boutonVille)
        haut.addView(recherche)
        haut.addView(etat)
        progression = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 1000; visibility = View.GONE
        }
        haut.addView(progression)
        arreter = Button(this).apply { setText(R.string.arreter); visibility = View.GONE }
        haut.addView(arreter, LinearLayout.LayoutParams(-2, -2))
        legende = construireLegende()
        haut.addView(legende)
        racine.addView(haut, FrameLayout.LayoutParams(-1, -2, Gravity.TOP))

        val pied = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        courbe = CourbeDenivele(this).apply {
            visibility = View.GONE
            setBackgroundColor(0xf7ffffff.toInt())
            contentDescription = getString(R.string.courbe_aide)
            onPosition = ::montrerPositionProfil
        }
        pied.addView(courbe, LinearLayout.LayoutParams(-1, dp(96)))
        val bas = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; setBackgroundColor(VOILE); setPadding(marge / 2, marge / 2, marge / 2, marge / 2)
        }
        for ((texte, action) in listOf<Pair<Int, () -> Unit>>(
            R.string.fond to ::choisirFond,
            R.string.retirer to ::retirerPoint,
            R.string.effacer to ::effacer,
            R.string.revenir to ::revenirAuDepart,
            R.string.exporter to ::exporter,
            R.string.reglages to ::ouvrirReglages,
        )) {
            bas.addView(Button(this).apply {
                setText(texte); textSize = 12f; isAllCaps = false; minWidth = 0; minimumWidth = 0
                setPadding(0, paddingTop, 0, paddingBottom)
                setOnClickListener { action() }
            }, LinearLayout.LayoutParams(0, -2, 1f))
        }
        pied.addView(bas, LinearLayout.LayoutParams(-1, -2))
        racine.addView(pied, FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM))

        // Android 15 dessine l'application sous les barres du système : les bandeaux s'en écartent.
        racine.setOnApplyWindowInsetsListener { _, insets ->
            val (dessus, dessous) = if (Build.VERSION.SDK_INT >= 30)
                insets.getInsets(WindowInsets.Type.systemBars()).let { it.top to it.bottom }
            else @Suppress("DEPRECATION") (insets.systemWindowInsetTop to insets.systemWindowInsetBottom)
            haut.setPadding(marge, marge + dessus, marge, marge)
            pied.setPadding(0, 0, 0, dessous)
            insets
        }
        setContentView(racine)
        appliquerAffichage()
    }

    /**
     * La légende de la page, sous le bandeau d'état : les mêmes symboles que
     * ceux dessinés par CalquesOverlay et par le tracé de l'itinéraire. Les
     * couleurs viennent des overlays, pour qu'une légende ne mente jamais sur
     * ce que la carte montre.
     */
    private fun construireLegende(): LinearLayout {
        val boite = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(8), 0, 0)
        }
        boite.addView(TextView(this).apply {
            setText(R.string.legende_titre); textSize = 12f
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            setTextColor(0xff202020.toInt())
        })
        fun ligne(texte: Int, couleur: Int, pastille: Boolean = false, tirets: Boolean = false) {
            val rangee = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            }
            val densite = resources.displayMetrics.density
            // Le même trait que CalquesOverlay : plein, en tirets, ou une pastille cerclée de blanc.
            rangee.addView(object : View(this) {
                private val pinceau = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                    style = Paint.Style.STROKE
                    strokeCap = Paint.Cap.ROUND
                }

                override fun onDraw(canvas: Canvas) {
                    val y = height / 2f
                    if (pastille) {
                        pinceau.style = Paint.Style.FILL
                        pinceau.color = couleur
                        canvas.drawCircle(width / 2f, y, 5 * densite, pinceau)
                        pinceau.style = Paint.Style.STROKE
                        pinceau.strokeWidth = 2 * densite
                        pinceau.color = 0xffffffff.toInt()
                        canvas.drawCircle(width / 2f, y, 5 * densite, pinceau)
                    } else {
                        pinceau.style = Paint.Style.STROKE
                        pinceau.strokeWidth = 3 * densite
                        pinceau.color = couleur
                        pinceau.pathEffect = if (tirets)
                            DashPathEffect(floatArrayOf(4 * densite, 3 * densite), 0f) else null
                        canvas.drawLine(2 * densite, y, width - 2 * densite, y, pinceau)
                    }
                }
            }, LinearLayout.LayoutParams(dp(28), dp(16)))
            rangee.addView(TextView(this).apply {
                setText(texte); textSize = 11f; setTextColor(0xff404040.toInt())
            })
            boite.addView(rangee)
        }
        // Le tracé de l'itinéraire, puis les calques du lot.
        ligne(R.string.legende_itineraire, 0xff175dcb.toInt())
        ligne(R.string.legende_officiel, CalquesOverlay.COULEUR_OFFICIEL, tirets = true)
        ligne(R.string.legende_osm, CalquesOverlay.COULEUR_OSM, tirets = true)
        ligne(R.string.legende_barriere, CalquesOverlay.COULEUR_BARRIERE)
        ligne(R.string.legende_bloque, CalquesOverlay.COULEUR_BLOQUE, true)
        ligne(R.string.legende_verifier, CalquesOverlay.COULEUR_A_VERIFIER, true)
        return boite
    }

    /** Applique les deux coches d'affichage des réglages, sans attendre un redémarrage. */
    private fun appliquerAffichage() {
        legende?.visibility = if (reglages.legende) View.VISIBLE else View.GONE
        afficherCourbe()
    }

    /**
     * La courbe n'a de sens qu'avec un profil calculé. Quand elle prend la
     * place au-dessus des boutons, l'échelle et l'attribution remontent pour
     * rester lisibles, comme les bandeaux de la page.
     */
    private fun afficherCourbe() {
        val vue = courbe ?: return
        val montre = reglages.courbeDenivele && vue.profil != null
        vue.visibility = if (montre) View.VISIBLE else View.GONE
        if (!montre) cacherRepereProfil()
        val hauteur = if (montre) dp(100) else 0
        echelle?.setScaleBarOffset(dp(8), dp(84) + hauteur)
        droits?.setOffset(dp(8), dp(64) + hauteur)
    }

    /** Le point du tracé sous le doigt, comme le circleMarker du profil de la page. */
    private fun montrerPositionProfil(fraction: Double?) {
        val position = fraction?.let { Denivele.positionSurTrace(coordonneesProfil, distancesProfil, it) }
        val geo = position?.let { GeoPoint(it[1], it[0]) }
        if (geo == null) {
            cacherRepereProfil(); return
        }
        repereProfil?.position = geo
        carte.invalidate()
    }

    private fun cacherRepereProfil() {
        val repere = repereProfil ?: return
        if (repere.position == null) return
        repere.position = null
        carte.invalidate()
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

    /**
     * « Revenir » de la page : le départ est ajouté en fin de parcours pour
     * fermer une boucle. Rien à faire sans au moins deux points, ni quand le
     * dernier point est déjà le départ.
     */
    private fun revenirAuDepart() {
        val depart = points.firstOrNull() ?: return
        val dernier = points.last()
        if (points.size < 2 || (depart.lat == dernier.lat && depart.lon == dernier.lon)) return
        ajouterPoint(depart)
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
        sequenceDenivele += 1
        bilanItineraire = ""
        coordonneesProfil = emptyList()
        distancesProfil = DoubleArray(0)
        cacherRepereProfil()
        courbe?.profil = null
        afficherCourbe()
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
            autoLotDemande = aFaire.first().lot.case
            telechargerAuto(aFaire.first()); return
        }
        if (points.size >= 2) calculer()
    }

    private fun calculer() {
        val etapes = points.toList()
        val memoire = (getSystemService(ACTIVITY_SERVICE) as ActivityManager).memoryClass
        sequenceDenivele += 1
        tache(R.string.etat_calcul, false, { _ ->
            val resultat = Itineraire(horsLigne, routeur).calculer(etapes, reglages.strict, reglages.officiels, memoire)
            val proprietes = resultat.feature.optJSONObject("properties")
            val bilan = getString(R.string.etat_itineraire, resultat.lot.case,
                (proprietes?.optString("track-length")?.toDoubleOrNull() ?: 0.0) / 1000)
            runOnUiThread {
                if (etapes == points) {
                    dernier = resultat
                    bilanItineraire = bilan
                    montrer(resultat.coordonnees)
                    etat.text = bilan
                }
            }
            bilan
        }, ensuite = { reussi -> if (reussi && etapes == points) demanderDenivele() })
    }

    /**
     * Le relief du tracé, en arrière-plan comme sur le PC : le tracé s'affiche
     * d'abord, le dénivelé et la durée de marche arrivent ensuite. Le calcul
     * n'occupe pas la tâche unique, un autre parcours reste possible.
     */
    private fun demanderDenivele() {
        val resultat = dernier ?: return
        val base = bilanItineraire
        val coordonnees = List(resultat.coordonnees.length()) { i ->
            val p = resultat.coordonnees.getJSONArray(i)
            doubleArrayOf(p.getDouble(0), p.getDouble(1))
        }
        val sequence = ++sequenceDenivele
        etat.text = listOf(base, getString(R.string.etat_denivele_calcul)).filter { it.isNotEmpty() }.joinToString("\n")
        EXECUTEUR_DENIVELE.execute {
            var profil: ProfilAltimetrique? = null
            var erreur = ""
            try {
                relief.preparer(coordonnees)
                profil = Denivele.calculer(coordonnees, relief, "Mapterhorn")
            } catch (e: Exception) {
                erreur = e.message ?: e.toString()
            }
            val calcule = profil
            runOnUiThread {
                if (sequence != sequenceDenivele || dernier !== resultat || isDestroyed) return@runOnUiThread
                etat.text = if (calcule != null)
                    listOf(base, getString(R.string.etat_denivele, calcule.monteeM, calcule.descenteM,
                        duree(calcule.dureeMarcheS))).filter { it.isNotEmpty() }.joinToString("\n")
                else
                    listOf(base, getString(R.string.etat_denivele_indisponible, erreur.take(160)))
                        .filter { it.isNotEmpty() }.joinToString("\n")
                courbe?.profil = calcule
                afficherCourbe()
            }
        }
    }

    /** La durée de marche arrondie au quart d'heure supérieur, comme la page. */
    private fun duree(secondes: Long): String {
        val minutes = (((secondes + 299) / 300) * 5).toInt()
        return if (minutes >= 60) getString(R.string.duree_heures, minutes / 60, minutes % 60)
        else getString(R.string.duree_minutes, minutes)
    }

    private fun montrer(coordonnees: JSONArray) {
        trace?.let { carte.overlays.remove(it) }
        cacherRepereProfil()
        courbe?.profil = null
        afficherCourbe()
        val geo = List(coordonnees.length()) {
            coordonnees.getJSONArray(it).let { p -> GeoPoint(p.getDouble(1), p.getDouble(0)) }
        }
        // Le tracé complet, distances cumulées comprises : la courbe s'y
        // reporte au doigt, comme positionSurProfil sur la page.
        coordonneesProfil = List(coordonnees.length()) { i ->
            coordonnees.getJSONArray(i).let { p -> doubleArrayOf(p.getDouble(0), p.getDouble(1)) }
        }
        distancesProfil = Denivele.distances(coordonneesProfil)
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

    // ------------------------------------------------------------------ calques du lot

    /**
     * Une coche sous le zoom 14 ne montre rien : le dire tout de suite, sinon
     * la case semble sans effet. Au-dessus, la lecture prévient si la vue ne
     * contient aucun chemin de calque.
     */
    private fun signalerCocheCalque() {
        if (carte.zoomLevelDouble < ZOOM_CALQUES) {
            calqueCoche = false
            Toast.makeText(this, R.string.calque_zoom, Toast.LENGTH_LONG).show()
        } else {
            calqueCoche = true
        }
    }

    /**
     * Les calques ne se lisent qu'au zoom 14, celui des tuiles du lot, comme
     * la page ; en dessous, mieux vaut ne rien montrer qu'un réseau tronqué.
     */
    private fun planifierCalques() {
        sequenceCalques += 1
        planificateur.removeCallbacksAndMessages(null)
        if ((!reglages.calqueOsm && reglages.calquesOfficiels.isEmpty()) ||
            carte.zoomLevelDouble < ZOOM_CALQUES) {
            calqueCoche = false
            overlayCalques.donnees = DonneesCalques()
            carte.invalidate()
            return
        }
        proposerLotCalques()
        planificateur.postDelayed({ rafraichirCalques() }, 350)
    }

    /**
     * Comme la page, afficher un calque est un usage réel de la région : le
     * lot de la case du centre se télécharge de lui-même s'il manque, ou si
     * le catalogue en a un plus récent. Un survol sous le zoom 14 ne suffit
     * pas, et une case refusée ou en échec attend une heure.
     */
    private fun proposerLotCalques() {
        if (enCours.get() || autoLotDemande != null) return
        val boite = carte.boundingBox ?: return
        val maintenant = SystemClock.elapsedRealtime()
        val exclu = exclues.filterValues { maintenant - it < REESSAI_MS }.keys + retirees
        val zone = Zone(boite.latSouth, boite.lonWest, boite.latNorth, boite.lonEast)
        val offre = offreAuCentre(offres, horsLigne.lots(), zone, exclu) ?: return
        autoLotDemande = offre.lot.case
        telechargerAuto(offre)
    }

    /** Lit les tuiles de la vue en arrière-plan ; une lecture à la fois. */
    private fun rafraichirCalques() {
        if (isDestroyed) return
        val osm = reglages.calqueOsm
        val officiels = reglages.calquesOfficiels
        if ((!osm && officiels.isEmpty()) || carte.zoomLevelDouble < ZOOM_CALQUES) {
            calqueCoche = false
            overlayCalques.donnees = DonneesCalques()
            carte.invalidate()
            return
        }
        val boite = carte.boundingBox ?: return
        if (!calquesOccupe.compareAndSet(false, true)) {
            calquesARefaire = true
            return
        }
        val sequence = ++sequenceCalques
        val zone = Zone(boite.latSouth, boite.lonWest, boite.latNorth, boite.lonEast)
        EXECUTEUR_CALQUES.execute {
            val donnees = try {
                calques.lire(zone, osm, officiels)
            } catch (e: Exception) {
                DonneesCalques()
            }
            calquesOccupe.set(false)
            runOnUiThread {
                if (isDestroyed) return@runOnUiThread
                if (sequence == sequenceCalques) {
                    overlayCalques.donnees = donnees
                    carte.invalidate()
                    if (calqueCoche) {
                        calqueCoche = false
                        if (donnees.vide && !enCours.get() && autoLotDemande == null)
                            Toast.makeText(this, R.string.calque_vide, Toast.LENGTH_LONG).show()
                    }
                }
                if (calquesARefaire) {
                    calquesARefaire = false
                    planifierCalques()
                }
            }
        }
    }

    // ------------------------------------------------------------------ lots

    /**
     * Le catalogue des lots, lu sur GitHub seulement (décision de Nico du
     * 2026-11-04) : le serveur publie les lots, un PC ne sert au téléphone que
     * ses fonds de carte (lireFondsPc). Un PC éteint ne retarde donc jamais le
     * lancement.
     */
    private fun actualiser() = tache(R.string.etat_catalogue, false, { _ ->
        val choix = choisir(listOf(Source.GITHUB to Depot().lireCatalogue(Source.GITHUB)))
        runOnUiThread { offres = choix; remplirReglages(); planifierCalques() }
        if (points.isEmpty()) getString(R.string.etat_pret) else getString(R.string.etat_catalogue_lu, choix.size)
    }, ensuite = { avancer() })

    /** Les fonds partagés par les PC, lus à la demande (bouton Fond, PC ajouté) ; un PC injoignable le dit sans rien bloquer. */
    private fun lireFondsPc(ensuite: () -> Unit) = tache(R.string.etat_fonds_pc, false, { _ ->
        val lus = mutableListOf<Pair<Source, Catalogue>>()
        val echecs = mutableListOf<String>()
        for (pc in reglages.pcs()) {
            try {
                lus.add(pc to Depot().lireCatalogue(pc))
            } catch (e: ErreurDepot) {
                echecs.add(texte(e))
            }
        }
        runOnUiThread { cataloguesPc = lus }
        if (echecs.isEmpty()) getString(R.string.etat_fonds_pc_lus, lus.sumOf { it.second.fonds.size })
        else echecs.joinToString("\n")
    }, ensuite = { ensuite() })

    /** Le lot qui manque : de lui-même sur le Wi-Fi, sur demande sur un réseau facturé. */
    private fun telechargerAuto(offre: Offre) {
        autoLotDemande = offre.lot.case
        val reseau = getSystemService(ConnectivityManager::class.java)
        if (reseau.activeNetwork == null) {
            autoLotDemande = null
            // Un calque sans réseau ne réessaie pas en boucle ; un parcours, lui, le dit à chaque calcul.
            if (points.size < 2) exclues[offre.lot.case] = SystemClock.elapsedRealtime()
            if (points.size >= 2) calculer()
            return
        }
        if (!reseau.isActiveNetworkMetered) {
            autoLotDemande = null
            telecharger(offre); return
        }
        AlertDialog.Builder(this)
            .setTitle(offre.lot.case)
            .setMessage(getString(R.string.confirmer_donnees_mobiles, offre.lot.case,
                Formatter.formatShortFileSize(this, offre.lot.octets), offre.source.libelle))
            .setPositiveButton(R.string.telecharger) { _, _ ->
                autoLotDemande = null
                telecharger(offre)
            }
            .setNegativeButton(R.string.plus_tard) { _, _ ->
                autoLotDemande = null
                exclues[offre.lot.case] = SystemClock.elapsedRealtime()
                avancer()
                planifierCalques()
            }
            .setCancelable(false)
            .show()
    }

    private fun telecharger(offre: Offre) {
        autoLotDemande = null
        val lot = offre.lot
        tache(R.string.etat_telechargement, true, { continuer ->
            runOnUiThread { etat.text = getString(R.string.etat_telechargement_lot, lot.case,
                Formatter.formatShortFileSize(this, lot.octets)) }
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
            planifierCalques()
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
                etat.text = getString(R.string.etat_supprime, lot.case,
                    Formatter.formatShortFileSize(this, octets))
                remplirReglages()
                planifierCalques()
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    // ------------------------------------------------------------------ fonds de carte

    /** Les fonds en ligne, les fonds hors ligne installés, et ceux que les PC proposent. */
    private fun choisirFond() {
        if (reglages.pcs().isNotEmpty() && cataloguesPc == null) {
            lireFondsPc { choisirFond() }; return
        }
        val choix = mutableListOf<Pair<String, () -> Unit>>()
        choix.add(getString(R.string.fond_osm) to { appliquerFond("osm") })
        choix.add(getString(R.string.fond_topo) to { appliquerFond("topo") })
        for ((source, fichiers) in fonds.parSource()) {
            choix.add(getString(R.string.fond_hors_ligne, Fonds.titre(source), fichiers.size,
                Formatter.formatShortFileSize(this, fichiers.sumOf { it.length() })) to
                { appliquerFond(source); cadrerSur(fichiers) })
        }
        val proposes = fondsProposes(cataloguesPc ?: emptyList(), fonds.installes().map { it.nameWithoutExtension }.toSet())
        for ((source, fond) in proposes) {
            choix.add(getString(R.string.fond_a_telecharger, Fonds.titre(fond.source), fond.nom,
                Formatter.formatShortFileSize(this, fond.octets), source.libelle) to
                { telechargerFond(source, fond) })
        }
        if (reglages.pcs().isEmpty()) choix.add(getString(R.string.fond_sans_pc) to { scannerQr() })
        else if (proposes.isEmpty()) choix.add(getString(R.string.fond_relire) to { cataloguesPc = null; choisirFond() })
        AlertDialog.Builder(this)
            .setTitle(R.string.titre_fond)
            .setItems(choix.map { it.first }.toTypedArray()) { _, i -> choix[i].second() }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun telechargerFond(source: Source, fond: Fond) {
        AlertDialog.Builder(this)
            .setTitle(fond.nom)
            .setMessage(getString(R.string.confirmer_telechargement,
                Formatter.formatShortFileSize(this, fond.octets), source.libelle))
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

    /** La table metadata d'un MBTiles (bounds « ouest,sud,est,nord », minzoom…), vide si illisible. */
    private fun metadonnees(f: File): Map<String, String> = try {
        SQLiteDatabase.openDatabase(f.path, null, SQLiteDatabase.OPEN_READONLY).use { base ->
            base.rawQuery("SELECT name, value FROM metadata", null).use { c ->
                buildMap { while (c.moveToNext()) put(c.getString(0), c.getString(1)) }
            }
        }
    } catch (e: Exception) {
        emptyMap()
    }

    /**
     * Le zoom le plus bas des fichiers d'un fond : en deçà, ils n'ont pas une
     * tuile, la carte resterait vide ou en morceaux. Un carré de 1° commence au
     * 13 (fonds.ZOOMS_CARRE) ; les fonds plus anciens d'une case, au 6.
     */
    private fun zoomMin(fichiers: List<File>): Int =
        fichiers.mapNotNull { metadonnees(it)["minzoom"]?.toIntOrNull() }.minOrNull() ?: 0

    /**
     * Un fond hors ligne ne couvre que sa zone : si la vue n'est dans aucun de
     * ses fichiers, la carte se centre sur le premier, d'après ses bornes, à un
     * zoom où il a des tuiles (cadrer le carré entier dézoomerait sous son minzoom).
     */
    private fun cadrerSur(fichiers: List<File>) {
        val boites = fichiers.mapNotNull { f ->
            metadonnees(f)["bounds"]?.split(',')?.mapNotNull { it.trim().toDoubleOrNull() }?.takeIf { it.size == 4 }
                ?.let { (o, s, e, n) -> BoundingBox(n, e, s, o) }
        }
        if (boites.isEmpty() || boites.any { it.contains(carte.mapCenter) }) return
        carte.controller.setZoom(maxOf(carte.zoomLevelDouble, zoomMin(fichiers).toDouble()))
        carte.controller.setCenter(boites.first().centerWithDateLine)
    }

    /**
     * Le fond de la carte. Un fond hors ligne réunit tous les MBTiles de sa
     * source ; osmdroid agrandit au-delà de leur zoom le plus fin, comme la page
     * (maxNativeZoom), et ne demande rien au réseau. La carte ne descend pas
     * sous son zoom le plus bas, où elle n'aurait rien à montrer.
     */
    private fun appliquerFond(cle: String) {
        val fichiers = fonds.parSource()[cle]
        when {
            fichiers != null -> {
                val minimum = zoomMin(fichiers)
                carte.setTileProvider(OfflineTileProvider(SimpleRegisterReceiver(this), fichiers.toTypedArray()))
                carte.setTileSource(XYTileSource("hors-ligne-$cle", minimum, 19, 256, "", arrayOf<String>(),
                    "© ${Fonds.titre(cle)}"))
                carte.setMinZoomLevel(minimum.toDouble())
                if (carte.zoomLevelDouble < minimum) carte.controller.setZoom(minimum.toDouble())
            }
            else -> {
                carte.setTileProvider(MapTileProviderBasic(applicationContext))
                carte.setTileSource(if (cle == "topo") TileSourceFactory.OpenTopo else TileSourceFactory.MAPNIK)
                carte.setMinZoomLevel(null)         // le zoom le plus bas de la source en ligne
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

        titre(colonne, R.string.titre_calques)
        colonne.addView(CheckBox(this).apply {
            setText(R.string.calque_osm); isChecked = reglages.calqueOsm
            setOnCheckedChangeListener { _, v ->
                reglages.calqueOsm = v
                if (v) signalerCocheCalque() else calqueCoche = false
                planifierCalques()
            }
        })
        for (fournisseur in fournisseursDisponibles()) {
            colonne.addView(CheckBox(this).apply {
                text = getString(R.string.calque_fournisseur, fournisseur.nom)
                isChecked = reglages.calqueOfficiel(fournisseur.cle)
                setOnCheckedChangeListener { _, v ->
                    reglages.changerCalqueOfficiel(fournisseur.cle, v)
                    if (v) signalerCocheCalque() else calqueCoche = false
                    planifierCalques()
                }
            })
        }
        colonne.addView(TextView(this).apply {
            text = getString(R.string.calque_aide, String.format(Locale.getDefault(), "%.1f", carte.zoomLevelDouble))
            textSize = 12f
        })

        titre(colonne, R.string.titre_affichage)
        colonne.addView(CheckBox(this).apply {
            setText(R.string.afficher_legende); isChecked = reglages.legende
            setOnCheckedChangeListener { _, v -> reglages.legende = v; appliquerAffichage() }
        })
        colonne.addView(CheckBox(this).apply {
            setText(R.string.afficher_courbe); isChecked = reglages.courbeDenivele
            setOnCheckedChangeListener { _, v -> reglages.courbeDenivele = v; afficherCourbe() }
        })

        titre(colonne, R.string.titre_lots)
        val installes = horsLigne.lots()
        for (lot in installes) {
            val offre = offres.firstOrNull { it.lot.case == lot.case }
            val ligne = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            ligne.addView(TextView(this).apply {
                text = getString(R.string.ligne_installe, lot.case, description(lot),
                    Formatter.formatShortFileSize(this@MainActivity, lot.octets))
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
                text = getString(R.string.au_catalogue, absents.joinToString(", ") {
                    "${it.lot.case} (${Formatter.formatShortFileSize(this@MainActivity, it.lot.octets)})"
                })
            })
        }
        colonne.addView(Button(this).apply { setText(R.string.actualiser); setOnClickListener { actualiser() } })

        titre(colonne, R.string.titre_fonds)
        val installesFonds = fonds.installes()
        for (f in installesFonds) {
            val ligne = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            ligne.addView(TextView(this).apply { text = getString(R.string.ligne_fond, f.nameWithoutExtension,
                Formatter.formatShortFileSize(this@MainActivity, f.length())) },
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
                setOnClickListener { reglages.oublierPc(pc); cataloguesPc = null; remplirReglages() }
            })
            colonne.addView(ligne)
        }
        colonne.addView(TextView(this).apply { setText(R.string.aide_qr) })
        colonne.addView(Button(this).apply { setText(R.string.scanner_qr); setOnClickListener { scannerQr() } })
        colonne.addView(Button(this).apply { setText(R.string.coller_lien); setOnClickListener { collerLien() } })

        titre(colonne, R.string.titre_cache)
        colonne.addView(Button(this).apply {
            text = getString(R.string.vider_cache, Formatter.formatShortFileSize(this@MainActivity, octetsCaches()))
            setOnClickListener { viderCache() }
        })

        titre(colonne, R.string.maj_titre)
        colonne.addView(TextView(this).apply { text = getString(R.string.maj_version, versionInstallee()) })
        colonne.addView(Button(this).apply { setText(R.string.maj_verifier); setOnClickListener { verifierMaj() } })
    }

    // ------------------------------------------------------------------ recherche de ville

    /**
     * La recherche de la page : une ville recentre la carte, des coordonnées
     * aussi. La requête part en arrière-plan (elle passe par le réseau) ; le
     * bouton reste occupé jusque-là, et une réponse plus ancienne ne peut pas
     * écraser la plus récente.
     */
    private fun chercherVille() {
        val champ = champVille ?: return
        val demande = champ.text.toString().trim()
        if (demande.length < 2) {
            Toast.makeText(this, R.string.recherche_court, Toast.LENGTH_SHORT).show()
            return
        }
        val sequence = ++sequenceVille
        val coordonnees = Communes.lireCoordonnees(demande)
        if (coordonnees != null) {
            centrerSurVille(coordonnees.first, coordonnees.second, 14.0)
            return
        }
        cacherClavier()
        val bouton = boutonVille ?: return
        bouton.isEnabled = false
        bouton.setText(R.string.recherche_attente)
        Thread {
            var villes: List<Ville>? = null
            var erreur = ""
            try {
                villes = Communes.chercher(demande)
            } catch (e: Exception) {
                erreur = e.message ?: e.toString()
            }
            val trouvees = villes
            runOnUiThread {
                if (sequence != sequenceVille || isDestroyed) return@runOnUiThread
                bouton.isEnabled = true
                bouton.setText(R.string.recherche_bouton)
                when {
                    trouvees == null -> Toast.makeText(this,
                        getString(R.string.recherche_erreur, erreur.take(160)),
                        Toast.LENGTH_LONG).show()
                    trouvees.isEmpty() ->
                        Toast.makeText(this, R.string.recherche_aucun, Toast.LENGTH_SHORT).show()
                    trouvees.size == 1 -> choisirVille(trouvees[0])
                    else -> AlertDialog.Builder(this)
                        .setTitle(R.string.recherche_titre)
                        .setItems(trouvees.map { if (it.detail.isEmpty()) it.nom else "${it.nom} · ${it.detail}" }
                            .toTypedArray()) { _, i -> choisirVille(trouvees[i]) }
                        .show()
                }
            }
        }.start()
    }

    private fun choisirVille(ville: Ville) {
        champVille?.setText(ville.nom)
        champVille?.setSelection(ville.nom.length)
        centrerSurVille(ville.lat, ville.lon, 13.0)
    }

    private fun centrerSurVille(lat: Double, lon: Double, zoom: Double) {
        cacherClavier()
        carte.controller.setZoom(zoom)
        carte.controller.setCenter(GeoPoint(lat, lon))
        carte.invalidate()
        planifierCalques()
    }

    private fun cacherClavier() {
        val champ = champVille ?: return
        (getSystemService(INPUT_METHOD_SERVICE) as? InputMethodManager)
            ?.hideSoftInputFromWindow(champ.windowToken, 0)
        champ.clearFocus()
    }

    // ------------------------------------------------------------------ mise à jour

    /** La version installée, celle de hike2gpx/__init__.py (build.gradle.kts), sans le suffixe « -essai » de l'APK de débogage. */
    private fun versionInstallee(): String =
        (packageManager.getPackageInfo(packageName, 0).versionName ?: "0.0.0").substringBefore('-')

    /**
     * Au lancement, sans bruit, comme le PC : une version plus récente se
     * propose, un échec ne dit rien. L'APK d'essai (.debug) ne s'y compare pas :
     * la release n'est pas son paquet.
     */
    private fun verifierMajAuLancement() {
        if (packageName.endsWith(".debug")) return
        Thread {
            val publication = try {
                ClientMaj().verifier(versionInstallee())
            } catch (e: Exception) {
                null
            }
            if (publication != null) runOnUiThread { if (!isDestroyed) proposerMaj(publication) }
        }.start()
    }

    /** Depuis les réglages : le résultat, quel qu'il soit, s'affiche. */
    private fun verifierMaj() {
        etat.setText(R.string.maj_verification)
        Thread {
            val message = try {
                val publication = ClientMaj().verifier(versionInstallee())
                if (publication != null) {
                    runOnUiThread { proposerMaj(publication) }; null
                } else getString(R.string.maj_a_jour, versionInstallee())
            } catch (e: Exception) {
                texte(e)
            }
            if (message != null) runOnUiThread { etat.text = message }
        }.start()
    }

    private fun proposerMaj(publication: Publication) {
        AlertDialog.Builder(this)
            .setTitle(R.string.maj_titre)
            .setMessage(getString(R.string.maj_disponible, publication.version, versionInstallee(),
                Formatter.formatShortFileSize(this, publication.octets)))
            .setPositiveButton(R.string.maj_installer) { _, _ -> telechargerMaj(publication) }
            .setNegativeButton(R.string.plus_tard, null)
            .show()
    }

    /** L'APK téléchargé, contrôlé (taille, SHA-256, paquet, version, signature), puis confié à l'installateur. */
    private fun telechargerMaj(publication: Publication) {
        tache(R.string.maj_telechargement, true, { continuer ->
            val apk = ClientMaj().telecharger(publication, MiseAJour.dossier(this), { faits, total ->
                runOnUiThread { progression.progress = (1000 * faits / maxOf(total, 1)).toInt() }
            }, continuer)
            MiseAJour.verifier(this, apk, publication)
            apkEnAttente = apk
            getString(R.string.maj_prete, publication.version)
        }, ensuite = { reussie -> if (reussie) installerMaj() })
    }

    /**
     * L'installateur d'Android. La première fois, Android demande d'autoriser
     * hike2gpx à installer des applications : on ouvre ce réglage, et l'on
     * reprend au retour (onResume).
     */
    private fun installerMaj() {
        val apk = apkEnAttente ?: return
        if (!packageManager.canRequestPackageInstalls()) {
            attenteAutorisation = true
            etat.setText(R.string.maj_autorisation)
            startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:$packageName")))
            return
        }
        apkEnAttente = null
        try {
            startActivity(Intent(Intent.ACTION_VIEW)
                .setDataAndType(MiseAJour.uri(this, apk), "application/vnd.android.package-archive")
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
        } catch (e: Exception) {
            etat.setText(R.string.maj_installateur)
        }
    }

    /** Ce que le vidage efface : lots et fonds, téléchargements interrompus, tuiles en ligne gardées par osmdroid. */
    private fun caches(): List<File> =
        listOf(horsLigne.racine, File(filesDir, "telechargements"), File(filesDir, "gpx2elev"),
            File(cacheDir, "osmdroid"))

    private fun octetsCaches(): Long = caches().sumOf { d -> d.walkTopDown().filter { it.isFile }.sumOf { it.length() } }

    /**
     * Le vidage du cache, comme sur le PC (application, action vider_cache) :
     * tout repart de zéro, lots et fonds compris ; ceux du serveur reviennent
     * d'eux-mêmes au prochain parcours qui en a besoin.
     */
    private fun viderCache() {
        AlertDialog.Builder(this)
            .setTitle(R.string.titre_cache)
            .setMessage(getString(R.string.confirmer_vider_cache,
                Formatter.formatShortFileSize(this, octetsCaches())))
            .setPositiveButton(R.string.vider) { _, _ ->
                if (enCours.get()) {
                    etat.setText(R.string.etat_occupe_cache); return@setPositiveButton
                }
                routeur.annuler()
                val octets = octetsCaches()
                horsLigne.vider()
                caches().forEach { it.deleteRecursively() }
                retirees.clear()
                exclues.clear()
                effacerTrace()
                appliquerFond(if (reglages.fond == "topo") "topo" else "osm")     // un fournisseur neuf, sur un cache neuf
                etat.text = getString(R.string.etat_cache_vide,
                    Formatter.formatShortFileSize(this, octets))
                remplirReglages()
                planifierCalques()
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    /** Les fournisseurs nationaux des lots installés : chacun a sa coche de calque. */
    private fun fournisseursDisponibles(): List<Fournisseur> =
        horsLigne.lots().flatMap { Fournisseurs.duLot(it) }
            .distinctBy { it.cle }.sortedBy { it.nom }

    private fun description(lot: Lot): String =
        if (lot.osm) "OSM" else getString(R.string.lot_enrichi,
            Fournisseurs.duLot(lot).joinToString("+") { it.nom }
                .ifEmpty { lot.fournisseurs.joinToString("+") })

    // ------------------------------------------------------------------ PC

    /** Un lien hike2gpx://depot reçu du QR code d'un PC (lu par l'appareil photo). */
    private fun lireLien(intent: Intent?) {
        val lien = intent?.data?.toString() ?: return
        if (!lien.startsWith("hike2gpx:")) return
        try {
            ajouterPc(LienDepot.lire(lien))
        } catch (e: ErreurDepot) {
            etat.text = texte(e)
        }
    }

    /** Le QR code affiché par le PC, lu par la caméra du téléphone (zxing-android-embedded, comme watch2notif). */
    private fun scannerQr() {
        IntentIntegrator(this)
            .setDesiredBarcodeFormats(IntentIntegrator.QR_CODE)
            .setPrompt(getString(R.string.scan_invite))
            .setBeepEnabled(false)
            .setOrientationLocked(false)
            .initiateScan()
    }

    /** Le texte lu dans un QR code : le même chemin que le lien ouvert par l'appareil photo, confirmation comprise. */
    private fun lienScanne(texte: String) {
        try {
            ajouterPc(LienDepot.lire(texte))
        } catch (e: ErreurDepot) {
            etat.text = texte(e)
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
                    etat.text = texte(e)
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
                cataloguesPc = null
                choisirFond()       // ce que le PC apporte au téléphone : ses fonds
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
        IntentIntegrator.parseActivityResult(requete, resultat, donnees)?.let { scan ->
            scan.contents?.let { lienScanne(it) }       // null : scan annulé
            return
        }
        val coordonnees = dernier?.coordonnees ?: return
        val adresse = donnees?.data ?: return
        if (requete != EXPORT || resultat != RESULT_OK) return
        try {
            contentResolver.openOutputStream(adresse)?.use { it.write(Gpx.ecrire(coordonnees).toByteArray()) }
            etat.setText(R.string.export_fait)
        } catch (e: Exception) {
            etat.text = texte(e)
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
            val bilan = try {
                travail { !arret.get() }.also { reussie = true }
            } catch (e: Abandon) {
                getString(R.string.etat_interrompu)
            } catch (e: Exception) {
                texte(e)
            } finally {
                enCours.set(false)
            }
            runOnUiThread {
                if (isDestroyed) return@runOnUiThread
                etat.text = bilan
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
        if (attenteAutorisation) {
            attenteAutorisation = false
            if (packageManager.canRequestPackageInstalls()) installerMaj() else etat.setText(R.string.maj_autorisation_refusee)
        }
    }

    override fun onPause() {
        reglages.vue = Triple(carte.mapCenter.latitude, carte.mapCenter.longitude, carte.zoomLevelDouble)
        carte.onPause(); super.onPause()
    }

    override fun onDestroy() {
        planificateur.removeCallbacksAndMessages(null)
        routeur.annuler()
        carte.onDetach()
        super.onDestroy()
    }

    companion object {
        private const val EXPORT = 1
        private const val REESSAI_MS = 3_600_000L
        private const val VOILE = 0xe6ffffff.toInt()
        /** Le zoom des tuiles vectorielles du lot, et celui où la page montre les calques. */
        private const val ZOOM_CALQUES = 14.0
        // Au niveau du processus : un téléchargement survit à l'écran qui l'a lancé.
        private val EXECUTEUR = Executors.newSingleThreadExecutor()
        // Les calques et le relief ne prennent pas la tâche unique : l'itinéraire
        // reste calculable pendant qu'ils se lisent.
        private val EXECUTEUR_CALQUES = Executors.newSingleThreadExecutor()
        private val EXECUTEUR_DENIVELE = Executors.newSingleThreadExecutor()
        private val enCours = AtomicBoolean(false)
    }
}
