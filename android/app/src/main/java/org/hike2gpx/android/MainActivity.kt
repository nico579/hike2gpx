package org.hike2gpx.android

import android.annotation.SuppressLint
import android.app.Activity
import android.app.ActivityManager
import android.app.AlertDialog
import android.app.DownloadManager
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Dialog
import android.Manifest
import android.content.ContentValues
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.Typeface
import android.graphics.drawable.ColorDrawable
import android.graphics.drawable.GradientDrawable
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.net.ConnectivityManager
import android.net.Uri
import android.provider.MediaStore
import android.provider.OpenableColumns
import android.provider.Settings
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.text.format.DateUtils
import android.text.format.Formatter
import android.text.method.PasswordTransformationMethod
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.window.OnBackInvokedCallback
import android.window.OnBackInvokedDispatcher
import androidx.annotation.RequiresApi
import android.database.sqlite.SQLiteDatabase
import android.view.Gravity
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.WindowInsets
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.ScrollView
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast
import com.google.zxing.integration.android.IntentIntegrator
import kotlin.concurrent.thread
import org.json.JSONArray
import org.mapsforge.map.rendertheme.InternalRenderTheme
import org.osmdroid.config.Configuration
import org.osmdroid.events.MapListener
import org.osmdroid.events.ScrollEvent
import org.osmdroid.events.ZoomEvent
import org.osmdroid.events.MapEventsReceiver
import org.osmdroid.mapsforge.MapsForgeTileProvider
import org.osmdroid.mapsforge.MapsForgeTileSource
import org.osmdroid.tileprovider.MapTileProviderBase
import org.osmdroid.tileprovider.MapTileProviderBasic
import org.osmdroid.tileprovider.modules.OfflineTileProvider
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.tileprovider.tilesource.XYTileSource
import org.osmdroid.tileprovider.util.SimpleRegisterReceiver
import org.osmdroid.util.BoundingBox
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.CustomZoomButtonsController
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.CopyrightOverlay
import org.osmdroid.views.overlay.MapEventsOverlay
import org.osmdroid.views.overlay.Marker
import org.osmdroid.views.overlay.Overlay
import org.osmdroid.views.overlay.Polyline
import org.osmdroid.views.overlay.ScaleBarOverlay
import org.osmdroid.views.overlay.milestones.MilestoneBitmapDisplayer
import org.osmdroid.views.overlay.milestones.MilestoneManager
import org.osmdroid.views.overlay.milestones.MilestoneMeterDistanceLister
import java.io.File
import java.io.IOException
import java.text.SimpleDateFormat
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Date
import java.util.Locale
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.log2
import kotlin.math.roundToInt

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
    private var rechercheVille: LinearLayout? = null
    private var sequenceVille = 0
    private var legende: LinearLayout? = null
    /** Les lignes de la légende, par identifiant (legende.json) ; chacune n'est montrée que si son objet est sur la carte. */
    private val lignesLegende = mutableMapOf<String, LinearLayout>()
    /** Le texte de la ligne « chemin IGN » : le réseau dépend du lot qui couvre la vue. */
    private var texteOfficiel: TextView? = null
    /** Vrai tant qu'aucune ligne de la légende n'est montrée : le panneau disparaît alors. */
    private var legendeVide = true
    private var courbe: CourbeDenivele? = null
    /** L'en-tête de la courbe : titre, résumé quand elle est repliée, chevron. Un toucher la replie ou la déplie. */
    private var enteteCourbe: LinearLayout? = null
    private var resumeCourbe: TextView? = null
    private var chevronCourbe: TextView? = null
    private var repereProfil: RepereProfil? = null
    private var coordonneesProfil: List<DoubleArray> = emptyList()
    private var distancesProfil: DoubleArray = DoubleArray(0)
    private lateinit var bandeauHaut: LinearLayout
    private lateinit var bandeauBas: LinearLayout
    private var bandeauxMasques = false
    private var positionOverlay: PositionOverlay? = null
    private lateinit var boutonPosition: BoutonRond
    private lateinit var boutonTrace: BoutonRond
    private lateinit var boutonMenu: BoutonRond
    private var commandesCarte: LinearLayout? = null
    private var commandesTrace: LinearLayout? = null
    /** La planification n'affiche ses commandes que lorsqu'on la choisit dans le menu. */
    private var modePlan = false
    /** La recherche de ville se referme après le choix d'une ville. */
    private var modeRecherche = false
    /**
     * Une recherche qui a abouti (ou un tap sur la carte) referme son bandeau :
     * la carte reste seule jusqu'au prochain mode choisi dans le menu.
     */
    private var rechercheRepliee = false
    /** Une tâche de fond montre son état quelques secondes, même hors mode. */
    private var tacheAffichee = false
    private var sequenceTache = 0
    /**
     * Ce qu'un PC a partagé et qui reste à télécharger, après la confirmation :
     * une tâche à la fois, la suivante à la fin de la précédente (tache).
     */
    private val recuperations = ArrayDeque<() -> Unit>()
    private var ecoutePosition: LocationListener? = null
    private var apresPermission: (() -> Unit)? = null
    private var centrerDesQuePosition = false
    private var traceEnregistree: Polyline? = null
    private var fichierTrace: File? = null
    private var insetBas = 0
    private var insetHaut = 0
    /** Le relief de la trace : cache gpx2elev seulement, sans réseau. */
    private lateinit var reliefTrace: Mapterhorn
    private val traceOccupe = AtomicBoolean(false)
    @Volatile private var traceARefaire = false
    private var contenuExport: ByteArray? = null
    // Les zones et les cartes cochées pour l'archive, en attendant le choix du fichier.
    private var archiveAEcrire: Pair<List<Lot>, List<File>>? = null
    private var echelle: ScaleBarOverlay? = null
    private var droits: CopyrightOverlay? = null
    private val points = mutableListOf<Point>()
    private val reperes = mutableListOf<Marker>()
    private var trace: Polyline? = null
    // Les flèches du sens de marche, posées par osmdroid le long du tracé (ses « milestones »).
    private var flechesTrace: List<MilestoneManager> = emptyList()
    /** Les traces importées (GPX, KML), dessinées sur la carte, et le nom du fichier : null sans import. */
    private val tracesImportees = mutableListOf<Polyline>()
    private var nomImport: String? = null
    /** Vrai pour un GPX (trait jaune de la légende) ; un KML garde les couleurs de son fichier. */
    private var importGpx = false
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
    /** Un recentrage a demandé le lot de sa zone avant que le catalogue soit lu. */
    private var lotDeZoneEnAttente = false
    private var fenetreReglages: LinearLayout? = null
    /** La page « Cartes » du menu, refaite après chaque téléchargement ou suppression. */
    private var fenetreCartes: LinearLayout? = null
    private var dialogueCartes: AlertDialog? = null
    private var dialogueItineraires: AlertDialog? = null
    /** La page « Itinéraires » du menu, refaite après chaque téléchargement ou suppression. */
    private var fenetreItineraires: LinearLayout? = null
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
    /** Le pays du centre de la carte commande le fond national, comme la page. */
    private lateinit var pays: Pays
    private var paysAffiche = Pays.AUTRE
    private val minuteurPays = Handler(Looper.getMainLooper())
    private val verifierPays = Runnable { majPays() }
    /** Un calcul de relief plus récent remplace celui qui tourne encore. */
    private var sequenceDenivele = 0
    /**
     * Le rendu Mapsforge affiché (cartes vectorielles .map d'un PC), libéré
     * quand un autre fond prend sa place : osmdroid détache le fournisseur,
     * mais les fichiers .map resteraient ouverts.
     */
    private var sourceMapsforge: MapsForgeTileSource? = null

    /** Le geste retour d'Android 13+ : quitte le mode en cours, sinon laisse le système agir. */
    private var retourSysteme: OnBackInvokedCallback? = null

    override fun onCreate(etatSauve: Bundle?) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            val rappel = OnBackInvokedCallback {
                if (!quitterModes()) {
                    // Rien à quitter : le comportement du système, sans notre rappel.
                    onBackInvokedDispatcher.unregisterOnBackInvokedCallback(retourSysteme!!)
                    onBackPressed()
                    onBackInvokedDispatcher.registerOnBackInvokedCallback(
                        OnBackInvokedDispatcher.PRIORITY_DEFAULT, retourSysteme!!)
                }
            }
            retourSysteme = rappel
            onBackInvokedDispatcher.registerOnBackInvokedCallback(OnBackInvokedDispatcher.PRIORITY_DEFAULT, rappel)
        }
        super.onCreate(etatSauve)
        Configuration.getInstance().userAgentValue = "${Depot.AGENT} (+https://github.com/nico579/hike2gpx)"
        Configuration.getInstance().osmdroidBasePath = File(cacheDir, "osmdroid")
        Configuration.getInstance().osmdroidTileCache = File(cacheDir, "osmdroid/tiles")
        // Mapsforge dessine les cartes vectorielles (.map) reçues d'un PC ; son
        // usine graphique doit recevoir le contexte avant toute source. Sans
        // condition : Mapsforge 0.21 crée d'office AndroidGraphicFactory.INSTANCE
        // SANS contexte (bloc statique), si bien qu'un test « INSTANCE == null »
        // ne l'initialisait jamais, et chaque tuile échouait sur un contexte nul
        // (carte blanche, 0.9.17).
        MapsForgeTileSource.createInstance(application)
        reglages = Reglages(this)
        reglages.oublierPcs()                   // un PC ne se contacte qu'au scan de son QR code
        horsLigne = HorsLigne(filesDir)
        fonds = Fonds(horsLigne.racine)
        pays = Pays(assets)
        routeur = Routeur(Reglages.profils(this))
        calques = Calques(horsLigne)
        relief = Mapterhorn(filesDir)
        reliefTrace = Mapterhorn(filesDir, reseau = false)
        val premierLancement = !reglages.vueConnue
        construire()
        if (premierLancement) centrerSurIp()
        // Avant la première mise en page, la carte n'a pas encore son centre
        // (0, 0) : le pays se lit sur la vue enregistrée, sinon une carte
        // nationale serait prise pour une carte du monde et remplacée par OSM.
        val vue = reglages.vue
        paysAffiche = pays.de(vue.first, vue.second)
        // La légende a été construite avant cette lecture : sa ligne « chemin
        // officiel » attend le pays enregistré.
        majLegende()
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
            // Le zoom se fait aux doigts : pas de boutons + et −.
            zoomController.setVisibility(CustomZoomButtonsController.Visibility.NEVER)
            controller.setZoom(vue.third)
            controller.setCenter(GeoPoint(vue.first, vue.second))
            // Les calques du lot restent sous le tracé et sous les repères.
            overlays.add(0, overlayCalques)
            // Le point de la courbe se dessine juste au-dessus du tracé.
            repereProfil = RepereProfil(this@MainActivity).also { overlays.add(1, it) }
            // La position GPS, sous les repères et au-dessus des calques.
            positionOverlay = PositionOverlay(this@MainActivity).also { overlays.add(2, it) }
            // Au-dessus de la barre de boutons : l'attribution du fond doit rester lisible.
            droits = CopyrightOverlay(this@MainActivity).apply { setOffset(dp(8), dp(64)) }
            overlays.add(droits)
            echelle = ScaleBarOverlay(this).apply { setAlignBottom(true); setScaleBarOffset(dp(8), dp(84)) }
            overlays.add(echelle)
            overlays.add(MapEventsOverlay(object : MapEventsReceiver {
                override fun singleTapConfirmedHelper(p: GeoPoint): Boolean {
                    // Un tap sur la carte referme aussi le bandeau de recherche.
                    fermerRecherche()
                    overlayCalques.franchissementToucheA(this@apply, p)?.let {
                        afficherFranchissement(it)
                        return true
                    }
                    // Une trace importée touchée ouvre sa fiche, comme sa bulle sur le PC (même en planification).
                    traceImporteeToucheeA(p)?.let {
                        afficherTraceImportee(it)
                        return true
                    }
                    if (modePlan) {
                        if (lotAuPoint(horsLigne.lots(), p.latitude, p.longitude) == null)
                            Toast.makeText(this@MainActivity, R.string.plan_point_sans_zone, Toast.LENGTH_SHORT).show()
                        else ajouterPoint(Point(p.latitude, p.longitude))
                    }
                    return true
                }
                // L'appui long, comme le clic droit du PC : les coordonnées du point.
                override fun longPressHelper(p: GeoPoint): Boolean {
                    menuPoint(p); return true
                }
            }))
            // Un double tap sur la carte masque les bandeaux et laisse la carte
            // seule, un second les ramène (geste de Locus Map). Il ne pose pas
            // de point : osmdroid réserve le simple tap au-dessus.
            overlays.add(object : Overlay() {
                override fun onDoubleTap(e: MotionEvent, mapView: MapView): Boolean {
                    basculerBandeaux(); return true
                }
            })
            addMapListener(object : MapListener {
                override fun onScroll(event: ScrollEvent): Boolean {
                    planifierCalques(); planifierPays(); return false
                }

                override fun onZoom(event: ZoomEvent): Boolean {
                    majFleches(); planifierCalques(); planifierPays(); return false
                }
            })
        }
        racine.addView(carte, FrameLayout.LayoutParams(-1, -1))

        val marge = dp(8)
        // Marges posées d'emblée : avant Android 15, l'écran ne passe pas sous
        // les barres du système et le rappel des marges ci-dessous peut ne pas venir.
        bandeauHaut = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setBackgroundColor(VOILE); setPadding(marge, marge, marge, marge)
        }
        etat = TextView(this).apply { setText(R.string.etat_pret); setTextColor(0xff202020.toInt()) }
        val recherche = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
        }
        rechercheVille = recherche
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
        }.avecIcone(R.drawable.ic_btn_chercher)
        recherche.addView(boutonVille)
        bandeauHaut.addView(recherche)
        bandeauHaut.addView(etat)
        progression = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 1000; visibility = View.GONE
        }
        bandeauHaut.addView(progression)
        arreter = Button(this).apply { setText(R.string.arreter); visibility = View.GONE }.avecIcone(R.drawable.ic_btn_arreter)
        bandeauHaut.addView(arreter, LinearLayout.LayoutParams(-2, -2))
        racine.addView(bandeauHaut, FrameLayout.LayoutParams(-1, -2, Gravity.TOP))
        // La légende est une surcouche de la carte, comme sur la page du PC :
        // en haut à droite, sous le bandeau quand il est là.
        legende = construireLegende().apply {
            setBackgroundColor(VOILE); setPadding(marge, marge, marge, marge)
        }
        racine.addView(legende, FrameLayout.LayoutParams(-2, -2, Gravity.END or Gravity.TOP)
            .apply { marginEnd = marge; topMargin = marge })

        bandeauBas = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        courbe = CourbeDenivele(this).apply {
            visibility = View.GONE
            setBackgroundColor(0xf7ffffff.toInt())
            contentDescription = getString(R.string.courbe_aide)
            onPosition = ::montrerPositionProfil
        }
        enteteCourbe = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            visibility = View.GONE
            setBackgroundColor(0xf7ffffff.toInt())
            setPadding(marge, 0, marge, 0)
            minimumHeight = dp(40)                          // une cible tactile, pas un simple filet
            setOnClickListener { reglages.courbeReduite = !reglages.courbeReduite; afficherCourbe() }
        }
        enteteCourbe?.addView(TextView(this).apply {
            setText(R.string.courbe_titre); textSize = 12f
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            setTextColor(0xff305574.toInt())
        })
        resumeCourbe = TextView(this).apply {
            textSize = 12f; setTextColor(0xff305574.toInt()); gravity = Gravity.END
        }
        enteteCourbe?.addView(resumeCourbe, LinearLayout.LayoutParams(0, -2, 1f).apply { marginStart = marge })
        chevronCourbe = TextView(this).apply {
            textSize = 18f; setTextColor(0xff305574.toInt()); setPadding(marge, 0, 0, 0)
        }
        enteteCourbe?.addView(chevronCourbe)
        bandeauBas.addView(enteteCourbe, LinearLayout.LayoutParams(-1, -2))
        bandeauBas.addView(courbe, LinearLayout.LayoutParams(-1, dp(96)))
        val bas = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; setBackgroundColor(VOILE); setPadding(marge / 2, marge / 2, marge / 2, marge / 2)
        }
        for ((texte, icone, action) in listOf<Triple<Int, Int, () -> Unit>>(
            Triple(R.string.retirer, R.drawable.ic_btn_retirer, ::retirerPoint),
            Triple(R.string.effacer, R.drawable.ic_btn_supprimer, ::effacer),
            Triple(R.string.revenir, R.drawable.ic_btn_revenir, ::revenirAuDepart),
        )) {
            bas.addView(Button(this).apply {
                setText(texte); textSize = 12f; isAllCaps = false; minWidth = 0; minimumWidth = 0
                setPadding(dp(4), paddingTop, dp(4), paddingBottom)
                setOnClickListener { action() }
            }.avecIcone(icone), LinearLayout.LayoutParams(0, -2, 1f))
        }
        bandeauBas.addView(bas, LinearLayout.LayoutParams(-1, -2))
        racine.addView(bandeauBas, FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM))

        // Les deux boutons ronds de Locus Map, en bas à gauche et à
        // l'horizontale : le menu au coin, la position à côté. Le carré rouge
        // de la trace reste seul en bas à droite, à portée de pouce.
        commandesCarte = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        commandesTrace = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val cote = dp(56)
        boutonPosition = BoutonRond(this, BoutonRond.Genre.POSITION).apply {
            contentDescription = getString(R.string.bouton_position)
            setOnClickListener { centrerSurPosition() }
        }
        boutonTrace = BoutonRond(this, BoutonRond.Genre.TRACE).apply {
            // Le carré rouge arrête la trace en cours, ou termine la
            // planification quand on n'enregistre pas.
            setOnClickListener {
                when {
                    EnregistrementGps.actif -> arreterEnregistrement()
                    modePlan -> basculerPlanification()
                }
            }
        }
        boutonMenu = BoutonRond(this, BoutonRond.Genre.MENU).apply {
            contentDescription = getString(R.string.bouton_menu)
            setOnClickListener { ouvrirMenu() }
        }
        commandesTrace!!.addView(boutonTrace, LinearLayout.LayoutParams(cote, cote))
        commandesCarte!!.addView(boutonMenu, LinearLayout.LayoutParams(cote, cote).apply {
            rightMargin = dp(12)
        })
        commandesCarte!!.addView(boutonPosition, LinearLayout.LayoutParams(cote, cote))
        racine.addView(commandesTrace, FrameLayout.LayoutParams(-2, -2,
            Gravity.BOTTOM or Gravity.END).apply {
            rightMargin = dp(12)
            bottomMargin = dp(84)
        })
        racine.addView(commandesCarte, FrameLayout.LayoutParams(-2, -2,
            Gravity.BOTTOM or Gravity.START).apply {
            leftMargin = dp(12)
            bottomMargin = dp(84)
        })
        majBoutonTrace()
        bandeauBas.addOnLayoutChangeListener { _, _, _, _, _, _, _, _, _ -> placerCommandes() }
        bandeauHaut.addOnLayoutChangeListener { _, _, _, _, _, _, _, _, _ -> placerLegende() }

        // Android 15 dessine l'application sous les barres du système : les bandeaux s'en écartent.
        racine.setOnApplyWindowInsetsListener { _, insets ->
            val (dessus, dessous) = if (Build.VERSION.SDK_INT >= 30)
                insets.getInsets(WindowInsets.Type.systemBars()).let { it.top to it.bottom }
            else @Suppress("DEPRECATION") (insets.systemWindowInsetTop to insets.systemWindowInsetBottom)
            bandeauHaut.setPadding(marge, marge + dessus, marge, marge)
            bandeauBas.setPadding(0, 0, 0, dessous)
            insetHaut = dessus
            insetBas = dessous
            placerCommandes()
            placerLegende()
            insets
        }
        setContentView(racine)
        appliquerAffichage()
        if (EnregistrementGps.actif) {
            dessinerTraceEnregistree()
            majBoutonTrace()
        } else {
            recupererTraces()
        }
    }

    /**
     * Une trace que le processus n'a pas pu finir (tué par Android, batterie
     * vide) a laissé son journal : il redevient un GPX, exporté dans
     * Téléchargements comme une trace terminée normalement.
     */
    private fun recupererTraces() {
        val refaites = EnregistrementGps.recuperer(dossierTraces())
        if (refaites.isEmpty()) return
        fichierTrace = refaites.last()
        refaites.forEach { exporterTrace(it) }
        Toast.makeText(this, getString(R.string.trace_recuperee,
            refaites.joinToString(", ") { it.name }), Toast.LENGTH_LONG).show()
    }

    /**
     * La légende de la page, en haut à droite sous le bandeau : les mêmes lignes
     * que celle du PC, dans le même ordre, avec les mêmes mots et les mêmes
     * couleurs, parce que les deux viennent d'un seul fichier
     * (hike2gpx/assets/legende.json, via tools/generer_legende.py). Les lignes
     * propres au PC (GPX chargé, tracé standard) n'y sont pas : le téléphone ne
     * les dessine pas. La croix la masque, comme la coche des réglages.
     */
    private fun construireLegende(): LinearLayout {
        val boite = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(8), 0, 0)
        }
        val tete = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
        }
        tete.addView(TextView(this).apply {
            setText(R.string.legende_titre); textSize = 12f
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            setTextColor(0xff202020.toInt())
        }, LinearLayout.LayoutParams(0, -2, 1f))
        tete.addView(TextView(this).apply {
            text = "×"; textSize = 22f; gravity = Gravity.CENTER
            setTextColor(0xff404040.toInt())
            contentDescription = getString(R.string.legende_fermer)
            minWidth = dp(40); minHeight = dp(32)            // une cible tactile, pas seulement un signe
            setOnClickListener { reglages.legende = false; appliquerAffichage() }
        })
        boite.addView(tete)

        fun ligne(entree: EntreeLegende): LinearLayout {
            val rangee = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            }
            val densite = resources.displayMetrics.density
            val contour = entree.contour ?: 0xffffffff.toInt()
            // Le même trait que CalquesOverlay : plein, en tirets, ou une pastille cerclée.
            rangee.addView(object : View(this) {
                private val pinceau = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                    style = Paint.Style.STROKE
                    strokeCap = Paint.Cap.ROUND
                }

                override fun onDraw(canvas: Canvas) {
                    val y = height / 2f
                    if (entree.forme == FormeLegende.PASTILLE) {
                        pinceau.style = Paint.Style.FILL
                        pinceau.color = entree.couleur
                        canvas.drawCircle(width / 2f, y, 5 * densite, pinceau)
                        pinceau.style = Paint.Style.STROKE
                        pinceau.strokeWidth = 2 * densite
                        pinceau.color = contour
                        canvas.drawCircle(width / 2f, y, 5 * densite, pinceau)
                    } else {
                        pinceau.style = Paint.Style.STROKE
                        pinceau.strokeWidth = entree.epaisseur * densite
                        pinceau.color = entree.couleur
                        pinceau.pathEffect = if (entree.forme == FormeLegende.TIRETS)
                            DashPathEffect(floatArrayOf(4 * densite, 3 * densite), 0f) else null
                        canvas.drawLine(2 * densite, y, width - 2 * densite, y, pinceau)
                    }
                }
            }, LinearLayout.LayoutParams(dp(28), dp(16)))
            rangee.addView(TextView(this).apply {
                setText(entree.texte); textSize = 11f; setTextColor(0xff404040.toInt())
            })
            boite.addView(rangee)
            return rangee
        }
        for (entree in LegendeGeneree.ENTREES) {
            val rangee = ligne(entree)
            lignesLegende[entree.id] = rangee
            if (entree.id == "chemins_officiels") texteOfficiel = rangee.getChildAt(1) as TextView
            rangee.visibility = View.GONE           // montrée par majLegende, quand son objet est sur la carte
        }
        majLegende()
        return boite
    }

    /**
     * La fiche d'un franchissement touché, comme la bulle de la page du PC : sa
     * nature et son état, la raison du classement, et le lien vers l'objet dans OSM.
     */
    private fun afficherFranchissement(f: PointFranchissement) {
        val etat = getString(if (f.statut == "blocked") R.string.bulle_bloquant else R.string.bulle_verifier)
        val fiche = AlertDialog.Builder(this)
            .setTitle("${f.nature.ifEmpty { getString(R.string.bulle_franchissement) }} : $etat")
            .setMessage(f.raison)
            .setNegativeButton(R.string.fermer, null)
        if (f.osm.isNotEmpty()) fiche.setPositiveButton(R.string.bulle_osm) { _, _ ->
            try {
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://www.openstreetmap.org/${f.osm}")))
            } catch (e: ActivityNotFoundException) {
                // pas de navigateur : la fiche se ferme, rien d'autre à faire
            }
        }
        fiche.show()
    }

    /**
     * La légende ne montre que ce qui est sur la carte : chaque ligne suit son
     * objet (chemins OSM, chemins du lot, tracé, clôtures, franchissements,
     * chemins non raccordés), lu dans les calques affichés et le tracé. La ligne
     * des chemins officiels nomme le réseau du lot qui couvre la vue (IGN,
     * ATKIS, swissTLM3D…), ou les deux d'une case frontalière. Sans aucune
     * ligne, le panneau disparaît.
     */
    private fun majLegende() {
        if (!::overlayCalques.isInitialized) return     // appelée avant la création des calques
        val d = overlayCalques.donnees
        val reseaux = fournisseursVisibles().joinToString(" / ") { it.court }
        val presentes = buildSet {
            if (d.voies.isNotEmpty()) add("osm")
            if (d.troncons.isNotEmpty() && reseaux.isNotEmpty()) add("chemins_officiels")
            if (trace != null) add("itineraire")
            if (importGpx) add("gpx")
            if (d.barrieres.isNotEmpty()) add("barriere")
            if (d.franchissements.any { it.statut == "blocked" }) add("bloque")
            if (d.franchissements.any { it.statut != "blocked" }) add("verifier")
            if (d.jonctions.isNotEmpty()) add("jonction")
        }
        for ((id, rangee) in lignesLegende) rangee.visibility = if (id in presentes) View.VISIBLE else View.GONE
        if (reseaux.isNotEmpty()) texteOfficiel?.text = getString(R.string.legende_chemins_officiels, reseaux)
        val vide = presentes.isEmpty()
        if (vide != legendeVide) {
            legendeVide = vide
            if (legende != null) appliquerAffichage()
        }
    }

    /**
     * Chaque mode a ses commandes : la carte seule au repos, le bandeau et la
     * barre d'itinéraire en planification, l'état de la trace pendant un
     * enregistrement, le champ de recherche quand on le demande. Les coches des
     * réglages ne font que préciser ce que ces modes montrent.
     */
    private fun appliquerAffichage() {
        val enregistre = EnregistrementGps.actif
        // La recherche se referme dès qu'elle a situé son point : le bandeau ne
        // revient que pour une tâche de fond, un enregistrement ou un mode choisi.
        val replie = rechercheRepliee && !tacheAffichee && !enregistre
        val haut = (modePlan || modeRecherche || enregistre || tacheAffichee) && !replie
        bandeauHaut.visibility = if (!bandeauxMasques && haut) View.VISIBLE else View.GONE
        rechercheVille?.visibility =
            if (!enregistre && modeRecherche) View.VISIBLE else View.GONE
        etat.visibility = if (modePlan || enregistre || tacheAffichee) View.VISIBLE else View.GONE
        // La légende suit la coche des réglages ; le double tap la cache avec les bandeaux.
        legende?.visibility = if (!bandeauxMasques && reglages.legende && !legendeVide) View.VISIBLE else View.GONE
        bandeauBas.visibility = if (!bandeauxMasques && modePlan) View.VISIBLE else View.GONE
        afficherCourbe()
        placerCommandes()
        placerLegende()
    }

    /**
     * Le double tap de Locus Map : les bandeaux disparaissent et la carte reste
     * seule, un second double tap les ramène. L'échelle et l'attribution OSM
     * restent : elles font partie de la carte. Un champ de recherche qui
     * disparaît rend d'abord le clavier, sinon il resterait ouvert sur du vide.
     */
    private fun basculerBandeaux() {
        bandeauxMasques = !bandeauxMasques
        if (bandeauxMasques) cacherClavier()
        else rechercheRepliee = false
        appliquerAffichage()
    }

    /**
     * Les boutons ronds restent juste au-dessus de la barre du bas, quelle que
     * soit sa hauteur (courbe du dénivelé comprise). Bandeaux masqués, ils
     * descendent au ras de la barre du système, comme les commandes de Locus.
     */
    private fun placerCommandes() {
        // Une vue GONE garde sa dernière hauteur mesurée : sans cette garde,
        // les boutons resteraient hauts après la sortie de la planification.
        val hauteur =
            if (!bandeauxMasques && bandeauBas.visibility == View.VISIBLE)
                maxOf(bandeauBas.height, insetBas)
            else insetBas
        for (vue in listOf(commandesCarte, commandesTrace)) {
            val parametres = vue?.layoutParams as? FrameLayout.LayoutParams ?: continue
            parametres.bottomMargin = hauteur + dp(10)
            vue.layoutParams = parametres
        }
        // L'échelle et l'attribution se rangent au-dessus des boutons ronds,
        // comme sur Locus Map ; la courbe du dénivelé les remonte avec eux.
        droits?.setOffset(dp(8), hauteur + dp(84))
        echelle?.setScaleBarOffset(dp(8), hauteur + dp(104))
    }

    /**
     * La légende reste en haut à droite, sous le bandeau quand il est visible :
     * sans cela elle passerait dessous, ou sous la barre d'état quand le
     * bandeau est caché.
     */
    private fun placerLegende() {
        val vue = legende ?: return
        val parametres = vue.layoutParams as? FrameLayout.LayoutParams ?: return
        val dessus = if (!bandeauxMasques && bandeauHaut.visibility == View.VISIBLE)
            bandeauHaut.height + dp(8) else insetHaut + dp(8)
        if (parametres.topMargin == dessus) return
        parametres.topMargin = dessus
        vue.layoutParams = parametres
    }

    /**
     * La courbe n'a de sens qu'avec un profil calculé. Quand elle prend la
     * place au-dessus des boutons, l'échelle et l'attribution remontent pour
     * rester lisibles, comme les bandeaux de la page.
     */
    private fun afficherCourbe() {
        val vue = courbe ?: return
        val montre = vue.profil != null && modePlan && !bandeauxMasques
        val reduite = reglages.courbeReduite
        enteteCourbe?.visibility = if (montre) View.VISIBLE else View.GONE
        vue.visibility = if (montre && !reduite) View.VISIBLE else View.GONE
        // Repliée, l'en-tête garde les chiffres du parcours ; dépliée, la courbe les montre déjà.
        resumeCourbe?.text = vue.profil?.takeIf { reduite }
            ?.let { getString(R.string.courbe_resume, it.monteeM, it.descenteM) } ?: ""
        chevronCourbe?.text = if (reduite) "⌃" else "⌄"
        enteteCourbe?.contentDescription = getString(if (reduite) R.string.courbe_deplier else R.string.courbe_replier)
        if (!montre || reduite) cacherRepereProfil()
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
        effacerReperes()
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

    /**
     * Les doigts verts du tracé disparaissent hors planification : seule la
     * ligne GPX reste sur la carte. Ils reviennent au retour dans le mode.
     */
    private fun effacerReperes() {
        reperes.forEach { carte.overlays.remove(it) }
        reperes.clear()
        carte.invalidate()
    }

    private fun effacerTrace() {
        trace?.let { carte.overlays.remove(it) }
        trace = null
        majLegende()
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
        val exclu = exclues.filterValues { maintenant - it < REESSAI_MS }.keys + retirees + reglages.zonesRefusees
        val aFaire = lotsATelecharger(offres, horsLigne.lots(), Zone.autour(points), exclu)
        if (reglages.zonesAuto && aFaire.isNotEmpty()) {
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
            val bilan = getString(R.string.etat_itineraire,
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
        val sources = sourcesRelief(relief)
        EXECUTEUR_DENIVELE.execute {
            var profil: ProfilAltimetrique? = null
            var erreur = ""
            try {
                profil = Denivele.calculer(coordonnees, sources)
            } catch (e: Exception) {
                erreur = e.message ?: e.toString()
            }
            val calcule = profil
            runOnUiThread {
                if (sequence != sequenceDenivele || dernier !== resultat || isDestroyed) return@runOnUiThread
                // Une seule ligne : « Distance : … km   Dénivelé : +… m, −… m   Durée : … ».
                etat.text = if (calcule != null)
                    listOf(base, getString(R.string.etat_denivele, calcule.monteeM, calcule.descenteM,
                        duree(calcule.dureeMarcheS))).filter { it.isNotEmpty() }.joinToString("   ")
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
            outlinePaint.color = COULEUR_ITINERAIRE
            outlinePaint.strokeWidth = 8f
        }
        val demi = dp(FLECHE_DP) / 2
        flechesTrace = listOf(MilestoneManager(
            MilestoneMeterDistanceLister(Denivele.distancesFleches(distancesProfil.lastOrNull() ?: 0.0)),
            MilestoneBitmapDisplayer(0.0, true, iconeFleche, demi, demi),
        ))
        majFleches()
        carte.overlays.add(1 + tracesImportees.size, trace)   // sur les traces importées, sous les touches et les repères
        majLegende()
        // Jamais de recadrage : les points sont posés à l'écran, et la carte reste
        // là où on l'a mise pour poser le suivant.
        carte.invalidate()
    }

    /**
     * Comme la page : pas de flèches sous le zoom 12, où elles s'entasseraient
     * sur le tracé. Le zoom de Leaflet se compte en pixels CSS, celui d'osmdroid
     * en pixels de l'écran : sur un écran de densité 2,6, la même échelle porte
     * un zoom plus grand de log2(2,6), soit 1,4.
     */
    private fun majFleches() {
        val zoomPage = carte.zoomLevelDouble - log2(resources.displayMetrics.density.toDouble())
        trace?.setMilestoneManagers(if (zoomPage >= ZOOM_FLECHES) flechesTrace else emptyList())
    }

    /**
     * La flèche de la page (.route-direction-icon) : une pastille blanche cerclée
     * de bleu, un triangle bleu pointé vers l'est, qu'osmdroid tourne dans le sens
     * du segment.
     */
    private val iconeFleche: Bitmap by lazy {
        val densite = resources.displayMetrics.density
        val cote = dp(FLECHE_DP)
        val image = Bitmap.createBitmap(cote, cote, Bitmap.Config.ARGB_8888)
        val toile = Canvas(image)
        val pinceau = Paint(Paint.ANTI_ALIAS_FLAG)
        val r = cote / 2f
        pinceau.color = 0xffffffff.toInt()
        toile.drawCircle(r, r, r - densite / 2, pinceau)
        pinceau.color = COULEUR_ITINERAIRE
        pinceau.style = Paint.Style.STROKE
        pinceau.strokeWidth = densite
        toile.drawCircle(r, r, r - densite / 2, pinceau)
        // Le chemin SVG « M4 4 14 9 4 14 6 9Z » (boîte de 18), réduit à 11 dp au centre.
        fun x(v: Float) = (1.5f + v * 11f / 18f) * densite
        pinceau.style = Paint.Style.FILL
        toile.drawPath(android.graphics.Path().apply {
            moveTo(x(4f), x(4f)); lineTo(x(14f), x(9f)); lineTo(x(4f), x(14f)); lineTo(x(6f), x(9f)); close()
        }, pinceau)
        image
    }

    // ------------------------------------------------------------------ calques du lot

    /**
     * Une coche sous le zoom 14 ne montre rien : le dire tout de suite, sinon
     * la case semble sans effet. Au-dessus, la lecture prévient si la vue ne
     * contient aucun chemin de calque.
     */
    private fun signalerCocheCalque() {
        if (carte.zoomLevelDouble < reglages.zoomCalques) {
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
        // Seule la lecture des calques déjà prévue s'annule : vider tout le
        // planificateur emportait aussi l'effacement du bilan d'une tâche, et
        // « Lot … installé » restait affiché pour de bon dès que la carte bougeait.
        planificateur.removeCallbacks(lectureCalques)
        if ((!reglages.calqueOsm && reglages.calquesOfficiels.isEmpty()) ||
            carte.zoomLevelDouble < reglages.zoomCalques) {
            calqueCoche = false
            overlayCalques.donnees = DonneesCalques()
            majLegende()
            carte.invalidate()
            return
        }
        proposerLotZone()
        planificateur.postDelayed(lectureCalques, 350)
    }

    /** La lecture des calques, différée le temps que la carte s'arrête (planifierCalques). */
    private val lectureCalques = Runnable { rafraichirCalques() }

    /**
     * Comme la page, s'arrêter sur une région est un usage réel : le lot de la
     * case du centre se télécharge de lui-même s'il manque, ou si le catalogue
     * en a un plus récent. Un survol sous le zoom 14 ne suffit pas, mais un
     * recentrage (recherche, position GPS) le propose aussitôt, sans attendre
     * un geste sur la carte. Une case refusée ou en échec attend une heure.
     */
    private fun proposerLotZone(attendreCatalogue: Boolean = false) {
        if (!reglages.zonesAuto) return         // réglage : les zones se prennent dans « Gestion des itinéraires »
        if (enCours.get() || autoLotDemande != null) {
            // Une tâche occupe le téléchargement : la demande attend son tour.
            if (attendreCatalogue) lotDeZoneEnAttente = true
            return
        }
        if (offres.isEmpty()) {
            // Une recherche peut aboutir avant la lecture du catalogue : le lot
            // de sa zone se proposera dès qu'il sera là.
            if (attendreCatalogue) lotDeZoneEnAttente = true
            return
        }
        lotDeZoneEnAttente = false
        val boite = carte.boundingBox ?: return
        val maintenant = SystemClock.elapsedRealtime()
        val exclu = exclues.filterValues { maintenant - it < REESSAI_MS }.keys + retirees + reglages.zonesRefusees
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
        if ((!osm && officiels.isEmpty()) || carte.zoomLevelDouble < reglages.zoomCalques) {
            calqueCoche = false
            overlayCalques.donnees = DonneesCalques()
            majLegende()
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
                    majLegende()
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
     * 2026-11-04) : le serveur publie les lots, les PC ajoutent les leurs à la
     * demande, au scan de leur QR code. Un PC éteint ne retarde donc jamais le
     * lancement.
     */
    private fun actualiser() = tache(R.string.etat_catalogue, false, { _ ->
        val choix = choisir(listOf(Source.GITHUB to Depot().lireCatalogue(Source.GITHUB)))
        runOnUiThread {
            offres = choix; remplirReglages(); remplirItineraires(); planifierCalques()
            // Une recherche faite avant la lecture du catalogue n'a pas perdu sa demande.
            if (lotDeZoneEnAttente) proposerLotZone()
        }
        // Le conseil de pose ne vaut qu'en planification ; au repos, le bilan
        // se contente du catalogue lu.
        if (points.isEmpty() && modePlan) getString(R.string.etat_pret)
        else getString(R.string.etat_catalogue_lu, choix.size)
    }, ensuite = { avancer() }, discret = true)


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
        if (offre.lot.case !in reglages.zonesProposees) {
            demanderZone(offre); return
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
            Depot().telecharger(lot, offre.source, travail,
                suiviTelechargement(getString(R.string.etat_zone_routage, lot.case)), continuer)
            runOnUiThread { progression.isIndeterminate = true }
            val installe = horsLigne.installer(travail)
            travail.deleteRecursively()
            retirees.remove(installe.case)
            getString(R.string.etat_installe, installe.case)
        }, ensuite = { reussi ->
            if (!reussi) exclues[lot.case] = SystemClock.elapsedRealtime()
            remplirReglages()
            remplirItineraires()
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
                remplirItineraires()
                planifierCalques()
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    // ------------------------------------------------------------------ fonds de carte

    // ------------------------------------------------------------------ cartes

    /**
     * La page « Cartes » du menu : le fond affiché, ceux qu'un PC partage (son
     * QR code), la suppression d'un fond et les calques. Ces commandes étaient
     * noyées dans les réglages ; elles ont ici leur page, comme sur le PC.
     */
    private fun ouvrirCartes() {
        val colonne = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(8), dp(16), dp(8))
        }
        fenetreCartes = colonne
        remplirCartes()
        dialogueCartes = AlertDialog.Builder(this)
            .setTitle(R.string.menu_cartes)
            .setView(ScrollView(this).apply { addView(colonne) })
            .setPositiveButton(R.string.fermer, null)
            .setOnDismissListener { fenetreCartes = null; dialogueCartes = null }
            .show()
    }

    /** Le contenu de la page « Cartes », refait après chaque téléchargement, suppression ou ajout de PC. */
    private fun remplirCartes() {
        val colonne = fenetreCartes ?: return
        colonne.removeAllViews()

        // Deux chapitres, comme sur le PC : les cartes servies par Internet,
        // puis celles qu'un PC a fabriquées pour le hors ligne. Un seul fond
        // est choisi à la fois : cocher l'un décoche l'autre groupe.
        val enLigne = RadioGroup(this).apply { orientation = RadioGroup.VERTICAL }
        val horsLigne = RadioGroup(this).apply { orientation = RadioGroup.VERTICAL }
        fun fondChoisi(groupe: RadioGroup, cle: String, libelle: String, action: () -> Unit) {
            groupe.addView(RadioButton(this).apply {
                // Un identifiant est nécessaire pour que le groupe décoche
                // l'ancien fond quand un autre est choisi.
                id = View.generateViewId()
                text = libelle
                isChecked = reglages.fond == cle
                setOnClickListener {
                    (if (groupe === enLigne) horsLigne else enLigne).clearCheck()
                    action()
                }
            })
        }

        titre(colonne, R.string.titre_fond)
        for (carte in CartesEnLigne.disponibles(paysAffiche, reglages.cleIgn))
            fondChoisi(enLigne, carte.cle, getString(carte.libelle)) { appliquerFond(carte.cle) }
        colonne.addView(enLigne)

        // Les cartes reçues d'un PC : le chapitre n'apparaît que s'il y en a.
        // Son titre dit déjà « hors ligne », d'où le seul nom de la carte.
        val recus = fonds.parSource()
        if (recus.isNotEmpty()) {
            titre(colonne, R.string.titre_fonds)
            for (source in recus.keys)
                fondChoisi(horsLigne, Fonds.cle(source), Fonds.titre(source)) {
                    appliquerFond(Fonds.cle(source))
                    cadrerSur(recus.getValue(source))
                }
            colonne.addView(horsLigne)
        }

        // Les fonds installés, pour la liste des zones en fin de page et les
        // propositions d'un PC.
        val installes = fonds.installes()

        // Les fonds d'un PC : son QR code l'ajoute, puis ses fonds manquants se téléchargent.
        titre(colonne, R.string.cartes_a_telecharger)
        val proposes = fondsProposes(cataloguesPc ?: emptyList(), installes.map { it.nameWithoutExtension }.toSet())
        for ((source, fond) in proposes) {
            colonne.addView(Button(this).apply {
                text = getString(R.string.fond_a_telecharger, Fonds.titre(fond.source), fond.nom,
                    Formatter.formatShortFileSize(this@MainActivity, fond.octets), source.libelle)
                setOnClickListener { telechargerFond(source, fond) }
            }.avecIcone(R.drawable.ic_btn_telecharger))
        }
        colonne.addView(Button(this).apply { setText(R.string.scanner_qr); setOnClickListener { scannerQr() } }
            .avecIcone(R.drawable.ic_btn_qr))
        boutonsArchive(colonne, emptyList(), installes)

        // Les calques du lot, comme dans la page du PC : la coche OSM reste
        // toujours, celle d'un fournisseur national n'apparaît que si le lot
        // de la zone est installé (sinon il n'y a rien à dessiner).
        titre(colonne, R.string.titre_calques)
        colonne.addView(CheckBox(this).apply {
            setText(R.string.calque_osm); isChecked = reglages.calqueOsm
            setOnCheckedChangeListener { _, v ->
                reglages.calqueOsm = v
                if (v) signalerCocheCalque() else calqueCoche = false
                planifierCalques()
            }
        })
        for (fournisseur in fournisseursVisibles()) {
            colonne.addView(CheckBox(this).apply {
                text = fournisseur.court
                isChecked = reglages.calqueOfficiel(fournisseur.cle)
                setOnCheckedChangeListener { _, v ->
                    reglages.changerCalqueOfficiel(fournisseur.cle, v)
                    if (v) signalerCocheCalque() else calqueCoche = false
                    planifierCalques()
                }
            })
        }

        // Les zones de carte téléchargées, supprimables une par une. En fin de
        // page, comme sur le PC : la liste peut s'allonger sans décaler les
        // boutons du dessus.
        titre(colonne, R.string.titre_lots)
        if (installes.isEmpty()) colonne.addView(TextView(this).apply { setText(R.string.aucun_fond) })
        for (f in installes) {
            val ligne = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
            }
            ligne.addView(TextView(this).apply {
                text = getString(R.string.ligne_fond, f.nameWithoutExtension,
                    Formatter.formatShortFileSize(this@MainActivity, f.length()))
                zoneCliquable { voirFond(f) }
            }, LinearLayout.LayoutParams(0, -2, 1f))
            ligne.addView(boutonPetit(R.string.supprimer, R.drawable.ic_btn_supprimer, rouge = true) { confirmerSuppressionFond(f) })
            colonne.addView(ligne)
        }
    }

    /** Une zone stockée se touche pour la voir sur la carte : soulignée, comme un lien. */
    private fun TextView.zoneCliquable(action: () -> Unit) {
        paintFlags = paintFlags or Paint.UNDERLINE_TEXT_FLAG
        minHeight = dp(48)
        gravity = Gravity.CENTER_VERTICAL
        setOnClickListener { action() }
    }

    private fun refermerPages() {
        dialogueCartes?.dismiss()
        dialogueItineraires?.dismiss()
    }

    /** Le lot touché : la page se referme et la carte cadre sa zone (comme sur le PC). */
    private fun voirLot(lot: Lot) {
        val zone = lot.couverture ?: return             // [sud, ouest, nord, est]
        refermerPages()
        carte.zoomToBoundingBox(BoundingBox(zone[2], zone[3], zone[0], zone[1]), false, dp(24))
    }

    /**
     * La carte touchée : elle devient le fond affiché, et la vue se pose sur
     * son carré, à un zoom où elle a des tuiles (en deçà de son minzoom, elle
     * resterait vide).
     */
    private fun voirFond(f: File) {
        val bornes = metadonnees(f)["bounds"]?.split(',')?.mapNotNull { it.trim().toDoubleOrNull() }
            ?.takeIf { it.size == 4 }
        refermerPages()
        appliquerFond(Fonds.source(f.nameWithoutExtension))
        if (bornes == null) return
        carte.controller.setZoom(maxOf(carte.zoomLevelDouble.coerceAtMost(15.0), zoomMin(listOf(f)).toDouble()))
        carte.controller.setCenter(GeoPoint((bornes[1] + bornes[3]) / 2, (bornes[0] + bornes[2]) / 2))
    }

    /** Un fond effacé après confirmation ; s'il était affiché et que sa source disparaît, la carte revient en ligne. */
    private fun confirmerSuppressionFond(f: File) {
        AlertDialog.Builder(this)
            .setTitle(R.string.cartes_supprimer_titre)
            .setMessage(getString(R.string.cartes_supprimer_message, f.nameWithoutExtension))
            .setPositiveButton(R.string.supprimer) { _, _ ->
                val source = Fonds.source(f.nameWithoutExtension)
                f.delete()
                if (reglages.fond == Fonds.cle(source) && fonds.parSource()[source] == null)
                    appliquerFond(CartesEnLigne.defaut(paysAffiche))
                remplirCartes()
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun telechargerFond(source: Source, fond: Fond) {
        AlertDialog.Builder(this)
            .setTitle(fond.nom)
            .setMessage(getString(R.string.confirmer_telechargement,
                Formatter.formatShortFileSize(this, fond.octets), source.libelle))
            .setPositiveButton(R.string.telecharger) { _, _ -> installerFond(source, fond) }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    /** Le fond téléchargé et installé, déjà confirmé (un bouton, ou la récupération d'un PC). */
    private fun installerFond(source: Source, fond: Fond) {
        tache(R.string.etat_telechargement, true, { continuer ->
            val travail = File(filesDir, "telechargements")
            val recu = Depot().telechargerFond(fond, source, travail,
                suiviTelechargement(getString(R.string.etat_zone_carte, fond.nom)), continuer)
            fonds.installer(recu, fond)
            getString(R.string.etat_fond_installe, fond.nom)
        }, ensuite = { reussi ->
            if (reussi) {
                appliquerFond(Fonds.cle(Fonds.source(fond.nom)))
                remplirCartes()
            }
        })
    }

    // ------------------------------------------------------------------ archive zip

    /**
     * Les deux boutons d'archive d'une page (Archive.kt) : exporter ce qu'elle
     * liste vers un fichier choisi (clé USB, Drive, Téléchargements), et
     * importer une archive, d'un PC ou d'un téléphone. Une case longue à
     * préparer (une heure pour un SCAN 25) s'y sauvegarde aussi.
     */
    private fun boutonsArchive(colonne: LinearLayout, lots: List<Lot>, cartes: List<File>) {
        if (lots.isNotEmpty() || cartes.isNotEmpty())
            colonne.addView(Button(this).apply {
                setText(R.string.archive_exporter); setOnClickListener { choisirExport(lots, cartes) }
            }.avecIcone(R.drawable.ic_btn_telecharger))
        colonne.addView(Button(this).apply {
            setText(R.string.archive_importer)
            setOnClickListener {
                startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    // Un Drive livre souvent un zip en application/octet-stream.
                    type = "*/*"
                    putExtra(Intent.EXTRA_MIME_TYPES, arrayOf("application/zip", "application/octet-stream"))
                }, IMPORT_ARCHIVE)
            }
        }.avecIcone(R.drawable.ic_btn_actualiser))
    }

    /** Les zones ou les cartes à mettre dans l'archive, toutes cochées d'abord, puis le fichier où l'écrire. */
    private fun choisirExport(lots: List<Lot>, cartes: List<File>) {
        val noms = lots.map { it.case } + cartes.map { it.nameWithoutExtension }
        val coches = BooleanArray(noms.size) { true }
        AlertDialog.Builder(this)
            .setTitle(if (lots.isNotEmpty()) R.string.archive_choix_zones else R.string.archive_choix_cartes)
            .setMultiChoiceItems(noms.toTypedArray(), coches) { _, i, v -> coches[i] = v }
            .setPositiveButton(R.string.archive_exporter) { _, _ ->
                val lotsChoisis = lots.filterIndexed { i, _ -> coches[i] }
                val cartesChoisies = cartes.filterIndexed { i, _ -> coches[lots.size + i] }
                if (lotsChoisis.isEmpty() && cartesChoisies.isEmpty()) {
                    etat.setText(R.string.archive_rien); return@setPositiveButton
                }
                archiveAEcrire = lotsChoisis to cartesChoisies
                startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = "application/zip"
                    putExtra(Intent.EXTRA_TITLE, Archive.nomPropose(
                        lotsChoisis.map { it.case } + cartesChoisies.map { it.nameWithoutExtension }))
                }, EXPORT_ARCHIVE)
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun ecrireArchive(adresse: Uri, lots: List<Lot>, cartes: List<File>) {
        val nom = nomAffiche(adresse)
        tache(R.string.etat_archive_ecriture, true, { continuer ->
            val sortie = contentResolver.openOutputStream(adresse) ?: throw IOException(nom)
            sortie.use { Archive.ecrire(it, lots, horsLigne, cartes, suiviTelechargement(nom), continuer) }
            getString(R.string.etat_archive_ecrite, nom)
        })
    }

    private fun lireArchive(adresse: Uri) {
        val nom = nomAffiche(adresse)
        tache(R.string.etat_archive_lecture, true, { continuer ->
            routeur.annuler()
            val entree = contentResolver.openInputStream(adresse) ?: throw IOException(nom)
            val r = entree.use {
                Archive.importer(it, horsLigne, fonds, File(filesDir, "archive"), suiviTelechargement(nom), continuer)
            }
            retirees.removeAll(r.lots.toSet())
            getString(R.string.etat_archive_importee, r.fonds.size, r.lots.size)
        }, ensuite = {
            remplirCartes()
            remplirItineraires()
            planifierCalques()
        })
    }

    // ------------------------------------------------------------------ itinéraires

    /**
     * La page « Itinéraires » du menu : le mode strict et les chemins
     * officiels, les lots de routage installés ou calculés sur un PC, et
     * l'enregistrement de trace GPS. Ces commandes quittent les réglages.
     */
    private fun ouvrirItineraires() {
        val colonne = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(8), dp(16), dp(8))
        }
        fenetreItineraires = colonne
        remplirItineraires()
        dialogueItineraires = AlertDialog.Builder(this)
            .setTitle(R.string.menu_itineraires)
            .setView(ScrollView(this).apply { addView(colonne) })
            .setPositiveButton(R.string.fermer, null)
            .setOnDismissListener { fenetreItineraires = null; dialogueItineraires = null }
            .show()
    }

    /** Le contenu de la page « Itinéraires », refait après chaque téléchargement ou suppression. */
    private fun remplirItineraires() {
        val colonne = fenetreItineraires ?: return
        colonne.removeAllViews()

        titre(colonne, R.string.itineraires_modes)
        colonne.addView(Switch(this).apply {
            setText(R.string.strict); isChecked = reglages.strict
            setOnCheckedChangeListener { _, v -> reglages.strict = v }
        })
        // Le nom vient des lots : « Inclure les chemins IGN », « ATKIS »…
        val fournisseurs = fournisseursDisponibles().ifEmpty {
            offres.flatMap { Fournisseurs.duLot(it.lot) }.distinctBy { it.cle }.sortedBy { it.nom }
        }
        colonne.addView(Switch(this).apply {
            text = if (fournisseurs.isEmpty()) getString(R.string.officiels_aucun)
            else getString(R.string.officiels, fournisseurs.joinToString(", ") { it.court })
            isChecked = reglages.officiels
            setOnCheckedChangeListener { _, v -> reglages.officiels = v }
        })

        // Les lots installés, pour la liste des zones en fin de page et pour
        // savoir ce qu'un PC apporte en plus.
        val installes = horsLigne.lots()

        // Ce que seul un PC calcule : ses lots absents du serveur et du téléphone.
        titre(colonne, R.string.itineraires_pc)
        val duPc = lotsDuPc(installes)
        for ((source, lot) in duPc) {
            colonne.addView(Button(this).apply {
                text = getString(R.string.itineraires_lot, lot.case, description(lot),
                    Formatter.formatShortFileSize(this@MainActivity, lot.octets), source.libelle)
                setOnClickListener { telecharger(Offre(source, lot)) }
            }.avecIcone(R.drawable.ic_btn_telecharger))
        }
        colonne.addView(Button(this).apply { setText(R.string.scanner_qr); setOnClickListener { scannerQr() } }
            .avecIcone(R.drawable.ic_btn_qr))
        boutonsArchive(colonne, installes, emptyList())

        // L'enregistrement de trace de Locus Map, appliqué au prochain point
        // même quand un enregistrement est en cours.
        titre(colonne, R.string.titre_trace)
        champNombre(colonne, R.string.trace_distance, reglages.distanceMin, entier = false) {
            reglages.distanceMin = it
            appliquerReglagesTrace()
        }
        champNombre(colonne, R.string.trace_duree, reglages.dureeMin.toDouble(), entier = true) {
            reglages.dureeMin = it.roundToInt()
            appliquerReglagesTrace()
        }
        champNombre(colonne, R.string.trace_precision, reglages.precisionMax, entier = false) {
            reglages.precisionMax = it
            appliquerReglagesTrace()
        }

        // Les zones de routage installées, supprimables une par une. En fin de
        // page, comme sur le PC : la liste peut s'allonger sans décaler les
        // réglages du dessus.
        titre(colonne, R.string.titre_lots)
        if (installes.isEmpty()) colonne.addView(TextView(this).apply { setText(R.string.aucun_lot) })
        for (lot in installes) {
            val offre = offres.firstOrNull { it.lot.case == lot.case }
            val ligne = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
            }
            ligne.addView(TextView(this).apply {
                text = getString(R.string.ligne_installe, lot.case, description(lot),
                    Formatter.formatShortFileSize(this@MainActivity, lot.octets))
                zoneCliquable { voirLot(lot) }
            }, LinearLayout.LayoutParams(0, -2, 1f))
            if (offre != null && plusRecent(offre.lot, lot))
                ligne.addView(boutonPetit(R.string.mettre_a_jour, R.drawable.ic_btn_actualiser) { telecharger(offre) })
            ligne.addView(boutonPetit(R.string.supprimer, R.drawable.ic_btn_supprimer, rouge = true) { supprimerLot(lot) })
            colonne.addView(ligne)
        }
    }

    /**
     * Les lots qu'un PC propose et qui manquent au téléphone, sans ceux que le
     * serveur publie déjà (il les fait venir de lui-même) : ce que seul un PC
     * calcule. Un lot est pris au premier PC qui le sert.
     */
    private fun lotsDuPc(installes: List<Lot>): List<Pair<Source, Lot>> {
        val presents = installes.map { it.case }.toSet()
        val github = offres.map { it.lot.case }.toSet()
        val vus = LinkedHashMap<String, Pair<Source, Lot>>()
        for ((source, catalogue) in cataloguesPc ?: emptyList())
            for (lot in catalogue.lots)
                if (lot.case !in presents && lot.case !in github && lot.case !in vus)
                    vus[lot.case] = source to lot
        return vus.values.sortedBy { it.second.case }
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
        // Une carte vectorielle connaît ses bornes par son moteur Mapsforge ;
        // un MBTiles les donne dans sa table metadata.
        val vectorielles = fichiers.filter { it.extension.equals("map", true) }
        val source = sourceMapsforge?.takeIf { vectorielles.isNotEmpty() && vectorielles.size == fichiers.size }
        val boites = if (source != null) listOf(source.boundsOsmdroid) else fichiers.mapNotNull { f ->
            metadonnees(f)["bounds"]?.split(',')?.mapNotNull { it.trim().toDoubleOrNull() }?.takeIf { it.size == 4 }
                ?.let { (o, s, e, n) -> BoundingBox(n, e, s, o) }
        }
        if (boites.isEmpty() || boites.any { it.contains(carte.mapCenter) }) return
        val minimum = source?.minimumZoomLevel?.toDouble() ?: zoomMin(fichiers).toDouble()
        carte.controller.setZoom(maxOf(carte.zoomLevelDouble, minimum))
        carte.controller.setCenter(boites.first().centerWithDateLine)
    }

    /**
     * Remplace le fournisseur de tuiles, puis libère le rendu Mapsforge
     * précédent : osmdroid détache l'ancien fournisseur, mais les .map
     * resteraient ouverts. [source] est le rendu du nouveau fournisseur, ou
     * null pour une carte en ligne ou un MBTiles.
     */
    private fun poserFournisseur(fournisseur: MapTileProviderBase, source: MapsForgeTileSource? = null) {
        val ancienne = sourceMapsforge
        sourceMapsforge = source
        carte.setTileProvider(fournisseur)
        ancienne?.dispose()
    }

    /**
     * Le fond de la carte. Un fond hors ligne réunit tous les fichiers de sa
     * source, MBTiles d'images ou cartes vectorielles .map (Mapsforge) ; la
     * carte ne demande rien au réseau. Un MBTiles agrandit au-delà de son zoom
     * le plus fin, comme la page (maxNativeZoom), et la carte ne descend pas
     * sous son zoom le plus bas, où elle n'aurait rien à montrer.
     *
     * Une carte nationale ne sert que dans son pays : si le centre de la carte
     * en est sorti, celle du pays affiché prend sa place, ou OpenStreetMap s'il
     * n'y en a pas. Un fond du monde ou hors ligne reste tel quel.
     */
    private fun appliquerFond(cle: String) {
        // Un fond reçu d'un PC porte la clé « pc:<source> » : même si une carte
        // en ligne a le même nom (SCAN 25, OpenStreetMap), les deux restent
        // distinctes et une seule est cochée. Ses fichiers disparus, le pays reprend.
        val sourcePc = Fonds.sourceDeCle(cle)
        if (sourcePc != null) {
            val fichiers = fonds.parSource()[sourcePc]
            if (fichiers == null) {
                appliquerFond(CartesEnLigne.defaut(paysAffiche))
                return
            }
            // Les .map d'un PC se dessinent avec Mapsforge, les .mbtiles avec
            // le lecteur hors ligne d'osmdroid. Une source mélangée prend ses
            // images, seules lisibles par le lecteur commun.
            val vectorielles = fichiers.filter { it.extension.equals("map", true) }
            val images = fichiers.filter { it.extension.equals("mbtiles", true) }
            when {
                images.isEmpty() && vectorielles.isNotEmpty() -> {
                    // Le cache des tuiles rendues porte le nom de la source :
                    // l'empreinte des fichiers y entre, pour qu'une carte mise à
                    // jour ne réaffiche pas les tuiles de l'ancienne.
                    val empreinte = vectorielles.joinToString("|") { "${it.name}:${it.length()}:${it.lastModified()}" }
                    // Le thème par défaut de Mapsforge, dessiné à l'échelle des tuiles
                    // en ligne (ECHELLE_RENDU) : Mapsforge multiplie par défaut traits
                    // et textes par la densité de l'écran, et osmdroid, qui affiche
                    // les tuiles pixel pour pixel, les rendait énormes. Le « v2 » du
                    // nom écarte les tuiles de l'ancien rendu restées en cache.
                    val source = try {
                        MapsForgeTileSource.createFromFiles(vectorielles.toTypedArray(),
                            InternalRenderTheme.DEFAULT,
                            "mapsforge-v2-$sourcePc-${Integer.toHexString(empreinte.hashCode())}")
                            .also { it.setUserScaleFactor(ECHELLE_RENDU / resources.displayMetrics.density) }
                    } catch (e: Exception) {
                        // Fichier illisible ou format Mapsforge inconnu : mieux
                        // vaut une carte en ligne qu'un écran vide.
                        appliquerFond(CartesEnLigne.defaut(paysAffiche))
                        return
                    }
                    poserFournisseur(MapsForgeTileProvider(SimpleRegisterReceiver(this), source, null), source)
                    val minimum = source.minimumZoomLevel.toDouble()
                    carte.setMinZoomLevel(minimum)
                    if (carte.zoomLevelDouble < minimum) carte.controller.setZoom(minimum)
                }
                images.isNotEmpty() -> {
                    val minimum = zoomMin(images)
                    poserFournisseur(OfflineTileProvider(SimpleRegisterReceiver(this), images.toTypedArray()))
                    carte.setTileSource(XYTileSource("hors-ligne-$sourcePc", minimum, 19, 256, "", arrayOf<String>(),
                        "© ${Fonds.titre(sourcePc)}"))
                    carte.setMinZoomLevel(minimum.toDouble())
                    if (carte.zoomLevelDouble < minimum) carte.controller.setZoom(minimum.toDouble())
                }
                else -> {                       // fichiers illisibles : la carte revient en ligne
                    appliquerFond(CartesEnLigne.defaut(paysAffiche))
                    return
                }
            }
            reglages.fond = cle
            carte.invalidate()
            return
        }
        val national = CartesEnLigne.parCle(cle)?.pays != null
        val choix = if (national && !CartesEnLigne.disponible(cle, paysAffiche, reglages.cleIgn))
            CartesEnLigne.defaut(paysAffiche) else cle
        val enLigne = CartesEnLigne.parCle(choix)
        val servi = CartesEnLigne.disponible(choix, paysAffiche, reglages.cleIgn)
        when {
            servi && enLigne != null -> {
                poserFournisseur(MapTileProviderBasic(applicationContext))
                carte.setTileSource(CartesEnLigne.tuile(enLigne, reglages.cleIgn))
                carte.setMinZoomLevel(null)         // le zoom le plus bas de la source en ligne
            }
            else -> {
                poserFournisseur(MapTileProviderBasic(applicationContext))
                carte.setTileSource(TileSourceFactory.MAPNIK)
                carte.setMinZoomLevel(null)
            }
        }
        reglages.fond = if (servi && enLigne != null) choix else "osm"
        carte.invalidate()
    }

    /** Le pays se lit après un temps de repos, comme la page (600 ms). */
    private fun planifierPays() {
        minuteurPays.removeCallbacks(verifierPays)
        minuteurPays.postDelayed(verifierPays, 600)
    }

    /**
     * Une carte nationale suit le pays du centre : en Suisse, swisstopo prend la
     * place du Plan IGN ; hors des pays couverts, OpenStreetMap. Un fond du
     * monde (OSM, OpenTopoMap, satellite) et un fond hors ligne restent.
     */
    private fun majPays() {
        val nouveau = pays.de(carte.mapCenter.latitude, carte.mapCenter.longitude)
        if (nouveau == paysAffiche) return
        paysAffiche = nouveau
        majLegende()
        if (Fonds.sourceDeCle(reglages.fond) == null &&
            CartesEnLigne.parCle(reglages.fond)?.pays != null)
            appliquerFond(CartesEnLigne.defaut(nouveau))
        if (fenetreCartes != null) remplirCartes()
    }

    // ------------------------------------------------------------------ menu

    /**
     * Le panneau du menu, comme celui de Locus Map : il monte du bas et laisse
     * la carte visible derrière. Chaque entrée ouvre un mode ou une fenêtre ;
     * la carte seule reste l'écran par défaut.
     */
    private fun ouvrirMenu() {
        val colonne = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(10), dp(20), dp(20))
            background = GradientDrawable().apply {
                // Le panneau laisse voir la carte derrière, comme une feuille
                // posée sur l'écran.
                setColor(0xccfafafa.toInt())
                cornerRadii = floatArrayOf(
                    dp(20).toFloat(), dp(20).toFloat(),
                    dp(20).toFloat(), dp(20).toFloat(),
                    0f, 0f, 0f, 0f)
            }
        }
        // La poignée du haut : on la glisse vers le bas pour refermer le panneau.
        val poignee = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            isClickable = true
        }
        poignee.addView(View(this).apply { setBackgroundColor(0xffcfd8dc.toInt()) },
            LinearLayout.LayoutParams(dp(40), dp(4)).apply {
                topMargin = dp(10)
                bottomMargin = dp(10)
            })
        colonne.addView(poignee, LinearLayout.LayoutParams(-1, dp(24)))
        colonne.addView(TextView(this).apply {
            setText(R.string.menu_titre)
            textSize = 18f
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            setTextColor(0xff263238.toInt())
            setPadding(0, 0, 0, dp(4))
        })

        val enregistre = EnregistrementGps.actif
        val entrees = listOf(
            Triple(R.drawable.ic_recherche, R.string.menu_recherche, ::ouvrirRecherche),
            Triple(R.drawable.ic_carte, R.string.menu_cartes, ::ouvrirCartes),
            Triple(R.drawable.ic_itineraires, R.string.menu_itineraires, ::ouvrirItineraires),
            Triple(R.drawable.ic_importer,
                if (nomImport == null) R.string.menu_importer else R.string.menu_retirer_import,
                ::basculerImport),
            Triple(R.drawable.ic_enregistrer,
                if (enregistre) R.string.menu_arreter else R.string.menu_enregistrer,
                ::basculerEnregistrement),
            Triple(R.drawable.ic_planifier,
                if (modePlan) R.string.menu_terminer_plan else R.string.menu_planifier,
                ::basculerPlanification),
            Triple(R.drawable.ic_reglages, R.string.reglages, ::ouvrirReglages),
            Triple(R.drawable.ic_aide, R.string.menu_aide, ::ouvrirAide),
        )
        val dialogue = Dialog(this)
        for ((icone, texte, action) in entrees) {
            val ligne = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                isClickable = true
                isFocusable = true
                setPadding(dp(4), dp(14), dp(4), dp(14))
                setBackgroundResource(android.R.drawable.list_selector_background)
            }
            ligne.addView(ImageView(this).apply {
                setImageResource(icone)
                scaleType = ImageView.ScaleType.FIT_CENTER
            }, LinearLayout.LayoutParams(dp(28), dp(28)))
            ligne.addView(TextView(this).apply {
                setText(texte)
                textSize = 16f
                setTextColor(0xff263238.toInt())
                setPadding(dp(18), 0, 0, 0)
            }, LinearLayout.LayoutParams(0, -2, 1f))
            // Sans zone de routage au centre, la planification ne peut rien calculer : grisée.
            if (texte == R.string.menu_planifier && !zoneAuCentre()) ligne.alpha = 0.4f
            ligne.setOnClickListener {
                dialogue.dismiss()
                action()
            }
            colonne.addView(ligne)
        }

        dialogue.setContentView(colonne)
        dialogue.show()
        dialogue.window?.apply {
            setBackgroundDrawable(ColorDrawable(0x00000000))
            setLayout(WindowManager.LayoutParams.MATCH_PARENT, WindowManager.LayoutParams.WRAP_CONTENT)
            setGravity(Gravity.BOTTOM)
            addFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND)
            setDimAmount(0.35f)
        }

        // Glisser la poignée vers le bas referme le panneau ; un petit
        // mouvement le laisse revenir en place.
        val seuil = dp(96).toFloat()
        var depart = 0f
        var glisse = 0f
        poignee.setOnTouchListener { _, evenement ->
            when (evenement.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    depart = evenement.rawY
                    glisse = 0f
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    glisse = (evenement.rawY - depart).coerceAtLeast(0f)
                    dialogue.window?.decorView?.translationY = glisse
                    true
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    if (glisse > seuil)
                        dialogue.dismiss()
                    else
                        dialogue.window?.decorView?.animate()
                            ?.translationY(0f)?.setDuration(150)?.start()
                    true
                }
                else -> false
            }
        }
    }

    /** Le mode d'emploi de l'application : le README Android, sur GitHub. */
    /**
     * L'aide est le mode d'emploi général, comme sur le PC : le README de la
     * version installée (son tag ; celui de main peut avoir pris de l'avance),
     * dans la langue du téléphone. Il renvoie au README propre à Android.
     */
    private fun ouvrirAide() {
        val fichier = if (Locale.getDefault().language == "fr") "README.fr.md" else "README.md"
        startActivity(Intent(Intent.ACTION_VIEW,
            Uri.parse("https://github.com/nico579/hike2gpx/blob/v${versionInstallee()}/$fichier")))
    }

    /** Le champ de recherche ne s'affiche qu'à la demande, depuis le menu. */
    private fun ouvrirRecherche() {
        // Pendant une trace, le bandeau ne montre que l'état de l'enregistrement.
        if (EnregistrementGps.actif) {
            Toast.makeText(this, R.string.plan_trace_en_cours, Toast.LENGTH_LONG).show()
            return
        }
        modeRecherche = true
        rechercheRepliee = false
        appliquerAffichage()
        val champ = champVille ?: return
        champ.requestFocus()
        // La fenêtre reprend le focus après la fermeture du panneau : on laisse
        // un instant au système avant de demander le clavier.
        champ.postDelayed({
            if (isDestroyed) return@postDelayed
            (getSystemService(INPUT_METHOD_SERVICE) as? InputMethodManager)
                ?.showSoftInput(champ, InputMethodManager.SHOW_IMPLICIT)
        }, 250)
    }

    /**
     * Referme la recherche et son bandeau : dès qu'une ville est située sur la
     * carte, ou qu'on touche la carte, il n'a plus de raison d'occuper l'écran.
     */
    private fun fermerRecherche() {
        if (!modeRecherche) return
        modeRecherche = false
        rechercheRepliee = true
        cacherClavier()
        appliquerAffichage()
    }

    /**
     * La planification est un mode : ses boutons et son état n'apparaissent
     * qu'une fois choisi dans le menu. Un parcours enregistré reste affiché
     * quand on en sort, et les points déjà posés sont repris au retour.
     */
    private fun basculerPlanification() {
        if (!modePlan && EnregistrementGps.actif) {
            Toast.makeText(this, R.string.plan_trace_en_cours, Toast.LENGTH_LONG).show()
            return
        }
        if (!modePlan && !zoneAuCentre()) {
            expliquerSansZone(); return
        }
        modePlan = !modePlan
        modeRecherche = false
        rechercheRepliee = false
        majBoutonTrace()
        if (modePlan) {
            dessinerPoints()
            when {
                points.isEmpty() -> etat.setText(R.string.etat_pret)
                points.size == 1 -> etat.setText(R.string.etat_depart_pose)
                bilanItineraire.isNotEmpty() -> etat.text = bilanItineraire
            }
        } else {
            cacherClavier()
            effacerReperes()
            if (dernier != null) proposerGpx()
            renduALaCarte()
        }
        appliquerAffichage()
    }

    /**
     * En quittant la planification, le bilan qui s'attardait quelques secondes
     * (« Touchez la carte… », la distance) disparaît aussitôt : la carte est
     * seule. Une tâche qui tourne vraiment (un téléchargement) garde son bandeau.
     */
    private fun renduALaCarte() {
        if (!enCours.get()) tacheAffichee = false
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

    /** Le contenu des réglages, refait après chaque changement du cache ou des lots. */
    private fun remplirReglages() {
        val colonne = fenetreReglages ?: return
        colonne.removeAllViews()
        titre(colonne, R.string.titre_affichage)
        colonne.addView(CheckBox(this).apply {
            setText(R.string.afficher_legende); isChecked = reglages.legende
            setOnCheckedChangeListener { _, v -> reglages.legende = v; appliquerAffichage() }
        })
        colonne.addView(CheckBox(this).apply {
            setText(R.string.reglage_zones_auto); isChecked = reglages.zonesAuto
            setOnCheckedChangeListener { _, v -> reglages.zonesAuto = v }
        })
        // Les calques ne se dessinent qu'à partir de ce zoom : plus haut, le
        // téléphone a moins à tracer.
        champNombre(colonne, R.string.reglages_zoom_calques, reglages.zoomCalques.toDouble(), entier = true) {
            reglages.zoomCalques = it.roundToInt()
            planifierCalques()
        }

        // La clé IGN du SCAN 25, le même réglage que sur le PC.
        titreAvecInfo(colonne, R.string.reglages_cle_ign, R.string.reglages_cle_note)
        val cleIgn = EditText(this).apply {
            setSingleLine()             // avant la transformation : sinon elle serait remplacée
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            transformationMethod = PasswordTransformationMethod.getInstance()
            setText(reglages.cleIgn)
            addTextChangedListener(object : TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
                override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
                override fun afterTextChanged(s: Editable?) {
                    val valeur = s?.toString()?.trim() ?: ""
                    if (!CLE_IGN.matches(valeur) || valeur == reglages.cleIgn) return
                    reglages.cleIgn = valeur
                    if (fenetreCartes != null) remplirCartes()
                    // Sans clé, le SCAN 25 ne sert plus : la carte du pays prend sa place.
                    if (valeur.isEmpty()) appliquerFond(reglages.fond)
                }
            })
        }
        colonne.addView(cleIgn)
        colonne.addView(CheckBox(this).apply {
            setText(R.string.reglages_cle_afficher)
            setOnCheckedChangeListener { _, v ->
                cleIgn.inputType = InputType.TYPE_CLASS_TEXT or
                    (if (v) InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD else InputType.TYPE_TEXT_VARIATION_PASSWORD)
                cleIgn.transformationMethod =
                    if (v) null else PasswordTransformationMethod.getInstance()
                cleIgn.setSelection(cleIgn.text.length)
            }
        })

        // Les réglages de trace et les lots ont leur page « Itinéraires ».
        titre(colonne, R.string.titre_cache)
        colonne.addView(Button(this).apply {
            text = getString(R.string.vider_cache, Formatter.formatShortFileSize(this@MainActivity, octetsCaches()))
            setOnClickListener { viderCache() }
        }.avecIcone(R.drawable.ic_btn_supprimer))

        titre(colonne, R.string.maj_titre)
        colonne.addView(TextView(this).apply { text = getString(R.string.maj_version, versionInstallee()) })
        colonne.addView(Button(this).apply { setText(R.string.maj_verifier); setOnClickListener { verifierMaj() } }
            .avecIcone(R.drawable.ic_btn_actualiser))
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
        // Le point est situé : le bandeau de recherche se referme aussitôt.
        fermerRecherche()
        // Le pays et le lot de la nouvelle zone n'attendent pas un geste sur la
        // carte : la recherche a amené l'utilisateur ici, le lot y part.
        planifierPays()
        planifierCalques()
        proposerLotZone(attendreCatalogue = true)
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
        // Un Toast, pas le bandeau d'état : au repos, il est caché derrière les réglages.
        Toast.makeText(this, R.string.maj_verification, Toast.LENGTH_SHORT).show()
        Thread {
            val message = try {
                val publication = ClientMaj().verifier(versionInstallee())
                if (publication != null) {
                    runOnUiThread { proposerMaj(publication) }; null
                } else getString(R.string.maj_a_jour, versionInstallee())
            } catch (e: Exception) {
                texte(e)
            }
            if (message != null) runOnUiThread {
                if (!isDestroyed) Toast.makeText(this, message, Toast.LENGTH_LONG).show()
            }
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
            val apk = ClientMaj().telecharger(publication, MiseAJour.dossier(this), suiviTelechargement(null), continuer)
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
                appliquerFond(reglages.fond)     // un fournisseur neuf, sur un cache neuf
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

    /** Ceux du lot qui couvre la vue, dans le pays affiché : les seules coches de superposition. */
    private fun fournisseursVisibles(): List<Fournisseur> {
        val boite = carte.boundingBox
        return calques.fournisseursVisibles(
            Zone(boite.latSouth, boite.lonWest, boite.latNorth, boite.lonEast), paysAffiche)
    }

    private fun description(lot: Lot): String =
        if (lot.osm) "OSM" else getString(R.string.lot_enrichi,
            Fournisseurs.duLot(lot).joinToString("+") { it.nom }
                .ifEmpty { lot.fournisseurs.joinToString("+") })

    // ------------------------------------------------------------------ PC

    /**
     * Ce qu'on ouvre avec hike2gpx : le lien hike2gpx://depot du QR code d'un
     * PC (lu par l'appareil photo), ou un GPX / KML ouvert depuis un
     * gestionnaire de fichiers, une pièce jointe, un téléchargement, ou
     * partagé vers hike2gpx. Le fichier suit le chemin de « Importer un GPX ou
     * un KML » du menu.
     */
    private fun lireLien(intent: Intent?) {
        intent ?: return
        val fichier = when (intent.action) {
            Intent.ACTION_VIEW -> intent.data?.takeIf { it.scheme == "content" || it.scheme == "file" }
            Intent.ACTION_SEND -> if (Build.VERSION.SDK_INT >= 33) intent.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java)
                else @Suppress("DEPRECATION") (intent.getParcelableExtra(Intent.EXTRA_STREAM) as? Uri)
            else -> null
        }
        if (fichier != null) {
            importer(fichier)
            return
        }
        val lien = intent.data?.toString() ?: return
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

    /**
     * Le QR code d'un PC lu : son catalogue dit ce qu'il partage, c'est-à-dire
     * ce qu'on a sélectionné sur sa carte. Une seule confirmation nomme le PC
     * et ce qui va venir ; elle ajoute le PC et récupère tout à la suite.
     * Toujours confirmé : une page web pourrait ouvrir un tel lien à l'insu de
     * l'utilisateur, et rien ne s'ajoute ni ne se télécharge sans ce « oui ».
     */
    private fun ajouterPc(source: Source) = tache(R.string.etat_pc, false, { _ ->
        val catalogue = Depot().lireCatalogue(source)
        runOnUiThread { proposerRecuperation(source, catalogue) }
        getString(R.string.etat_pc_lus, catalogue.fonds.size + catalogue.cartes.size, catalogue.lots.size)
    })

    private fun proposerRecuperation(source: Source, catalogue: Catalogue) {
        // Ce qui manque au téléphone : une zone absente ou plus ancienne, un fond absent.
        val presents = horsLigne.lots().associateBy { it.case }
        val lots = catalogue.lots.filter { lot -> presents[lot.case]?.let { plusRecent(lot, it) } ?: true }
        val fondsVenus = fondsProposes(listOf(source to catalogue),
            fonds.installes().map { it.nameWithoutExtension }.toSet()).map { it.second }
        val rien = lots.isEmpty() && fondsVenus.isEmpty()
        val octets = lots.sumOf { it.octets } + fondsVenus.sumOf { it.octets }
        AlertDialog.Builder(this)
            .setTitle(R.string.recuperer_titre)
            .setMessage(if (rien) getString(R.string.recuperer_rien, source.libelle)
                else getString(R.string.recuperer_message, source.libelle, lots.size, fondsVenus.size,
                    Formatter.formatShortFileSize(this, octets)))
            .setPositiveButton(if (rien) android.R.string.ok else R.string.telecharger) { _, _ ->
                // Le PC n'est pas retenu : son jeton meurt avec le partage. Les pages
                // gardent son catalogue le temps de la session, puis se redessinent.
                cataloguesPc = listOf(source to catalogue)
                for (lot in lots) recuperations.addLast { telecharger(Offre(source, lot)) }
                for (fond in fondsVenus) recuperations.addLast { installerFond(source, fond) }
                recuperations.addLast { remplirCartes(); remplirItineraires() }
                if (!enCours.get()) recuperations.removeFirstOrNull()?.invoke()
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    // ------------------------------------------------------------------ premier lancement et zones

    /**
     * Au tout premier lancement, la carte s'ouvre sur la ville de l'adresse IP
     * (PositionIp) plutôt que sur un point fixe ; sans réponse, elle reste où
     * elle est. La zone de routage de la ville se propose ensuite (une fois).
     */
    private fun centrerSurIp() {
        thread(isDaemon = true) {
            val position = PositionIp.demander() ?: return@thread
            runOnUiThread {
                if (isDestroyed || reglages.vueConnue) return@runOnUiThread
                carte.controller.setZoom(12.0)
                carte.controller.setCenter(GeoPoint(position.first, position.second))
                reglages.vue = Triple(position.first, position.second, 12.0)
                proposerLotZone(attendreCatalogue = true)
            }
        }
    }

    /** Une zone de routage installée couvre-t-elle le centre de la carte ? */
    private fun zoneAuCentre(): Boolean {
        val centre = carte.mapCenter
        return lotAuPoint(horsLigne.lots(), centre.latitude, centre.longitude) != null
    }

    /** Sans zone de routage, la planification ne mènerait à rien : on le dit, et où la prendre. */
    private fun expliquerSansZone() {
        AlertDialog.Builder(this)
            .setTitle(R.string.plan_sans_zone_titre)
            .setMessage(R.string.plan_sans_zone_message)
            .setPositiveButton(R.string.menu_itineraires) { _, _ -> ouvrirItineraires() }
            .setNegativeButton(R.string.fermer, null)
            .show()
    }

    /**
     * Le premier téléchargement automatique d'une case demande d'abord, même
     * sur Wi-Fi : une zone pèse plusieurs centaines de Mo, et recentrer la
     * carte sur une ville ne doit pas suffire à la télécharger. La question
     * n'est posée qu'une fois par case ; un refus est retenu, la zone restant
     * disponible dans « Gestion des itinéraires ». Une zone acceptée se
     * renouvelle ensuite d'elle-même.
     */
    private fun demanderZone(offre: Offre) {
        reglages.zonesProposees = reglages.zonesProposees + offre.lot.case
        AlertDialog.Builder(this)
            .setTitle(R.string.zone_initiale_titre)
            .setMessage(getString(R.string.zone_initiale_message, offre.lot.case,
                Formatter.formatShortFileSize(this, offre.lot.octets)))
            .setPositiveButton(R.string.telecharger) { _, _ ->
                autoLotDemande = null
                telecharger(offre)
            }
            .setNegativeButton(R.string.zone_refuser) { _, _ ->
                autoLotDemande = null
                reglages.zonesRefusees = reglages.zonesRefusees + offre.lot.case
                Toast.makeText(this, getString(R.string.zone_refusee, offre.lot.case), Toast.LENGTH_LONG).show()
                avancer()
                planifierCalques()
            }
            .setCancelable(false)
            .show()
    }

    // ------------------------------------------------------------------ import GPX et KML

    /**
     * Importer un GPX ou un KML, ou retirer celui qui est affiché, depuis le menu
     * principal, comme sur la page du PC : importer n'est pas tracer.
     */
    private fun basculerImport() {
        if (nomImport != null) {
            retirerImport(); return
        }
        startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            // Un GPX arrive souvent en application/octet-stream : le tri se fait à la lecture.
            type = "*/*"
        }, IMPORT)
    }

    private fun nomAffiche(adresse: Uri): String = try {
        contentResolver.query(adresse, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
            if (c.moveToFirst()) c.getString(0) else null
        } ?: "import"
    } catch (e: Exception) {
        "import"
    }

    private fun importer(adresse: Uri) {
        etat.setText(R.string.import_lecture)
        EXECUTEUR_TRACE.execute {
            val nom = nomAffiche(adresse)
            val traces = try {
                val octets = contentResolver.openInputStream(adresse)?.use { it.readBytes() } ?: ByteArray(0)
                if (octets.size > IMPORT_MAX_OCTETS) null else TracesImportees.lire(String(octets, Charsets.UTF_8), nom)
            } catch (e: Exception) {
                null
            }
            runOnUiThread {
                if (isDestroyed) return@runOnUiThread
                if (traces.isNullOrEmpty()) etat.setText(R.string.import_invalide) else afficherImport(traces, nom)
            }
        }
    }

    /** Chaque trace dans la couleur de son fichier (un GPX en jaune, comme sur le PC) ; un toucher ouvre sa fiche. */
    private fun afficherImport(traces: List<TraceImportee>, fichier: String) {
        retirerImport()
        val densite = resources.displayMetrics.density
        val gpx = fichier.endsWith(".gpx", true) || traces.all { it.couleur == null }
        var sud = 90.0; var nord = -90.0; var ouest = 180.0; var est = -180.0
        fun ajouter(ligne: Polyline) {
            carte.overlays.add(1 + tracesImportees.size, ligne)        // au-dessus des calques, sous le tracé
            tracesImportees.add(ligne)
        }
        for (t in traces) for (segment in t.segments) {
            val points = segment.map { GeoPoint(it.first, it.second) }
            if (gpx) ajouter(Polyline(carte).apply {
                setPoints(points)
                outlinePaint.color = COULEUR_GPX_BORD; outlinePaint.strokeWidth = 7 * densite
                outlinePaint.pathEffect = DashPathEffect(floatArrayOf(9 * densite, 6 * densite), 0f)
                relatedObject = t
            })
            ajouter(Polyline(carte).apply {
                setPoints(points)
                outlinePaint.color = t.couleur ?: COULEUR_GPX
                outlinePaint.strokeWidth = (if (gpx) 4f else (t.epaisseur ?: 4f) * 0.8f) * densite
                outlinePaint.strokeCap = Paint.Cap.ROUND
                if (gpx) outlinePaint.pathEffect = DashPathEffect(floatArrayOf(9 * densite, 6 * densite), 0f)
                relatedObject = t
            })
            for ((lat, lon) in segment) {
                sud = minOf(sud, lat); nord = maxOf(nord, lat); ouest = minOf(ouest, lon); est = maxOf(est, lon)
            }
        }
        nomImport = fichier.substringBeforeLast('.')
        importGpx = gpx
        etat.text = ""
        majLegende()
        carte.zoomToBoundingBox(BoundingBox(nord, est, sud, ouest), true, dp(30))
        carte.invalidate()
    }

    /** La trace importée la plus haute à moins de 16 dp du doigt, ou null. */
    private fun traceImporteeToucheeA(p: GeoPoint): TraceImportee? {
        val tolerance = 16.0 * resources.displayMetrics.density
        return tracesImportees.asReversed().firstOrNull { it.isCloseTo(p, tolerance, carte) }
            ?.relatedObject as? TraceImportee
    }

    private fun retirerImport() {
        tracesImportees.forEach { carte.overlays.remove(it) }
        tracesImportees.clear()
        nomImport = null
        importGpx = false
        majLegende()
        carte.invalidate()
    }

    /** La fiche d'une trace importée, comme la bulle du PC : lieu, date, distance, dénivelé, durée. */
    private fun afficherTraceImportee(t: TraceImportee) {
        val lu = TracesImportees.lireNom(t.nom)
        val lignes = mutableListOf<String>()
        lu.date?.let { iso ->
            runCatching { LocalDate.parse(iso).format(DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)) }
                .getOrNull()?.let { jour -> lignes += getString(R.string.import_date, lu.heure?.let { "$jour, $it" } ?: jour) }
        }
        // La distance du nom vient du GPX complet ; la géométrie d'un KML est souvent simplifiée.
        val km = lu.km ?: (TracesImportees.longueur(t.segments) / 1000)
        lignes += getString(R.string.import_distance, String.format(Locale.getDefault(), "%.2f km", km))
        val denivele = TracesImportees.denivele(t)
        if (denivele != null) lignes += getString(R.string.import_denivele, denivele.first, denivele.second, denivele.third)
        else lu.dplus?.let { lignes += getString(R.string.import_denivele_nom, it) }
        lu.minutes?.let { m ->
            lignes += getString(R.string.import_duree, if (m < 60) "$m min" else String.format(Locale.getDefault(), "%d h %02d", m / 60, m % 60))
        }
        AlertDialog.Builder(this)
            .setTitle(lu.titre.ifEmpty { t.nom.ifEmpty { nomImport ?: "" } })
            .setMessage(lignes.joinToString("\n"))
            .setPositiveButton(R.string.fermer, null)
            // Le retrait là où l'on regarde la trace, pas seulement dans le menu.
            .setNeutralButton(R.string.menu_retirer_import) { _, _ -> retirerImport() }
            .show()
    }

    // ------------------------------------------------------------------ appui long

    /**
     * L'appui long sur la carte, comme le clic droit du PC : les coordonnées
     * du point en titre, à copier, et deux façons d'y aller depuis la position
     * GPS : l'itinéraire de hike2gpx, ou la navigation d'une autre application
     * (lien geo:, que OsmAnd, Organic Maps ou Google Maps savent ouvrir).
     */
    private fun menuPoint(p: GeoPoint) {
        val coordonnees = String.format(Locale.US, "%.6f, %.6f", p.latitude, p.longitude)
        AlertDialog.Builder(this)
            .setTitle(coordonnees)
            .setItems(arrayOf(getString(R.string.point_copier), getString(R.string.point_itineraire),
                getString(R.string.point_naviguer))) { _, choix ->
                when (choix) {
                    0 -> {
                        (getSystemService(CLIPBOARD_SERVICE) as android.content.ClipboardManager)
                            .setPrimaryClip(android.content.ClipData.newPlainText("hike2gpx", coordonnees))
                        Toast.makeText(this, R.string.point_copie, Toast.LENGTH_SHORT).show()
                    }
                    1 -> itineraireVers(p)
                    else -> naviguerVers(p)
                }
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    /** L'itinéraire de hike2gpx de la position GPS jusqu'au point : la planification, ses deux points posés. */
    private fun itineraireVers(p: GeoPoint) {
        if (lotAuPoint(horsLigne.lots(), p.latitude, p.longitude) == null) {
            Toast.makeText(this, R.string.plan_point_sans_zone, Toast.LENGTH_SHORT).show(); return
        }
        avecPosition {
            val ici = dernierPointConnu()
            if (ici == null) {
                etat.setText(if (gpsActif()) R.string.position_recherchee else R.string.gps_inactif)
                etat.visibility = View.VISIBLE
                return@avecPosition
            }
            if (!modePlan) basculerPlanification()
            if (!modePlan) return@avecPosition          // planification refusée (trace en cours), déjà expliqué
            points.clear()
            effacerTrace()
            ajouterPoint(Point(ici.latitude, ici.longitude))
            ajouterPoint(Point(p.latitude, p.longitude))
        }
    }

    /** La navigation d'une autre application, par le lien geo: standard (RFC 5870). */
    private fun naviguerVers(p: GeoPoint) {
        val lien = Uri.parse(String.format(Locale.US, "geo:%.6f,%.6f?q=%.6f,%.6f", p.latitude, p.longitude,
            p.latitude, p.longitude))
        try {
            startActivity(Intent.createChooser(Intent(Intent.ACTION_VIEW, lien), getString(R.string.point_naviguer)))
        } catch (e: ActivityNotFoundException) {
            Toast.makeText(this, R.string.point_sans_application, Toast.LENGTH_LONG).show()
        }
    }

    // ------------------------------------------------------------------ position et trace GPS

    private val gestionnairePosition by lazy {
        getSystemService(LOCATION_SERVICE) as LocationManager
    }

    private fun aPosition(): Boolean =
        checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
            checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED

    /** La position n'est demandée qu'au premier appui sur un bouton, pas au lancement. */
    private fun avecPosition(action: () -> Unit) {
        if (aPosition()) {
            demarrerPosition()
            action()
            return
        }
        apresPermission = { demarrerPosition(); action() }
        requestPermissions(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION), PERMISSION_POSITION)
    }

    override fun onRequestPermissionsResult(requete: Int, permissions: Array<out String>,
                                            resultats: IntArray) {
        super.onRequestPermissionsResult(requete, permissions, resultats)
        if (requete == PERMISSION_NOTIFICATIONS) {
            val nom = exportANotifier
            exportANotifier = null
            if (nom != null && resultats.firstOrNull() == PackageManager.PERMISSION_GRANTED) posterNotificationExport(nom)
            return
        }
        if (requete != PERMISSION_POSITION) return
        val action = apresPermission
        apresPermission = null
        if (aPosition()) action?.invoke() else etat.setText(R.string.position_refusee)
    }

    /**
     * Les mises à jour de position, GPS et réseau : elles tournent tant que
     * l'écran existe, pour le point bleu et pour la trace. Le GPS ne dit rien
     * quand il est coupé ; le message du bouton le rappelle.
     */
    private fun demarrerPosition() {
        if (ecoutePosition != null || !aPosition()) return
        val ecoute = object : LocationListener {
            override fun onLocationChanged(location: Location) = surPosition(location)
            override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) {}
            override fun onProviderEnabled(provider: String) {}
            override fun onProviderDisabled(provider: String) {}
        }
        var posee = false
        for (fournisseur in listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)) {
            try {
                gestionnairePosition.requestLocationUpdates(fournisseur, 1_000L, 0f, ecoute,
                    Looper.getMainLooper())
                posee = true
            } catch (e: SecurityException) {
                // permission retirée entre-temps : pas de position
            } catch (e: Exception) {
                // fournisseur absent : l'autre suffit
            }
        }
        if (posee) ecoutePosition = ecoute
        dernierPointConnu()?.let { surPosition(it) }
    }

    private fun arreterPosition() {
        val ecoute = ecoutePosition ?: return
        try {
            gestionnairePosition.removeUpdates(ecoute)
        } catch (e: Exception) {
            // permission retirée entre-temps
        }
        ecoutePosition = null
    }

    private fun dernierPointConnu(): Location? {
        if (!aPosition()) return null
        return listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER).mapNotNull {
            try {
                gestionnairePosition.getLastKnownLocation(it)
            } catch (e: SecurityException) {
                null
            } catch (e: Exception) {
                null
            }
        }.maxByOrNull { it.time }
    }

    private fun gpsActif(): Boolean = try {
        gestionnairePosition.isProviderEnabled(LocationManager.GPS_PROVIDER)
    } catch (e: Exception) {
        false
    }

    /**
     * Une position reçue par l'écran : le point bleu et le recentrage. La
     * trace, elle, reçoit ses points de ServiceTrace, qui tourne aussi écran
     * éteint.
     */
    private fun surPosition(location: Location) {
        if (isDestroyed) return
        val precision = if (location.hasAccuracy()) location.accuracy else 0f
        val point = GeoPoint(location.latitude, location.longitude)
        positionOverlay?.apply {
            position = point
            this.precision = precision
        }
        carte.invalidate()
        if (centrerDesQuePosition) {
            centrerDesQuePosition = false
            centrerCarte(point)
        }
    }

    /** Un point retenu par ServiceTrace : l'écran visible le dessine. */
    private val surPointTrace: () -> Unit = {
        if (!isDestroyed) {
            dessinerTraceEnregistree()
            majEtatTrace()
            calculerDeniveleTrace()
        }
    }

    private fun centrerSurPosition() {
        avecPosition {
            val connu = dernierPointConnu()
            if (connu != null) {
                centrerCarte(GeoPoint(connu.latitude, connu.longitude))
            } else {
                centrerDesQuePosition = true
                etat.setText(if (gpsActif()) R.string.position_recherchee else R.string.gps_inactif)
            }
        }
    }

    private fun centrerCarte(point: GeoPoint) {
        if (carte.zoomLevelDouble < 14.0) carte.controller.setZoom(15.0)
        carte.controller.setCenter(point)
        carte.invalidate()
        // Un recentrage sur la position est un usage réel de la zone : le lot
        // qui la couvre se propose sans attendre un geste sur la carte.
        planifierPays()
        planifierCalques()
        proposerLotZone(attendreCatalogue = true)
    }

    private fun basculerEnregistrement() {
        if (EnregistrementGps.actif) arreterEnregistrement() else avecPosition { demarrerEnregistrement() }
    }

    private fun demarrerEnregistrement() {
        val dossier = dossierTraces().apply { mkdirs() }
        val nom = "trace-" + SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(Date()) + ".gpx"
        val trace = TraceGps(reglages.distanceMin, reglages.dureeMin * 1_000L, reglages.precisionMax)
        EnregistrementGps.demarrer(trace, File(dossier, nom))
        // Le service tient le GPS écran éteint ; sans la notification (refusée
        // sur Android 13 et plus), il tourne quand même.
        ServiceTrace.demarrer(this)
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), PERMISSION_NOTIFICATIONS)
        traceEnregistree?.let { carte.overlays.remove(it) }
        traceEnregistree = null
        modePlan = false
        modeRecherche = false
        rechercheRepliee = false
        effacerReperes()
        majBoutonTrace()
        appliquerAffichage()
        etat.setText(R.string.trace_demarree)
        if (!gpsActif()) Toast.makeText(this, R.string.gps_inactif, Toast.LENGTH_LONG).show()
    }

    private fun arreterEnregistrement() {
        ServiceTrace.arreter(this)
        val trace = EnregistrementGps.arreter() ?: return
        val fichier = EnregistrementGps.fichier
        majBoutonTrace()
        if (trace.taille == 0) {
            fichier?.let { EnregistrementGps.terminer(it) }
            appliquerAffichage()
            Toast.makeText(this, R.string.trace_sans_point, Toast.LENGTH_LONG).show()
            return
        }
        try {
            fichier?.writeText(Gpx.ecrireTrace(trace.points, fichier.nameWithoutExtension))
            fichier?.let { EnregistrementGps.terminer(it) }
        } catch (e: Exception) {
            // Le journal reste : la trace sera refaite au prochain lancement.
            appliquerAffichage()
            Toast.makeText(this, texte(e), Toast.LENGTH_LONG).show()
            return
        }
        fichierTrace = fichier
        appliquerAffichage()
        val resume = resumeTrace(trace)
        etat.text = resume
        // Comme un tracé planifié : directement dans Téléchargements, sans rien demander.
        exporterTrace(fichier)
        AlertDialog.Builder(this)
            .setTitle(R.string.trace_titre)
            .setMessage(listOf(resume, getString(R.string.trace_dans_telechargements, fichier?.name ?: ""))
                .joinToString("\n"))
            .setPositiveButton(R.string.fermer, null)
            .show()
    }

    /**
     * Le dénivelé de la trace en cours, calculé avec gpx2elev sur les seules
     * tuiles du cache : en randonnée, le téléphone n'a pas de réseau. Le calcul
     * se fait hors de l'écran ; un point arrivé entre-temps le relance une fois.
     */
    private fun calculerDeniveleTrace() {
        val trace = EnregistrementGps.trace ?: return
        if (trace.taille < 2) return
        if (!traceOccupe.compareAndSet(false, true)) {
            traceARefaire = true
            return
        }
        val points = trace.points
        EXECUTEUR_TRACE.execute {
            val profil = try {
                Denivele.calculer(points.map { doubleArrayOf(it.lon, it.lat) }, reliefTrace)
            } catch (e: Exception) {
                null
            }
            runOnUiThread {
                traceOccupe.set(false)
                if (isDestroyed) return@runOnUiThread
                if (EnregistrementGps.trace === trace) {
                    trace.profil = profil
                    majEtatTrace()
                }
                if (traceARefaire) {
                    traceARefaire = false
                    calculerDeniveleTrace()
                }
            }
        }
    }

    private fun dessinerTraceEnregistree() {
        val trace = EnregistrementGps.trace ?: return
        if (trace.taille == 0) return
        val ligne = traceEnregistree ?: Polyline(carte).also {
            it.outlinePaint.color = 0xffe64a19.toInt()
            it.outlinePaint.strokeWidth = dp(4).toFloat()
            it.outlinePaint.strokeCap = Paint.Cap.ROUND
            carte.overlays.add(2, it)          // au-dessus de l'itinéraire, sous les repères
            traceEnregistree = it
        }
        ligne.setPoints(trace.points.map { GeoPoint(it.lat, it.lon) })
        carte.invalidate()
    }

    private fun majBoutonTrace() {
        if (!::boutonTrace.isInitialized) return
        val actif = EnregistrementGps.actif
        val plan = modePlan && !actif
        boutonTrace.enregistre = actif || plan
        // Le carré rouge n'apparaît que pendant une trace ou une planification :
        // le départ se donne par le menu, l'arrêt doit rester à portée de pouce.
        boutonTrace.visibility = if (actif || plan) View.VISIBLE else View.GONE
        boutonTrace.contentDescription = getString(when {
            actif -> R.string.bouton_trace_stop
            plan -> R.string.menu_terminer_plan
            else -> R.string.bouton_trace
        })
    }

    private fun majEtatTrace() {
        val trace = EnregistrementGps.trace ?: return
        val profil = trace.profil
        etat.text = when {
            trace.taille < 2 -> getString(R.string.trace_etat_debut, pointsTexte(trace.taille),
                distanceTexte(trace.distance), dureeTexte(trace.duree))
            profil != null -> getString(R.string.trace_etat, pointsTexte(trace.taille),
                distanceTexte(trace.distance), dureeTexte(trace.duree),
                profil.monteeM, profil.descenteM)
            else -> getString(R.string.trace_etat_sans_denivele, pointsTexte(trace.taille),
                distanceTexte(trace.distance), dureeTexte(trace.duree))
        }
    }

    private fun resumeTrace(trace: TraceGps): String {
        val points = pointsTexte(trace.taille)
        val distance = distanceTexte(trace.distance)
        val duree = dureeTexte(trace.duree)
        val profil = trace.profil
        return when {
            trace.taille < 2 ->
                getString(R.string.trace_resume_court, points, distance, duree)
            profil != null ->
                getString(R.string.trace_resume_denivele, points, distance, duree,
                    profil.monteeM, profil.descenteM)
            else -> getString(R.string.trace_resume_sans_denivele, points, distance, duree)
        }
    }

    private fun dossierTraces(): File =
        File(getExternalFilesDir(null) ?: filesDir, "traces")

    private fun tracesEnregistrees(): List<File> =
        dossierTraces().listFiles { f -> f.isFile && f.extension.equals("gpx", true) }
            ?.sortedByDescending { it.lastModified() } ?: emptyList()

    private fun reseauDisponible(): Boolean = try {
        getSystemService(ConnectivityManager::class.java).activeNetwork != null
    } catch (e: Exception) {
        false
    }

    /**
     * L'export relit le GPX et remet le dénivelé gpx2elev : d'abord le cache,
     * qui suffit souvent ; sinon le réseau, s'il est là. Sans les deux, le
     * fichier part tel qu'il a été enregistré.
     */
    private fun exporterTrace(fichier: File?) {
        if (fichier == null || !fichier.exists()) return
        fichierTrace = fichier
        etat.setText(R.string.trace_denivele_calcul)
        EXECUTEUR_TRACE.execute {
            val texte = try {
                fichier.readText()
            } catch (e: Exception) {
                null
            }
            val points = texte?.let { Gpx.lireTrace(it) } ?: emptyList()
            val enrichi = preparerGpxEnrichi(points, fichier)
            runOnUiThread {
                if (isDestroyed) return@runOnUiThread
                contenuExport = enrichi?.toByteArray()
                lancerExport(fichier.name)
            }
        }
    }

    private fun preparerGpxEnrichi(points: List<PointTrace>, fichier: File): String? {
        if (points.size < 2) return null
        // Une instance neuve : le calcul du tracé peut lire le relief en même
        // temps, et Mapterhorn n'est pas partagé entre deux tâches.
        val sources = sourcesRelief(Mapterhorn(filesDir, reseau = reseauDisponible()))
        return try {
            val (enrichis, profil) = Gpx.enrichir(points, sources)
            Gpx.ecrireTrace(enrichis, fichier.nameWithoutExtension,
                getString(R.string.trace_gpx_desc, profil.monteeM, profil.descenteM))
        } catch (e: Exception) {
            null        // aucun relief complet : le GPX reste tel quel
        }
    }

    /**
     * L'ordre de gpx2elev : IGN LiDAR HD quand le réseau est là, puis
     * Mapterhorn (son cache d'abord, le réseau s'il le permet).
     */
    private fun sourcesRelief(mapterhorn: Mapterhorn): List<SourceRelief> =
        if (reseauDisponible()) listOf(IgnLidar(), mapterhorn.source()) else listOf(mapterhorn.source())

    /**
     * Android 10 et plus (les appelants testent la version) : le GPX va directement
     * dans Téléchargements (MediaStore, sans permission ni sélecteur), comme sur le
     * PC. Avant, il faudrait une permission d'écriture : le sélecteur de fichiers reste.
     * Vrai si le fichier est écrit ; sinon l'erreur est dans le bandeau. Pas de message de succès.
     */
    @RequiresApi(Build.VERSION_CODES.Q)
    private fun ecrireTelechargements(nom: String, octets: ByteArray): Boolean {
        return try {
            val valeurs = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, nom)
                put(MediaStore.Downloads.MIME_TYPE, "application/gpx+xml")
                put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
            }
            val adresse = contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, valeurs)
                ?: throw IOException("MediaStore")
            contentResolver.openOutputStream(adresse)?.use { it.write(octets) }
            notifierExport(nom, adresse)
            true
        } catch (e: Exception) {
            etat.text = texte(e)
            false
        }
    }

    /**
     * MediaStore n'annonce rien : la notification dit où est le fichier, et un
     * toucher ouvre Téléchargements. Android 13 et plus demande l'autorisation
     * de notifier au premier export ; la notification part dès qu'elle est
     * accordée. Refusée, l'export reste silencieux.
     */
    private var exportANotifier: String? = null

    private fun notifierExport(nom: String, adresse: Uri) {
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            exportANotifier = nom
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), PERMISSION_NOTIFICATIONS)
            return
        }
        posterNotificationExport(nom)
    }

    private fun posterNotificationExport(nom: String) {
        val gestionnaire = getSystemService(NotificationManager::class.java)
        gestionnaire.createNotificationChannel(NotificationChannel(CANAL_EXPORT,
            getString(R.string.export_canal), NotificationManager.IMPORTANCE_LOW))
        val ouvrir = PendingIntent.getActivity(this, 0, Intent(DownloadManager.ACTION_VIEW_DOWNLOADS),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        gestionnaire.notify(nom.hashCode(), Notification.Builder(this, CANAL_EXPORT)
            .setSmallIcon(R.drawable.ic_btn_telecharger)
            .setContentTitle(nom)
            .setContentText(getString(R.string.export_notification_texte))
            .setContentIntent(ouvrir)
            .setAutoCancel(true)
            .build())
    }

    private fun lancerExport(nom: String) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val octets = contenuExport ?: fichierTrace?.takeIf { it.isFile }?.readBytes()
            contenuExport = null
            // Le « calcul du dénivelé » qui précédait s'efface : le fichier est dans Téléchargements.
            if (octets == null || ecrireTelechargements(nom, octets)) etat.text = ""
            return
        }
        startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "application/gpx+xml"
            putExtra(Intent.EXTRA_TITLE, nom)
        }, EXPORT_TRACE)
    }

    private fun pointsTexte(nombre: Int): String =
        resources.getQuantityString(R.plurals.trace_points, nombre, nombre)

    private fun distanceTexte(metres: Double): String =
        if (metres < 1_000) getString(R.string.distance_metres, metres.roundToInt())
        else getString(R.string.distance_km, metres / 1_000)

    private fun dureeTexte(millisecondes: Long): String {
        val secondes = (millisecondes / 1_000).coerceAtLeast(0)
        return when {
            secondes >= 3_600 -> getString(R.string.duree_heures, (secondes / 3_600).toInt(),
                ((secondes % 3_600) / 60).toInt())
            secondes >= 60 -> getString(R.string.duree_minutes, (secondes / 60).toInt())
            else -> getString(R.string.duree_secondes, secondes.toInt())
        }
    }

    // ------------------------------------------------------------------ export

    private fun exporter() {
        if (dernier == null) {
            etat.setText(R.string.rien_a_exporter); return
        }
        // Horodaté comme la trace GPS (« trace-… »), avec son propre préfixe pour ne pas les confondre.
        val nom = "itineraire-" + SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(Date()) + ".gpx"
        val coordonnees = dernier?.coordonnees ?: return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ecrireTelechargements(nom, Gpx.ecrire(coordonnees).toByteArray())
            return
        }
        startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "application/gpx+xml"
            putExtra(Intent.EXTRA_TITLE, nom)
        }, EXPORT)
    }

    /**
     * À l'arrêt de la planification, le parcours calculé est proposé en GPX :
     * c'est le seul moment où on l'enregistre, le bouton « GPX » de la barre a
     * disparu.
     */
    private fun proposerGpx() {
        AlertDialog.Builder(this)
            .setMessage(R.string.plan_gpx_proposer)
            .setPositiveButton(R.string.plan_gpx_enregistrer) { _, _ -> exporter() }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    @Deprecated("Activity de la plateforme : pas d'AndroidX dans cette application.")
    override fun onActivityResult(requete: Int, resultat: Int, donnees: Intent?) {
        super.onActivityResult(requete, resultat, donnees)
        IntentIntegrator.parseActivityResult(requete, resultat, donnees)?.let { scan ->
            scan.contents?.let { lienScanne(it) }       // null : scan annulé
            return
        }
        if (requete == IMPORT) {
            if (resultat == RESULT_OK) donnees?.data?.let { importer(it) }
            return
        }
        if (requete == EXPORT_ARCHIVE) {
            val choix = archiveAEcrire
            archiveAEcrire = null
            if (resultat == RESULT_OK && choix != null) donnees?.data?.let { ecrireArchive(it, choix.first, choix.second) }
            return
        }
        if (requete == IMPORT_ARCHIVE) {
            if (resultat == RESULT_OK) donnees?.data?.let { lireArchive(it) }
            return
        }
        if (requete == EXPORT_TRACE) {
            if (resultat != RESULT_OK) {
                contenuExport = null
                etat.setText(R.string.trace_export_annule)
                return
            }
            val adresse = donnees?.data ?: return
            try {
                contentResolver.openOutputStream(adresse)?.use { sortie ->
                    val contenu = contenuExport
                    if (contenu != null) sortie.write(contenu)
                    else fichierTrace?.takeIf { it.isFile }?.let { sortie.write(it.readBytes()) }
                }
                etat.text = ""              // le « calcul du dénivelé » qui précédait s'efface
            } catch (e: Exception) {
                etat.text = texte(e)
            }
            contenuExport = null
            return
        }
        val coordonnees = dernier?.coordonnees ?: return
        val adresse = donnees?.data ?: return
        if (requete != EXPORT || resultat != RESULT_OK) return
        try {
            contentResolver.openOutputStream(adresse)?.use { it.write(Gpx.ecrire(coordonnees).toByteArray()) }
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
                      ensuite: ((Boolean) -> Unit)? = null, discret: Boolean = false) {
        if (enCours.getAndSet(true)) {
            etat.setText(R.string.etat_occupe); return
        }
        val arret = AtomicBoolean(false)
        val sequence = ++sequenceTache
        // Une tâche discrète (lecture du catalogue au lancement) ne montre ni
        // bandeau ni progression : seule son erreur, s'il y en a une, s'affiche.
        tacheAffichee = !discret
        etat.setText(message)
        if (!discret) etat.visibility = View.VISIBLE
        progression.progress = 0
        progression.isIndeterminate = !interruptible
        progression.visibility = if (discret) View.GONE else View.VISIBLE
        arreter.visibility = if (interruptible && !discret) View.VISIBLE else View.GONE
        arreter.setOnClickListener { arret.set(true) }
        appliquerAffichage()
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        EXECUTEUR.execute {
            var reussie = false
            var interrompue = false
            val bilan = try {
                travail { !arret.get() }.also { reussie = true }
            } catch (e: Abandon) {
                interrompue = true
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
                if (discret && reussie) {
                    // Rien à dire : l'écran reste tel quel, sans bilan éphémère.
                    appliquerAffichage()
                } else {
                    etat.visibility = View.VISIBLE
                    // Le bilan d'une tâche de fond reste lisible quelques secondes,
                    // puis l'écran revient à son mode (carte seule, plan ou trace).
                    planificateur.postDelayed({
                        if (sequence == sequenceTache) {
                            tacheAffichee = false
                            appliquerAffichage()
                        }
                    }, 5000)
                }
                val reprendre = aReprendre
                ensuite?.invoke(reussie)
                if (reprendre && !enCours.get()) avancer()
                // Un recentrage demandé pendant la tâche n'a pas perdu sa demande.
                if (lotDeZoneEnAttente && !enCours.get() && autoLotDemande == null)
                    proposerLotZone()
                // « Arrêter » pendant une récupération l'arrête toute ; sinon la suivante part.
                if (interrompue) recuperations.clear()
                if (!enCours.get()) recuperations.removeFirstOrNull()?.invoke()
            }
        }
    }

    // ------------------------------------------------------------------ outils

    /**
     * Le suivi d'un téléchargement : la barre de progression et, avec un
     * libellé, le bandeau « Zone de routage E5_N40 · 120 Mo sur 248 Mo ·
     * 3,9 Mo/s · reste 00:33 ». Le réseau livre des paquets de quelques Ko :
     * l'écran ne se rafraîchit que quatre fois par seconde au plus, et à la fin.
     */
    private fun suiviTelechargement(libelle: String?): (Long, Long) -> Unit {
        var debut = 0L
        var faitsDebut = 0L
        var dernier = 0L
        return { faits, total ->
            val maintenant = SystemClock.elapsedRealtime()
            if (debut == 0L) {
                debut = maintenant
                faitsDebut = faits
            }
            if (maintenant - dernier >= 250 || faits >= total) {
                dernier = maintenant
                val avancement = (1000 * faits / maxOf(total, 1)).toInt()
                // Le débit sur ce qui est arrivé depuis le début, une fois la première seconde passée.
                val secondes = (maintenant - debut) / 1000.0
                val debit = if (secondes >= 1) (faits - faitsDebut) / secondes else 0.0
                val texte = when {
                    libelle == null -> null
                    debit > 0 -> getString(R.string.etat_progression, libelle,
                        Formatter.formatShortFileSize(this, faits), Formatter.formatShortFileSize(this, total),
                        Formatter.formatShortFileSize(this, debit.toLong()),
                        DateUtils.formatElapsedTime(((total - faits).coerceAtLeast(0) / debit).toLong()))
                    else -> getString(R.string.etat_progression_debut, libelle,
                        Formatter.formatShortFileSize(this, faits), Formatter.formatShortFileSize(this, total))
                }
                runOnUiThread {
                    progression.progress = avancement
                    if (texte != null) etat.text = texte
                }
            }
        }
    }

    private fun dp(n: Int) = (n * resources.displayMetrics.density).toInt()

    private fun titre(parent: LinearLayout, texte: Int) =
        parent.addView(TextView(this).apply { setText(texte); textSize = 18f; setPadding(0, dp(16), 0, dp(4)) })

    /**
     * Un titre suivi d'un « i » jaune, comme sur la page du PC : la note ne
     * prend pas de place dans la page, un toucher l'affiche (pas de survol
     * sur un téléphone, donc une petite fenêtre plutôt qu'une info-bulle).
     */
    private fun titreAvecInfo(parent: LinearLayout, texte: Int, info: Int) {
        val ligne = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, dp(16), 0, dp(4))
        }
        ligne.addView(TextView(this).apply { setText(texte); textSize = 18f })
        ligne.addView(TextView(this).apply {
            text = "i"
            textSize = 13f
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
            setTextColor(0xff4e342e.toInt())
            gravity = Gravity.CENTER
            background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(0xfffdd835.toInt()) }
            contentDescription = getString(info)
            setOnClickListener {
                AlertDialog.Builder(this@MainActivity).setMessage(info).setPositiveButton(R.string.fermer, null).show()
            }
        }, LinearLayout.LayoutParams(dp(24), dp(24)).apply { marginStart = dp(10) })
        parent.addView(ligne)
    }

    /**
     * Un réglage numérique : libellé à gauche, champ à droite. Chaque saisie
     * valide est enregistrée aussitôt (virgule décimale acceptée), pour ne pas
     * perdre la dernière valeur quand la fenêtre se ferme.
     */
    private fun champNombre(parent: LinearLayout, libelle: Int, valeur: Double,
                            entier: Boolean, enregistrer: (Double) -> Unit) {
        val ligne = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        ligne.addView(TextView(this).apply { setText(libelle) }, LinearLayout.LayoutParams(0, -2, 1f))
        val champ = EditText(this).apply {
            setText(nombre(valeur, entier))
            inputType = if (entier) InputType.TYPE_CLASS_NUMBER
            else InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
            setSingleLine()
            addTextChangedListener(object : TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
                override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
                override fun afterTextChanged(s: Editable?) {
                    val v = s?.toString()?.trim()?.replace(',', '.')?.toDoubleOrNull() ?: return
                    if (v.isFinite() && v >= 0) enregistrer(v)
                }
            })
        }
        ligne.addView(champ, LinearLayout.LayoutParams(dp(96), -2))
        parent.addView(ligne)
    }

    private fun nombre(valeur: Double, entier: Boolean): String =
        if (entier || valeur == valeur.roundToInt().toDouble()) valeur.roundToInt().toString()
        else String.format(Locale.getDefault(), "%.1f", valeur)

    /** Un changement de réglage s'applique au prochain point, sans arrêter la trace. */
    private fun appliquerReglagesTrace() {
        EnregistrementGps.trace?.apply {
            distanceMin = reglages.distanceMin
            dureeMin = reglages.dureeMin * 1_000L
            precisionMax = reglages.precisionMax
        }
        // Le service demande le GPS au rythme du filtre : il reprend sa demande.
        if (EnregistrementGps.actif) ServiceTrace.demarrer(this)
    }

    /** Une icône de 18 dp avant le texte du bouton, comme sur la page du PC ; rouge pour ce qui supprime. */
    private fun Button.avecIcone(icone: Int, rouge: Boolean = false): Button = apply {
        getDrawable(icone)?.mutate()?.let { d ->
            d.setBounds(0, 0, dp(18), dp(18))
            if (rouge) d.setTint(0xffb3261e.toInt())
            setCompoundDrawablesRelative(d, null, null, null)
        }
        compoundDrawablePadding = dp(6)
        if (rouge) setTextColor(0xffb3261e.toInt())
    }

    private fun boutonPetit(texte: Int, icone: Int, rouge: Boolean = false, action: () -> Unit) = Button(this).apply {
        setText(texte); textSize = 12f; isAllCaps = false
        minWidth = 0; minimumWidth = 0
        setPadding(dp(8), paddingTop, dp(8), paddingBottom)
        setOnClickListener { action() }
    }.avecIcone(icone, rouge)

    /** Quitte la planification ou la recherche ; faux s'il n'y en avait pas. */
    private fun quitterModes(): Boolean {
        if (!modePlan && !modeRecherche) return false
        modePlan = false
        modeRecherche = false
        effacerReperes()
        majBoutonTrace()
        cacherClavier()
        renduALaCarte()
        appliquerAffichage()
        return true
    }

    /**
     * Retour : d'abord quitter le mode (planification ou recherche), ensuite l'application.
     * Avant Android 13 le système appelle onBackPressed ; depuis, le geste passe par
     * [retourSysteme] (enregistré dans onCreate) et n'appelle plus onBackPressed.
     */
    @Suppress("DEPRECATION", "OVERRIDE_DEPRECATION")
    @SuppressLint("GestureBackNavigation")          // le chemin Android 13+ est retourSysteme
    override fun onBackPressed() {
        if (quitterModes()) return
        super.onBackPressed()
    }

    override fun onResume() {
        super.onResume(); carte.onResume()
        // La position ne se demande pas au lancement : sans autorisation,
        // demarrerPosition ne fait rien.
        demarrerPosition()
        EnregistrementGps.abonner(surPointTrace)
        if (EnregistrementGps.actif) {
            dessinerTraceEnregistree()
            majBoutonTrace()
            majEtatTrace()
            appliquerAffichage()
            calculerDeniveleTrace()
        }
        if (attenteAutorisation) {
            attenteAutorisation = false
            if (packageManager.canRequestPackageInstalls()) installerMaj()
            else Toast.makeText(this, R.string.maj_autorisation_refusee, Toast.LENGTH_LONG).show()
        }
    }

    override fun onPause() {
        reglages.vue = Triple(carte.mapCenter.latitude, carte.mapCenter.longitude, carte.zoomLevelDouble)
        // L'écran caché n'a plus besoin du point bleu : le GPS se repose, et une
        // trace en cours continue dans ServiceTrace.
        EnregistrementGps.desabonner(surPointTrace)
        arreterPosition()
        carte.onPause(); super.onPause()
    }

    override fun onDestroy() {
        arreterPosition()
        planificateur.removeCallbacksAndMessages(null)
        routeur.annuler()
        carte.onDetach()
        sourceMapsforge?.dispose()
        sourceMapsforge = null
        super.onDestroy()
    }

    companion object {
        /** Taille de dessin des cartes Mapsforge d'un PC, en pixels d'écran par pixel de la carte : celle des cartes en ligne. */
        private const val ECHELLE_RENDU = 1f
        private const val EXPORT = 1
        private const val EXPORT_TRACE = 2
        private const val IMPORT = 5
        private const val EXPORT_ARCHIVE = 6
        private const val IMPORT_ARCHIVE = 7
        /** Le jaune du GPX importé et son liseré, ceux de la page du PC. */
        private const val COULEUR_GPX = 0xffffe14a.toInt()
        private const val COULEUR_GPX_BORD = 0xff344132.toInt()
        private const val IMPORT_MAX_OCTETS = 20_000_000
        private const val PERMISSION_POSITION = 3
        private const val PERMISSION_NOTIFICATIONS = 4
        private const val CANAL_EXPORT = "export"
        private const val REESSAI_MS = 3_600_000L
        private const val VOILE = 0xe6ffffff.toInt()
        /** Le bleu de l'itinéraire, celui de la page du PC. */
        private const val COULEUR_ITINERAIRE = 0xff1565c0.toInt()
        private const val FLECHE_DP = 14          // la pastille de la page, 14 px
        private const val ZOOM_FLECHES = 12.0     // afficherFleches sur la page
        /** Une clé IGN valide, comme le réglage du PC : lettres, chiffres, _ et -, 100 au plus. */
        private val CLE_IGN = Regex("[A-Za-z0-9_-]{0,100}")
        /** Le zoom des tuiles vectorielles du lot, et celui où la page montre les calques. */
        // Au niveau du processus : un téléchargement survit à l'écran qui l'a lancé.
        private val EXECUTEUR = Executors.newSingleThreadExecutor()
        // Les calques et le relief ne prennent pas la tâche unique : l'itinéraire
        // reste calculable pendant qu'ils se lisent.
        private val EXECUTEUR_CALQUES = Executors.newSingleThreadExecutor()
        private val EXECUTEUR_DENIVELE = Executors.newSingleThreadExecutor()
        // La trace GPS et son export se suivent ; le calcul du dénivelé live
        // n'empêche pas l'écran de répondre.
        private val EXECUTEUR_TRACE = Executors.newSingleThreadExecutor()
        private val enCours = AtomicBoolean(false)
    }
}
