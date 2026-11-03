# Application Android

Le téléphone ne fabrique rien : il prend les lots hors ligne que le serveur
publie sur GitHub (le dépôt nico579/hike2gpx-bundles), ou ceux d'un PC du
réseau local, et calcule l'itinéraire lui-même avec BRouter, sans réseau.

## Ce qu'elle fait

L'application lit le catalogue des lots (`catalog.json`, le format de
`hike2gpx/depot.py`) et affiche les cases disponibles avec leur taille et
l'édition de leurs sources. Un lot se télécharge fichier par fichier ; une
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
