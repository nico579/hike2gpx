package org.hike2gpx.android

import android.app.Activity
import android.app.ActivityManager
import android.app.AlertDialog
import android.app.Dialog
import android.Manifest
import android.content.ContentValues
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Canvas
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.drawable.ColorDrawable
import android.graphics.drawable.GradientDrawable
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.net.ConnectivityManager
import android.net.Uri
import android.provider.MediaStore
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
import org.osmdroid.views.CustomZoomButtonsController
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.CopyrightOverlay
import org.osmdroid.views.overlay.MapEventsOverlay
import org.osmdroid.views.overlay.Marker
import org.osmdroid.views.overlay.Overlay
import org.osmdroid.views.overlay.Polyline
import org.osmdroid.views.overlay.ScaleBarOverlay
import java.io.File
import java.io.IOException
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
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
    private var courbe: CourbeDenivele? = null
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
    private var fenetreBibliotheque: LinearLayout? = null
    private var ecoutePosition: LocationListener? = null
    private var apresPermission: (() -> Unit)? = null
    private var centrerDesQuePosition = false
    private var traceEnregistree: Polyline? = null
    private var fichierTrace: File? = null
    private var insetBas = 0
    /** Le relief de la trace : cache gpx2elev seulement, sans réseau. */
    private lateinit var reliefTrace: Mapterhorn
    private val traceOccupe = AtomicBoolean(false)
    @Volatile private var traceARefaire = false
    private var contenuExport: ByteArray? = null
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

    override fun onCreate(etatSauve: Bundle?) {
        super.onCreate(etatSauve)
        Configuration.getInstance().userAgentValue = "${Depot.AGENT} (+https://github.com/nico579/hike2gpx)"
        Configuration.getInstance().osmdroidBasePath = File(cacheDir, "osmdroid")
        Configuration.getInstance().osmdroidTileCache = File(cacheDir, "osmdroid/tiles")
        reglages = Reglages(this)
        reglages.oublierPcs()                   // un PC ne se contacte qu'au scan de son QR code
        horsLigne = HorsLigne(filesDir)
        fonds = Fonds(horsLigne.racine)
        pays = Pays(assets)
        routeur = Routeur(Reglages.profils(this))
        calques = Calques(horsLigne)
        relief = Mapterhorn(filesDir)
        reliefTrace = Mapterhorn(filesDir, reseau = false)
        construire()
        // Avant la première mise en page, la carte n'a pas encore son centre
        // (0, 0) : le pays se lit sur la vue enregistrée, sinon une carte
        // nationale serait prise pour une carte du monde et remplacée par OSM.
        val vue = reglages.vue
        paysAffiche = pays.de(vue.first, vue.second)
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
                    if (modePlan) ajouterPoint(Point(p.latitude, p.longitude))
                    return true
                }
                override fun longPressHelper(p: GeoPoint) = false
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
                    planifierCalques(); planifierPays(); return false
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
        }
        recherche.addView(boutonVille)
        bandeauHaut.addView(recherche)
        bandeauHaut.addView(etat)
        progression = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 1000; visibility = View.GONE
        }
        bandeauHaut.addView(progression)
        arreter = Button(this).apply { setText(R.string.arreter); visibility = View.GONE }
        bandeauHaut.addView(arreter, LinearLayout.LayoutParams(-2, -2))
        legende = construireLegende()
        bandeauHaut.addView(legende)
        racine.addView(bandeauHaut, FrameLayout.LayoutParams(-1, -2, Gravity.TOP))

        bandeauBas = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        courbe = CourbeDenivele(this).apply {
            visibility = View.GONE
            setBackgroundColor(0xf7ffffff.toInt())
            contentDescription = getString(R.string.courbe_aide)
            onPosition = ::montrerPositionProfil
        }
        bandeauBas.addView(courbe, LinearLayout.LayoutParams(-1, dp(96)))
        val bas = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; setBackgroundColor(VOILE); setPadding(marge / 2, marge / 2, marge / 2, marge / 2)
        }
        for ((texte, action) in listOf<Pair<Int, () -> Unit>>(
            R.string.retirer to ::retirerPoint,
            R.string.effacer to ::effacer,
            R.string.revenir to ::revenirAuDepart,
        )) {
            bas.addView(Button(this).apply {
                setText(texte); textSize = 12f; isAllCaps = false; minWidth = 0; minimumWidth = 0
                setPadding(0, paddingTop, 0, paddingBottom)
                setOnClickListener { action() }
            }, LinearLayout.LayoutParams(0, -2, 1f))
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

        // Android 15 dessine l'application sous les barres du système : les bandeaux s'en écartent.
        racine.setOnApplyWindowInsetsListener { _, insets ->
            val (dessus, dessous) = if (Build.VERSION.SDK_INT >= 30)
                insets.getInsets(WindowInsets.Type.systemBars()).let { it.top to it.bottom }
            else @Suppress("DEPRECATION") (insets.systemWindowInsetTop to insets.systemWindowInsetBottom)
            bandeauHaut.setPadding(marge, marge + dessus, marge, marge)
            bandeauBas.setPadding(0, 0, 0, dessous)
            insetBas = dessous
            placerCommandes()
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
     * vide) a laissé son journal : il redevient un GPX de la bibliothèque.
     */
    private fun recupererTraces() {
        val refaites = EnregistrementGps.recuperer(dossierTraces())
        if (refaites.isEmpty()) return
        fichierTrace = refaites.last()
        Toast.makeText(this, getString(R.string.trace_recuperee,
            refaites.joinToString(", ") { it.name }), Toast.LENGTH_LONG).show()
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
        fun ligne(texte: Int, couleur: Int, pastille: Boolean = false, tirets: Boolean = false,
                  cercle: Int = 0xffffffff.toInt()) {
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
                        pinceau.color = cercle
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
        ligne(R.string.legende_jonction, CalquesOverlay.COULEUR_JONCTION, true, cercle = CalquesOverlay.CONTOUR_JONCTION)
        return boite
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
        // Ni légende ni recherche dans les bandeaux de planification et
        // d'enregistrement : la carte, l'état et les commandes suffisent.
        legende?.visibility = View.GONE
        bandeauBas.visibility = if (!bandeauxMasques && modePlan) View.VISIBLE else View.GONE
        afficherCourbe()
        placerCommandes()
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
     * La courbe n'a de sens qu'avec un profil calculé. Quand elle prend la
     * place au-dessus des boutons, l'échelle et l'attribution remontent pour
     * rester lisibles, comme les bandeaux de la page.
     */
    private fun afficherCourbe() {
        val vue = courbe ?: return
        val montre = reglages.courbeDenivele && vue.profil != null && modePlan && !bandeauxMasques
        vue.visibility = if (montre) View.VISIBLE else View.GONE
        if (!montre) cacherRepereProfil()
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
            outlinePaint.color = 0xff175dcb.toInt()
            outlinePaint.strokeWidth = 8f
        }
        carte.overlays.add(1, trace)        // sous les touches et les repères
        // Jamais de recadrage : les points sont posés à l'écran, et la carte reste
        // là où on l'a mise pour poser le suivant.
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
        proposerLotZone()
        planificateur.postDelayed({ rafraichirCalques() }, 350)
    }

    /**
     * Comme la page, s'arrêter sur une région est un usage réel : le lot de la
     * case du centre se télécharge de lui-même s'il manque, ou si le catalogue
     * en a un plus récent. Un survol sous le zoom 14 ne suffit pas, mais un
     * recentrage (recherche, position GPS) le propose aussitôt, sans attendre
     * un geste sur la carte. Une case refusée ou en échec attend une heure.
     */
    private fun proposerLotZone(attendreCatalogue: Boolean = false) {
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
                fondChoisi(horsLigne, source, Fonds.titre(source)) {
                    appliquerFond(source)
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
            })
        }
        colonne.addView(Button(this).apply { setText(R.string.scanner_qr); setOnClickListener { scannerQr() } })

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
            ligne.addView(boutonPetit(R.string.supprimer) { confirmerSuppressionFond(f) })
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
                if (reglages.fond == source && fonds.parSource()[source] == null)
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
                appliquerFond(Fonds.source(fond.nom))
                remplirCartes()
            }
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
            })
        }
        colonne.addView(Button(this).apply { setText(R.string.scanner_qr); setOnClickListener { scannerQr() } })

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
                ligne.addView(boutonPetit(R.string.mettre_a_jour) { telecharger(offre) })
            ligne.addView(boutonPetit(R.string.supprimer) { supprimerLot(lot) })
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
     *
     * Une carte nationale ne sert que dans son pays : si le centre de la carte
     * en est sorti, celle du pays affiché prend sa place, ou OpenStreetMap s'il
     * n'y en a pas. Un fond du monde ou hors ligne reste tel quel.
     */
    private fun appliquerFond(cle: String) {
        val horsLigne = fonds.parSource()[cle]
        val national = CartesEnLigne.parCle(cle)?.pays != null
        val choix = if (horsLigne == null && national &&
            !CartesEnLigne.disponible(cle, paysAffiche, reglages.cleIgn))
            CartesEnLigne.defaut(paysAffiche) else cle
        val fichiers = fonds.parSource()[choix]
        val enLigne = CartesEnLigne.parCle(choix)
        val servi = CartesEnLigne.disponible(choix, paysAffiche, reglages.cleIgn)
        when {
            fichiers != null -> {
                val minimum = zoomMin(fichiers)
                carte.setTileProvider(OfflineTileProvider(SimpleRegisterReceiver(this), fichiers.toTypedArray()))
                carte.setTileSource(XYTileSource("hors-ligne-$choix", minimum, 19, 256, "", arrayOf<String>(),
                    "© ${Fonds.titre(choix)}"))
                carte.setMinZoomLevel(minimum.toDouble())
                if (carte.zoomLevelDouble < minimum) carte.controller.setZoom(minimum.toDouble())
            }
            servi && enLigne != null -> {
                carte.setTileProvider(MapTileProviderBasic(applicationContext))
                carte.setTileSource(CartesEnLigne.tuile(enLigne, reglages.cleIgn))
                carte.setMinZoomLevel(null)         // le zoom le plus bas de la source en ligne
            }
            else -> {
                carte.setTileProvider(MapTileProviderBasic(applicationContext))
                carte.setTileSource(TileSourceFactory.MAPNIK)
                carte.setMinZoomLevel(null)
            }
        }
        reglages.fond = if (fichiers != null || (servi && enLigne != null)) choix else "osm"
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
        if (fonds.parSource()[reglages.fond] == null &&
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
            Triple(R.drawable.ic_bibliotheque, R.string.menu_bibliotheque, ::ouvrirBibliotheque),
            Triple(R.drawable.ic_carte, R.string.menu_cartes, ::ouvrirCartes),
            Triple(R.drawable.ic_itineraires, R.string.menu_itineraires, ::ouvrirItineraires),
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
    private fun ouvrirAide() {
        startActivity(Intent(Intent.ACTION_VIEW,
            Uri.parse("https://github.com/nico579/hike2gpx/blob/main/android/README.md")))
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
        }
        appliquerAffichage()
    }

    // ------------------------------------------------------------------ bibliothèque

    /** L'historique des parcours enregistrés, rangé dans « Ma bibliothèque ». */
    private fun ouvrirBibliotheque() {
        val colonne = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(8), dp(16), dp(8))
        }
        fenetreBibliotheque = colonne
        remplirBibliotheque()
        AlertDialog.Builder(this)
            .setTitle(R.string.menu_bibliotheque)
            .setView(ScrollView(this).apply { addView(colonne) })
            .setPositiveButton(R.string.fermer, null)
            .setOnDismissListener { fenetreBibliotheque = null }
            .show()
    }

    private fun remplirBibliotheque() {
        val colonne = fenetreBibliotheque ?: return
        colonne.removeAllViews()
        titre(colonne, R.string.titre_traces)
        val traces = tracesEnregistrees()
        if (traces.isEmpty()) {
            colonne.addView(TextView(this).apply { setText(R.string.traces_aucune) })
            return
        }
        val cases = linkedMapOf<File, CheckBox>()
        val date = SimpleDateFormat("dd/MM/yyyy HH:mm:ss", Locale.getDefault())
        for (f in traces) {
            val ligne = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
            }
            val selection = CheckBox(this)
            cases[f] = selection
            ligne.addView(selection, LinearLayout.LayoutParams(-2, -2))
            ligne.addView(TextView(this).apply {
                text = "${date.format(Date(f.lastModified()))} · " +
                    Formatter.formatShortFileSize(this@MainActivity, f.length())
                textSize = 13f
            }, LinearLayout.LayoutParams(0, -2, 1f))
            ligne.addView(boutonPetit(R.string.exporter) { exporterTrace(f) })
            ligne.addView(boutonPetit(R.string.supprimer) { confirmerSuppression(listOf(f)) })
            colonne.addView(ligne)
        }
        colonne.addView(Button(this).apply {
            setText(R.string.traces_supprimer_selection)
            setOnClickListener {
                val choisies = cases.filterValues { it.isChecked }.keys.toList()
                if (choisies.isEmpty())
                    Toast.makeText(this@MainActivity, R.string.traces_selection_vide,
                        Toast.LENGTH_SHORT).show()
                else confirmerSuppression(choisies)
            }
        })
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
            setText(R.string.afficher_courbe); isChecked = reglages.courbeDenivele
            setOnCheckedChangeListener { _, v -> reglages.courbeDenivele = v; afficherCourbe() }
        })
        colonne.addView(CheckBox(this).apply {
            setText(R.string.afficher_recherche); isChecked = reglages.recherche
            setOnCheckedChangeListener { _, v -> reglages.recherche = v; appliquerAffichage() }
        })

        // La clé IGN du SCAN 25, le même réglage que sur le PC.
        titre(colonne, R.string.reglages_cle_ign)
        colonne.addView(TextView(this).apply {
            setText(R.string.reglages_cle_note); textSize = 12f
        })
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
        getString(R.string.etat_pc_lus, catalogue.fonds.size, catalogue.lots.size)
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
        AlertDialog.Builder(this)
            .setTitle(R.string.trace_titre)
            .setMessage(listOf(resume, getString(R.string.trace_fichier, fichier?.name ?: ""))
                .joinToString("\n"))
            .setPositiveButton(R.string.trace_exporter) { _, _ -> exporterTrace(fichier) }
            .setNegativeButton(R.string.fermer, null)
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
     * Android 10 et plus : le GPX va directement dans Téléchargements (MediaStore,
     * sans permission ni sélecteur), comme sur le PC. Avant, il faudrait une
     * permission d'écriture : le sélecteur de fichiers reste.
     */
    private val telechargementsDirects get() = Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q

    private fun ecrireTelechargements(nom: String, octets: ByteArray) {
        try {
            val valeurs = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, nom)
                put(MediaStore.Downloads.MIME_TYPE, "application/gpx+xml")
                put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
            }
            val adresse = contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, valeurs)
                ?: throw IOException("MediaStore")
            contentResolver.openOutputStream(adresse)?.use { it.write(octets) }
            etat.text = getString(R.string.export_telechargements, nom)
        } catch (e: Exception) {
            etat.text = texte(e)
        }
    }

    private fun lancerExport(nom: String) {
        if (telechargementsDirects) {
            val octets = contenuExport ?: fichierTrace?.takeIf { it.isFile }?.readBytes()
            contenuExport = null
            if (octets != null) ecrireTelechargements(nom, octets)
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
        if (telechargementsDirects) {
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
                etat.setText(R.string.export_fait)
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
    }

    private fun boutonPetit(texte: Int, action: () -> Unit) = Button(this).apply {
        setText(texte); textSize = 12f; isAllCaps = false
        minWidth = 0; minimumWidth = 0
        setPadding(dp(8), paddingTop, dp(8), paddingBottom)
        setOnClickListener { action() }
    }

    private fun confirmerSuppression(fichiers: List<File>) {
        if (fichiers.isEmpty()) return
        val message = if (fichiers.size == 1)
            getString(R.string.trace_supprimer_message, fichiers.first().name)
        else getString(R.string.traces_supprimer_message, fichiers.size)
        AlertDialog.Builder(this)
            .setTitle(R.string.trace_supprimer_titre)
            .setMessage(message)
            .setPositiveButton(R.string.supprimer) { _, _ ->
                fichiers.forEach { it.delete() }
                if (fichiers.any { it == fichierTrace }) fichierTrace = null
                contenuExport = null
                remplirBibliotheque()
                remplirReglages()
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    /** Retour : d'abord quitter le mode (planification ou recherche), ensuite l'application. */
    @Suppress("DEPRECATION", "OVERRIDE_DEPRECATION")
    override fun onBackPressed() {
        if (modePlan || modeRecherche) {
            modePlan = false
            modeRecherche = false
            effacerReperes()
            majBoutonTrace()
            cacherClavier()
            appliquerAffichage()
            return
        }
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
        super.onDestroy()
    }

    companion object {
        private const val EXPORT = 1
        private const val EXPORT_TRACE = 2
        private const val PERMISSION_POSITION = 3
        private const val PERMISSION_NOTIFICATIONS = 4
        private const val REESSAI_MS = 3_600_000L
        private const val VOILE = 0xe6ffffff.toInt()
        /** Une clé IGN valide, comme le réglage du PC : lettres, chiffres, _ et -, 100 au plus. */
        private val CLE_IGN = Regex("[A-Za-z0-9_-]{0,100}")
        /** Le zoom des tuiles vectorielles du lot, et celui où la page montre les calques. */
        private const val ZOOM_CALQUES = 14.0
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
