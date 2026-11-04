# Application Android

Le téléphone ne fabrique rien : il prend les lots hors ligne que le serveur
publie sur GitHub (le dépôt nico579/hike2gpx-bundles), ou ceux d'un PC du
réseau local, et calcule l'itinéraire lui-même avec BRouter, sans réseau.

## Ce qu'elle fait

L'écran est celui de la page du PC : la carte d'abord, en plein écran. On
touche la carte pour poser le départ, puis l'arrivée et d'éventuelles étapes ;
« Retour » retire le dernier point, « Effacer » les retire tous. Dès qu'il y a
deux points, l'itinéraire se calcule hors ligne et s'affiche ; « GPX »
l'exporte.

Les lots du serveur se téléchargent d'eux-mêmes, comme sur le PC
(`application._lot_automatique`) : l'application lit les catalogues à son
lancement, et quand un parcours touche une case dont le lot manque, ou dont le
dépôt a une édition plus récente, ce lot part aussitôt. Sur le Wi-Fi, sans
rien demander ; sur un réseau facturé (données mobiles), après confirmation.
Un échec ou un refus n'est pas repris avant une heure, et un lot supprimé à la
main ne revient pas de la séance.

Le bouton « Fond » choisit le fond de carte : OpenStreetMap ou OpenTopoMap en
ligne, ou un fond hors ligne reçu d'un PC (le SCAN 25 ou le Plan IGN qu'il a
fabriqués, `hike2gpx/fonds.py`). Les fonds qu'un PC partage et qui manquent
au téléphone sont proposés dans la même liste, avec leur taille. Un fond est
un MBTiles rangé sous `hors-ligne/fonds/`, comme sur le PC ; tous ceux d'une
même source s'affichent ensemble, et osmdroid agrandit au-delà de leur zoom le
plus fin.

Les réglages réunissent le reste : mode strict et chemins officiels, lots et
fonds installés (mise à jour, suppression), sources, et « Vider le cache », qui
efface comme sur le PC les lots, les fonds, les téléchargements interrompus et
les tuiles en ligne gardées ; les lots du serveur reviennent d'eux-mêmes.

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
lancement : ce n'est pas le même paquet.

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

Le calcul suit la règle du PC : un parcours dont la zone tient dans un lot se
calcule sur ce lot seul. Les franchissements de la zone deviennent des coupes
`polylines` de BRouter (interdites ou pondérées, les interdites en dernier),
la zone s'élargit si le tracé en sort, et un dernier contrôle refuse un tracé
qui passerait encore une coupe interdite. Le tracé s'exporte en GPX.

BRouter 1.7.10 est un sous-module épinglé, compilé dans l'APK. Ses profils
(table de tags et `hike2gpx.brf`, standard et « maison ») sont dans
`app/src/main/assets/brouter`, écrits par `tools/profils_android.py` avec les
fonctions mêmes du PC ; `tests/test_android.py` vérifie qu'ils n'ont pas dérivé.

## Un PC comme seconde source

Le PC affiche un QR code qui porte un lien
`hike2gpx://depot?url=<adresse du catalogue, encodée>&jeton=<jeton>`.
L'appareil photo du téléphone l'ouvre dans l'application (le lien est déclaré
dans le manifeste Android), qui demande confirmation avant d'ajouter le PC ; le
lien peut aussi se coller à la main. Toutes les requêtes vers ce PC portent
`Authorization: Bearer <jeton>`, et seulement vers l'origine de son catalogue.
Le HTTP simple n'est accepté que vers le réseau local.

GitHub reste la source par défaut. Pour chaque case, l'application propose le
lot dont l'extrait OSM (`sources.osm`) est le plus récent ; à égalité, GitHub.

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
