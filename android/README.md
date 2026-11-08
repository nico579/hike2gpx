# Application Android

Le téléphone ne fabrique rien : il prend les lots hors ligne que le serveur
publie sur GitHub (le dépôt nico579/hike2gpx-bundles), ou ceux d'un PC du
réseau local, et calcule l'itinéraire lui-même avec BRouter, sans réseau.

## Ce qu'elle fait

L'écran est celui de la page du PC : la carte d'abord, en plein écran. Un
bouton à trois traits, en bas à droite, ouvre le menu de Locus Map :
« Recherche », « Ma bibliothèque », « Enregistrer un parcours », « Planifier un
itinéraire » et « Réglages ». La carte reste seule tant qu'on n'a pas choisi un
mode. En planification, on touche la carte pour poser le départ, puis l'arrivée
et d'éventuelles étapes ; « Retirer » retire le dernier point, « Effacer » les
retire tous, et « Revenir » ajoute le départ en fin de parcours pour fermer une
boucle. Dès qu'il y a deux points, l'itinéraire se calcule hors ligne et
s'affiche ; « GPX » l'exporte. Un bouton rond rouge au carré, comme celui de la
trace, arrête la planification ; un second choix de « Planifier un itinéraire »
le fait aussi. La carte redevient seule, sans effacer le parcours.

Le menu « Recherche » ouvre le champ de la page : il recentre la carte sur
une ville ou sur des coordonnées « lat, lon », sans poser de point. Les
communes françaises répondent d'abord (geo.api.gouv.fr, avec leur
département) ; ailleurs, ou si la France ne connaît rien, Nominatim donne les
villes et villages d'OSM avec leur région et leur pays. Une seule réponse
recadre aussitôt, plusieurs se choisissent dans une liste ; le bandeau de
recherche se referme ensuite, sans légende pendant la saisie, et un tap sur la
carte le referme aussi. Le menu « Recherche » reste disponible en planification ;
pendant l'enregistrement, seul l'état de la trace s'affiche.

Les calques du lot s'affichent sur la carte, comme ceux de la page : les
chemins OSM (sentiers en tirets violets, pistes et routes) avec les barrières
qui gênent un piéton et les franchissements bloquants (rouge) ou à vérifier
(orange), et les chemins de chaque fournisseur national retenu par le lot
(BD TOPO en France, turquoise), chacun avec sa coche dans les réglages
(« Chemin IGN BD TOPO », « Chemin ATKIS »…). Ils n'apparaissent qu'à
partir du zoom 14, celui des tuiles vectorielles du lot : en dessous, mieux
vaut ne rien montrer qu'un réseau tronqué. Les réglages rappellent le zoom
courant ; une coche sous ce zoom, ou une vue sans chemin de calque, le dit
plutôt que de laisser croire que la case ne marche pas. Les calques sont lus dans
`calques.mbtiles` (MVT) en arrière-plan, sans gêner le calcul de l'itinéraire ;
un lot ancien qui n'a pas ce fichier n'affiche simplement rien.

Sous la distance, l'itinéraire donne aussi le dénivelé et la durée de marche,
calculés comme sur le PC par le protocole de gpx2elev : altitude échantillonnée
tous les 5 m, lissage gaussien de 20 m, D+/D− avec une hystérésis de 2 m, puis
modèle de Tobler tous les 20 m. Le téléphone lit le même relief Mapterhorn
(tuiles Terrarium du zoom 12, LiDAR HD de l'IGN en France), qu'il rapatrie à la
demande dans `gpx2elev/tiles` ; une tuile déjà là sert aux parcours suivants.
Le calcul du relief est séparé de celui de l'itinéraire : le tracé s'affiche
d'abord, le dénivelé arrive ensuite. Sans relief disponible, la ligne le dit et
la valeur BRouter ne le remplace pas, comme sur le PC. Les bandeaux de
planification et d'enregistrement ne montrent ni légende ni champ de recherche :
la carte, l'état et les commandes suffisent. La coche « Afficher courbe du
dénivelé » dessine au-dessus des boutons le profil de la page — distance en
abscisse, altitude lissée en ordonnée, aire bleue et bornes d'altitude. La courbe
n'apparaît qu'une fois le relief calculé ;
décochée, elle laisse toute la carte. Comme sur la page, poser le doigt sur la
courbe montre le point du tracé correspondant : un trait vertical, la distance
et l'altitude sous le doigt, et un disque bleu cerclé de blanc sur la carte.
Lever le doigt efface les deux.

Un double tap sur la carte, comme sur Locus Map, masque les deux bandeaux et
laisse la carte seule ; un second double tap les ramène. L'échelle et
l'attribution OSM restent visibles : elles font partie de la carte.

Le bouton rond du bas, à trois traits, ouvre le menu ; juste au-dessus, celui
de la position recentre la carte sur le GPS, avec le point bleu et son halo de
précision. Le démarrage d'une trace passe par « Enregistrer un parcours » :
pendant l'enregistrement, un bouton rond rouge apparaît au-dessus de la
position pour arrêter (carré) sans rouvrir le menu, et le GPX est rangé dans
`traces/`, avec l'heure et l'altitude de chaque point. Les réglages suivent
ceux de Locus : distance minimale entre deux points (10 m), durée minimale
(10 s) et déviation GPS maximale (100 m). Un point n'est retenu que si le GPS
est plus précis que la déviation, et si la distance et la durée depuis le point
précédent sont toutes deux atteintes ; le premier point n'a que la précision à
respecter. Un changement de réglage s'applique au point suivant, même pendant
un enregistrement. La localisation n'est demandée qu'au premier appui sur le
bouton de position ou au démarrage d'une trace, jamais au lancement. La trace
enregistrée s'affiche en orange, au-dessus de l'itinéraire bleu, et l'écran
reste allumé tant qu'elle tourne.

Pendant l'enregistrement, le bandeau donne la distance, la durée et le dénivelé
D+/D− calculé comme gpx2elev. Le calcul ne lit que le cache `gpx2elev/tiles` :
en randonnée, le téléphone n'a pas de réseau. Si le cache ne couvre pas encore
le parcours, le dénivelé reste absent du bandeau, sans arrêter la trace. À
l'export, le GPX est relu et les altitudes sont remplacées par celles de
gpx2elev : d'abord avec le cache, puis avec le réseau s'il est disponible et que
le cache est incomplet ; sans les deux, le fichier part tel qu'il a été
enregistré. La description du GPX porte alors « D+ … m / D− … m (gpx2elev) ».

« Ma bibliothèque », dans le menu, liste l'historique des traces : chaque
fichier de `traces/` affiche sa date et sa taille réelle, avec un bouton
« GPX » pour le réexporter et un bouton « Supprimer ». Les cases à cocher et
« Supprimer la sélection » effacent plusieurs traces d'un coup, après
confirmation. « Vider le cache » ne touche pas à cet historique.

Les lots du serveur se téléchargent d'eux-mêmes, comme sur le PC
(`application._lot_automatique`) : l'application lit les catalogues à son
lancement, et quand un parcours touche une case dont le lot manque, ou dont le
dépôt a une édition plus récente, ce lot part aussitôt. Afficher un calque du
lot au zoom 14 compte aussi comme un usage de la région : le lot de la case du
centre se télécharge de lui-même. Sur le Wi-Fi, sans rien demander ; sur un
réseau facturé (données mobiles), après confirmation. Un échec ou un refus
n'est pas repris avant une heure, et un lot supprimé à la main ne revient pas
de la séance. Les lots et les fonds installés affichent leur taille réelle
(« 254 kB » pour un petit lot d'essai, jamais un « 0 Mo » trompeur).

Le bouton « Fond », dans le bandeau de planification, choisit le fond de carte :
OpenStreetMap ou OpenTopoMap en
ligne, ou un fond hors ligne reçu d'un PC (le SCAN 25 ou le Plan IGN qu'il a
fabriqués, `hike2gpx/fonds.py`). Les fonds qu'un PC partage et qui manquent
au téléphone sont proposés dans la même liste, avec leur taille. Un fond est
un MBTiles rangé sous `hors-ligne/fonds/`, comme sur le PC ; tous ceux d'une
même source s'affichent ensemble, et osmdroid agrandit au-delà de leur zoom le
plus fin.

Les réglages réunissent le reste : mode strict et chemins officiels, lots et
fonds installés (mise à jour, suppression), sources, et « Vider le cache », qui
efface comme sur le PC les lots, les fonds, les téléchargements interrompus,
les tuiles en ligne gardées et les tuiles de relief gpx2elev ; les lots du
serveur reviennent d'eux-mêmes.

L'application parle anglais ou français selon la langue du téléphone, comme
watch2notif : l'anglais dans `res/values`, la langue par défaut, le français
dans `res/values-fr`. Les erreurs du code métier portent la ressource de leur
texte (`ErreurTexte`) et l'écran les traduit ; `tests/test_android.py` vérifie
que les deux langues ont les mêmes phrases et les mêmes arguments.

L'APK de débogage s'installe à côté de la version publiée, sous l'identifiant
`org.hike2gpx.android.debug` et le nom « hike2gpx (essai) » : sa clé diffère,
il ne pourrait pas la remplacer, et l'essayer n'efface rien.

## Mise à jour

L'application se met à jour depuis les releases GitHub, comme gpxelev et
blink2temp (`MiseAJour.kt`, d'après leur `ReleaseUpdates.kt`). Au lancement,
sans bruit, et à la demande dans les réglages (« Vérifier les mises à jour »),
elle lit `releases/latest` ; une version plus récente se propose. L'APK
`hike2gpx-android.apk` ne se télécharge que depuis GitHub en HTTPS, contrôlé
par sa taille et son SHA-256 (le champ `digest` de l'API, sinon le fichier
`.sha256` publié à côté), puis par son paquet, sa version et sa signature, qui
doit être celle de l'application installée. Il passe alors à l'installateur
d'Android par un `FileProvider` (`FournisseurMaj`, qui ne partage que
`cache/maj`). La première fois, Android demande d'autoriser hike2gpx à
installer des applications ; la mise à jour reprend au retour. Lots, fonds et
réglages sont gardés. L'APK d'essai ne se compare pas aux releases au
lancement : ce n'est pas le même paquet. Il a donc son propre stockage : les
lots et les fonds téléchargés dans l'application normale ne s'y voient pas, il
faut les y télécharger ou les recevoir d'un PC.

Le catalogue des lots (`catalog.json`) a le format de `hike2gpx/depot.py`.
Un lot se télécharge fichier par fichier ; une
coupure reprend là où elle s'est arrêtée (en-tête `Range`), et chaque fichier
est contrôlé par son SHA-256, puis tout le lot une seconde fois contre son
manifeste à l'installation, comme `HorsLigne.installer` sur le PC. Les
fichiers sont rangés comme sur le PC :

```text
hors-ligne/segments/E5_N40.rd5          RD5 des lots enrichis
hors-ligne/segments-osm/E5_N40.rd5      RD5 officielles des lots OSM
hors-ligne/E5_N40/manifest.json, franchissements.json.gz, calques.mbtiles
```

Les tuiles de relief vont dans `gpx2elev/tiles/`, à la racine des fichiers de
l'application, sous le même nom que sur le PC (`mapterhorn_12_x_y.webp`) : un
cache recopié d'un PC sert tel quel.

Le calcul suit la règle du PC : un parcours dont la zone tient dans un lot se
calcule sur ce lot seul. Les franchissements de la zone deviennent des coupes
`polylines` de BRouter (interdites ou pondérées, les interdites en dernier),
la zone s'élargit si le tracé en sort, et un dernier contrôle refuse un tracé
qui passerait encore une coupe interdite. Le tracé s'exporte en GPX.

BRouter 1.7.10 est un sous-module épinglé, compilé dans l'APK. Ses profils
(table de tags et `hike2gpx.brf`, standard et « maison ») sont dans
`app/src/main/assets/brouter`, écrits par `tools/profils_android.py` avec les
fonctions mêmes du PC ; `tests/test_android.py` vérifie qu'ils n'ont pas dérivé.

## Un PC pour les fonds de carte

Le PC affiche un QR code qui porte un lien
`hike2gpx://depot?url=<adresse du catalogue, encodée>&jeton=<jeton>`.
L'appareil photo du téléphone l'ouvre dans l'application (le lien est déclaré
dans le manifeste Android), qui demande confirmation avant d'ajouter le PC ; le
lien peut aussi se coller à la main. Toutes les requêtes vers ce PC portent
`Authorization: Bearer <jeton>`, et seulement vers l'origine de son catalogue.
Le HTTP simple n'est accepté que vers le réseau local.

Les lots se lisent sur GitHub seulement (décision du 2026-11-04) : le
catalogue du serveur, au lancement. Un PC ne sert au téléphone que ses fonds
de carte ; son catalogue ne se lit qu'à la demande, quand on ouvre « Fond » ou
qu'on ajoute le PC, si bien qu'un PC éteint ne retarde jamais le lancement.

## Construire

```text
git submodule update --init android/brouter
powershell -File android/build-local.ps1
```

Le script lance les tests unitaires (JVM) puis construit l'APK de débogage,
sous `android/app/build/outputs/apk/debug/`, avec le JDK et le SDK d'Android
Studio. Le workflow `.github/workflows/android.yml` fait de même à chaque
demande de fusion qui touche `android/` et garde l'APK en artefact.

Deux essais demandent des données hors du dépôt et ne tournent que si leur
variable d'environnement est définie : `HIKE2GPX_SEGMENTS_OSM` (un dossier qui
contient `E5_N40.rd5`) pour BRouter seul, et `HIKE2GPX_ESSAI_GITHUB` (un
dossier de travail) pour le parcours complet : catalogue GitHub, lot E5_N40
interrompu puis repris, installation, itinéraire.
