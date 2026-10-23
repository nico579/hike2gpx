*[English](README.md) | **Français***

# hike2gpx

hike2gpx trace un itinéraire de randonnée, partout dans le monde, sans
traverser les clôtures, barrières et interdictions que décrit OpenStreetMap.
Il calcule son dénivelé et sa durée, puis l'exporte en GPX. En France, il
peut emprunter en plus les chemins que seule l'IGN connaît.

Les planificateurs courants, Visorando, Locus Map, brouter-web, ne voient pas
une clôture dessinée en ligne qui coupe un sentier. Ce n'est pas un oubli de
leur part : leurs moteurs de calcul ne lisent que les étiquettes posées sur les
nœuds du chemin, et une clôture est une ligne à part. hike2gpx examine
d'avance le réseau de la zone, repère chaque croisement entre un chemin et une
barrière, le juge, puis interdit ou décourage son passage. À Garéoult (Var),
le profil Randonnée standard de BRouter franchit une clôture en béton pour un
trajet de 69 m ; hike2gpx la contourne par un détour de 435 m.

Pour ordinateur : Windows, macOS et Linux. Le téléphone viendra plus tard,
par l'application BRouter pour Android.

Installé depuis une release, hike2gpx se met à jour tout seul, comme les
autres applications de nico579 : quand une version plus récente est publiée,
un bandeau de la page et le menu de son icône proposent de l'installer ; il
la télécharge, la vérifie, puis redémarre dessus. Le bouton « Vérifier les
mises à jour » du panneau Réglages pose la question tout de suite, sans
attendre la vérification périodique. Lancé depuis les sources, hike2gpx se
contente d'ouvrir la page de la nouvelle version.

## Ce que fait hike2gpx

Tout se passe dans une page locale, ouverte dans le navigateur, et dans le
menu d'une icône de la zone de notification.

**La carte.** Elle suit le pays de son centre, y compris quand on la déplace
à la main, et propose les fonds de ce pays ; chaque pays garde son dernier
fond choisi.

- **Partout** : OpenStreetMap, OSM rando (OpenTopoMap), OSM vélo (CyclOSM),
  Thunderforest Outdoors avec une clé API, et une vue satellite (Esri).
  Un calque à cocher, à partir du zoom 14, montre les
  chemins d'OpenStreetMap (les sentiers en tirets), avec les clôtures et murs
  qu'il cartographie.
- **En France** : les fonds de l'IGN, SCAN 25 (avec une clé IGN, voir plus
  bas), Plan IGN, photos aériennes, et le relief du LiDAR HD là où l'IGN l'a
  publié. Un second calque montre les chemins de la BD TOPO de l'IGN ; mis à
  côté de celui d'OpenStreetMap, il montre d'un coup d'œil les sentiers qu'une
  source ignore.
- **Dans huit autres pays** : la carte nationale de l'Espagne, de la Suisse, de
  l'Allemagne (BKG TopPlusOpen), de l'Autriche, des Pays-Bas, du Luxembourg,
  de la Norvège et des États-Unis.
  L'Espagne, la Suisse et les États-Unis y ajoutent leurs sentiers officiels,
  pour l'affichage seulement. Le bouton ⓘ, à côté du choix des fonds, liste ces
  pays.

Une recherche de ville recentre la carte : les communes françaises par l'API
Géo de l'État, le reste du monde par Nominatim, le moteur de recherche
d'OpenStreetMap. Un bouton passe la carte en plein écran. Un voyant dit si le
tracé est possible tout de suite, grâce à un extrait OSM déjà installé ou à
Overpass.

**Le tracé.** Un clic pose le départ, puis les étapes et l'arrivée ; un point
se déplace en le faisant glisser et se retire depuis sa bulle. « Revenir »
referme la boucle sur le départ, « Retirer » ôte le dernier point, « Effacer »
repart de zéro. Le calcul est celui de BRouter, en local, avec les barrières
d'OpenStreetMap mises en travers des chemins (voir plus bas). Trois options le
règlent :

- **Mode strict** : éviter aussi les passages « à vérifier », pas seulement
  les bloquants ;
- **Chemins IGN** (en France) : laisser BRouter emprunter aussi les chemins de
  la BD TOPO absents d'OpenStreetMap. Ils s'affichent en tirets orange et
  rejoignent les points à vérifier, car rien ne garantit qu'ils existent encore
  ni qu'on y passe. Hors de France, la case est inactive et le calcul se fait
  sur OpenStreetMap ; en Espagne, en Suisse et aux États-Unis, elle nomme les
  sentiers officiels du pays et précise qu'ils ne servent qu'à l'affichage ;
- **Comparaison** : montrer en pointillé le tracé standard, celui qui ignore
  les barrières, avec sa longueur et les franchissements bloquants qu'il
  traverserait.

**Le résultat.** Un résumé donne la distance, la durée estimée (modèle de
Tobler, appliqué à la pente du profil), le dénivelé positif et négatif, le
point haut et le point bas. Le profil d'altitude se déplie en bas de la carte,
avec le nom du modèle de terrain qui a servi ; le survoler montre le point
correspondant sur l'itinéraire. Les franchissements à vérifier sont listés,
chacun avec un lien pour centrer la carte et un autre vers l'objet dans
OpenStreetMap. « Exporter le GPX » enregistre l'itinéraire, avec ces points en
points de passage.

« Charger un GPX » affiche un tracé existant (pistes et itinéraires GPX) en
jaune sur la carte et centre la vue dessus. Son nom, sans extension, apparaît
dans les couches : la coche masque ou réaffiche le tracé sans le supprimer, et
la légende montre son trait jaune tant qu'il est chargé. Il sert de repère
pendant la préparation du parcours : il ne modifie pas les points de passage
ni l'export. Le bouton devient « Supprimer le GPX » après le chargement et
retire ce tracé de la carte sans toucher au fichier sur l'ordinateur. Le tracé
chargé reste affiché jusqu'à la fermeture ou au rechargement de la page.

**Les réglages.** Les clés de carte IGN pour le SCAN 25 et Thunderforest pour
Outdoors, le délai de renouvellement des
données téléchargées (30 jours par défaut), la transparence des bandeaux et
leur masquage, et un bouton qui vide tous les caches locaux. Un bouton ouvre
le dossier `logs`, qui contient les journaux de l'application et de BRouter ;
un autre affiche la version installée et vérifie s'il en existe une plus
récente. La page parle français ou anglais, et retrouve à sa réouverture la
vue, le fond, les calques et les options de la fois précédente.
Téléchargements, imports et calculs en cours s'affichent dans un bandeau en
bas de la carte.

## Comment ça marche

Le calcul passe par cinq pièces.

1. **Les franchissements.** Pour la zone du tracé, hike2gpx lit dans
   OpenStreetMap (dans un extrait installé, ou par Overpass, en tuiles de 0,05°
   gardées sept jours) les chemins praticables à pied, les barrières dessinées
   en ligne, les nœuds barrière et les itinéraires de randonnée balisés. Chaque
   croisement est jugé **bloquant**, **à vérifier** ou **franchissable**, avec
   les règles de [gpx2elev](https://github.com/nico579/gpx2elev), recopiées
   telles quelles dans `regles.py` : une clôture traversée sans ouverture
   cartographiée bloque, un portail sans indication d'accès est à vérifier,
   `foot=yes` prime sur `access=private`, des horaires ou des conditions
   laissent un doute.
2. **Le moteur.** [BRouter](https://github.com/abrensch/brouter), celui
   qu'utilise Locus, calcule l'itinéraire en local. Chaque franchissement lui
   arrive comme une petite ligne d'un mètre posée en travers du chemin : sans
   poids, elle retire le tronçon du calcul ; avec un poids, elle le rend
   coûteux, de sorte qu'un détour de moins de 300 m environ l'évite. Le profil
   est celui de la randonnée de BRouter, corrigé pour qu'une interdiction
   piétonne (`foot=no` ou `foot=private`) soit respectée même là où un vélo
   passerait ou qu'un trottoir est indiqué. Quand deux coupes tombent sur le
   même tronçon, l'interdite l'emporte toujours sur la pondérée ; et si le
   tracé rendu par BRouter passait malgré tout une coupe interdite, hike2gpx le
   refuserait au lieu de l'afficher.
3. **La page.** Une page locale, servie par la bibliothèque commune
   [nico579-commons](https://pypi.org/project/nico579-commons/), qui partage
   avec les autres applications de nico579 l'icône, la langue et la mise à
   jour. Chaque calcul laisse sa trace dans le journal de la session
   (`logs/hike2gpx-<date>.log`, dans le dossier de données ; les dix dernières
   sessions sont gardées), avec le temps de chaque étape, ses erreurs et ses
   lenteurs.
4. **Le dénivelé.** Une fois l'itinéraire affiché, le moteur de
   [gpx2elev](https://pypi.org/project/gpx2elev/) recalcule son dénivelé :
   tracé échantillonné tous les 5 m, lissage gaussien de 20 m, hystérésis de
   2 m. Il prend le meilleur modèle de terrain qui couvre tout le parcours :
   l'IGN LiDAR HD en France, sinon Mapterhorn, FABDEM, Copernicus GLO-30 ou
   SRTM. Le chiffre de BRouter, tiré d'un modèle mondial plus grossier, ne sert
   que d'estimation en attendant ; si aucun modèle ne couvre le parcours, le
   dénivelé est dit indisponible plutôt que remplacé par ce chiffre.
5. **Les chemins IGN, en France.** Un sentier que la BD TOPO connaît et
   qu'OpenStreetMap ignore n'existe pas pour BRouter, qui ne voit que ses
   tuiles. hike2gpx fabrique donc sa propre tuile BRouter à partir des données
   déjà lues : les voies d'OpenStreetMap, plus les tronçons de la BD TOPO qui
   n'en doublent aucune, raccordés au réseau. La tuile grossit au fil des zones
   consultées, jusqu'à 25 tuiles de 0,05° avant de repartir de la zone
   demandée, et ne se refait que pour une zone nouvelle ou des données relues,
   en six secondes environ pour neuf tuiles. Les franchissements se cherchent
   alors sur le réseau fusionné : un sentier OSM et un chemin IGN arrêtés de
   part et d'autre d'une clôture, une fois raccordés, la traversent. Ces
   chemins coûtent un peu plus que les autres, s'affichent en tirets orange
   sur l'itinéraire et rejoignent les points à vérifier, car rien ne dit
   qu'ils existent encore ni qu'on y passe ; un accès piéton restreint dans la
   BD TOPO les ferme. Une case permet de s'en passer, et si la fabrication
   échoue, le calcul se fait sur OpenStreetMap seul, avec un avertissement.
   Le gain est réel : sur les tuiles les plus riches en sentiers, la BD TOPO
   agrandit le réseau de 18 à 100 %, et de 21 à 72 % dans le Var. Hors de
   France, les sources officielles mesurées (États-Unis, Suisse, Pays-Bas)
   n'ajoutent que 0 à 12 % : le calcul y reste sur OSM seul. Mesure et analyse
   dans [RAPPORT_SOURCES_CHEMINS_BROUTER.md](RAPPORT_SOURCES_CHEMINS_BROUTER.md).

Ce que hike2gpx ajoute aux règles de gpx2elev, parce qu'il examine un réseau
entier et non une seule trace :

- une barrière qui s'arrête sur un chemin, ou qui le touche et repart du même
  côté, ne le traverse pas ; un chemin sur un pont ou dans un tunnel non plus ;
- une barrière qui se termine à moins de 2 m du chemin se contourne ;
- un portail posé sur la clôture tout près du chemin, sans être porté par lui,
  est jugé comme s'il l'était : verrouillé ou privé, il ne rend pas la clôture
  franchissable ;
- deux niveaux différents (`layer`) rendent le franchissement « à vérifier » ;
- un sentier balisé passe forcément quelque part : une barrière qui le
  bloquerait y devient « à vérifier ».

Si OpenStreetMap ne répond pas, le calcul s'arrête : une barrière inconnue ne
prouve jamais qu'un passage est libre. Et s'il n'existe aucun itinéraire, la
page le dit, sans relier les points en ligne droite.

### Données OSM hors ligne

Overpass, le service qui répond aux questions sur OpenStreetMap, sature par
moments et tombe parfois. Pour ne plus en dépendre, hike2gpx télécharge de
lui-même un extrait d'OpenStreetMap autour de l'endroit où l'on travaille.

Partout dans le monde, c'est le plus petit extrait de
[Geofabrik](https://download.geofabrik.de/) qui contient toute la zone, parmi
quelque 550 : le Liechtenstein à Vaduz (3 Mo), un État américain comme
l'Utah plutôt que les États-Unis entiers. En France, hike2gpx procède en deux
temps. D'abord le département, tiré des [extraits
d'OSM France](https://download.openstreetmap.fr/extracts/europe/france/) : à
Garéoult, le Var pèse 83 Mo et se trouve prêt en une quarantaine de secondes,
import compris ; on travaille aussitôt. Pendant ce temps, la région de
Geofabrik se prépare : la PACA pèse 391 Mo et demande plus de trois minutes.
Dès qu'elle est là, c'est elle qui sert, car OSM France coupe net les chemins à
la limite du département, là où Geofabrik les garde entiers.

Le téléchargement part dès que la région sert vraiment, par un calcul ou le
calque des chemins OSM, mais pas quand la carte ne fait que la survoler ; il
s'arrête si la carte quitte la région. Il se fait en tâche de fond, vérifié
par son MD5, pendant qu'Overpass continue de servir ; le panneau en suit
l'avancement, et un calcul qui l'attendait reprend de lui-même dès que
l'extrait est là. Un extrait de plus de 2 Go, ou que le disque ne pourrait pas
loger, n'est pas téléchargé : Overpass reste alors la source. L'extrait est lu
une fois et rangé dans une base SQLite par tuile, au dossier de données
(`geofabrik/`), puis le fichier téléchargé est effacé.

Une fois installé, l'extrait est la source des tuiles qu'il contient :
lecture instantanée, sans quota ni panne, hors connexion comprise. Une tuile en
sort sous la forme exacte d'une réponse d'Overpass, si bien que les
franchissements se jugent de la même façon. Overpass ne sert plus qu'ailleurs :
hors des extraits installés, ou sur une tuile à cheval sur leur limite ; et
une tuile qui attendait Overpass au moment où un extrait s'installe bascule
aussitôt sur lui. OSM France et Geofabrik refont leurs extraits chaque jour ;
plus vieux que le délai choisi dans les réglages (30 jours par défaut, de 1 à
365), l'extrait se renouvelle de lui-même en tâche de fond, l'ancien servant
jusqu'à la bascule. Les tuiles BRouter suivent le même délai.

## Limites

hike2gpx ne peut éviter que ce qui est cartographié. Autour de Garéoult, sur
250 km², OpenStreetMap ne recense que 18 clôtures, et la BD TOPO de l'IGN
aucune (voir [ESSAI.md](ESSAI.md)). Une clôture rencontrée sur le terrain et
ajoutée à OpenStreetMap est respectée par hike2gpx dès que son cache de la
zone se renouvelle ; les moteurs des autres planificateurs, eux, continuent de
l'ignorer.

Hors de France, le calcul ne connaît que les chemins d'OpenStreetMap : un
sentier absent d'OSM n'existe pas pour lui, même si la carte nationale le
dessine.

Un calcul examine au plus 100 tuiles de 0,05°, soit environ 55 × 40 km : la
première lecture d'une zone plus grande prendrait des dizaines de minutes. Un
long parcours se découpe en étapes.

## Installation

Le plus simple : télécharger le programme de son système dans les
[releases](https://github.com/nico579/hike2gpx/releases) (Windows, Linux,
macOS), le décompresser, par exemple sous Windows dans
`%LOCALAPPDATA%\Programs\hike2gpx`, et lancer `hike2gpx`. Il embarque son
Java et se met à jour tout seul ; « Créer un raccourci sur le Bureau », dans
le menu de son icône, pose le raccourci.

Depuis les sources, il faut Python 3.12, [uv](https://docs.astral.sh/uv/) et
Java 11 ou plus pour BRouter.

```
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -e ".[test]"
.venv\Scripts\hike2gpx installer E5_N40
.venv\Scripts\hike2gpx serve
```

`installer` télécharge BRouter 1.7.10 (archive vérifiée par son empreinte
SHA256) et une tuile de données, ici E5_N40, qui couvre la Provence, de 5° à
10° E et de 40° à 45° N. Depuis la page, rien à faire : le moteur s'installe
de lui-même au premier lancement, et chaque tuile de données se télécharge en
tâche de fond dès qu'un calcul en a besoin, n'importe où dans le monde, le
calcul reprenant à son arrivée. Les données vont dans le dossier d'état
standard (`%LOCALAPPDATA%\hike2gpx-data` sous Windows), ou dans celui que
désigne la variable `HIKE2GPX_HOME`.

Le SCAN 25 n'est pas une donnée libre : il demande une clé IGN, à saisir dans
les réglages de la page. Sans clé, la carte utilise le Plan IGN, sous Licence
Ouverte. Thunderforest Outdoors demande également une clé, à obtenir sur
[thunderforest.com](https://www.thunderforest.com/pricing/) puis à saisir dans
les mêmes réglages. Les clés restent dans les préférences locales de
l'application et les anciennes clés IGN y sont reprises automatiquement.
TopPlusOpen et les autres fonds ne demandent aucune clé.

## Tests

```
.venv\Scripts\python.exe -m pytest
```

Les tests unitaires tournent sans réseau ni BRouter. `test_regles.py` compare
`regles.py` à sa source dans gpx2elev quand ce dépôt est présent sur la
machine. `test_integration.py` rejoue un cas réel de Garéoult avec le vrai
BRouter : il est sauté tant que BRouter et sa tuile E5_N40 manquent dans le
dossier de données, et tourne en quelques secondes avec
`$env:HIKE2GPX_HOME = 'D:\hike2gpx'`. `test_integration_maison.py` fabrique
une tuile maison avec le vrai créateur de tuiles, sur un petit réseau inventé
où deux sentiers OSM ne se rejoignent que par des chemins IGN ; il demande en
plus les profils de création de BRouter, que la première fabrication depuis
la page télécharge dans le dossier de données. `test_integration_securite.py`
vérifie de la même façon, sur six cas inventés, que le profil et l'ordre des
coupes respectent les interdictions. `test_page.py` fait tourner la page sous
Node, quand Node est installé ; il vérifie aussi que chaque pays de
`providers/` a ses libellés en français et en anglais. Les outils de `tools/`
rejouent l'essai décrit dans [ESSAI.md](ESSAI.md) et la mesure des sources de
chemins.

## Construire le programme

```
python build.py --archive
```

`build.py` crée un environnement isolé, l'emplit du verrou
`requirements-build.txt` (versions et empreintes exactes, PyInstaller
compris), télécharge le JRE Temurin 21 de ce système en vérifiant l'empreinte
que publie Adoptium, construit le programme avec `hike2gpx.spec`, puis lance
son auto-test (`--self-test-version`) : Java embarqué, pyosmium, rasterio,
page. Avec `--archive`, il emballe l'archive publiée et son `.sha256`, sous le
nom qu'attend la mise à jour automatique du commun. Le programme figé n'emploie
que son Java ; depuis les sources, hike2gpx prend celui du système. Sur
GitHub, `release.yml` fait la même chose sur les quatre systèmes à chaque tag,
et sur chaque pull request qui touche au programme. Sous macOS, il faut
macOS 15 ou plus, comme pour les roues de rasterio.

Les verrous se régénèrent avec uv :

```
uv pip compile pyproject.toml --universal --python-version 3.12 --generate-hashes -o requirements.txt
uv pip compile requirements-build.in --universal --python-version 3.12 --generate-hashes -o requirements-build.txt
```

## Licence

GPL-3.0-or-later. BRouter (MIT) est téléchargé à l'installation ; Leaflet 1.9.4
(BSD-2-Clause) est fourni dans `hike2gpx/assets/web/leaflet`. Le programme
publié embarque le JRE Temurin 21 d'Eclipse Adoptium (GPL-2.0 avec exception
Classpath, textes dans `_internal/jre/legal`). Données ©
contributeurs OpenStreetMap (ODbL), y compris l'extrait de test
`tests/donnees/gareoult_cloture.json` ; BD TOPO © IGN (Licence Ouverte) ;
cartes © IGN, et pour les fonds nationaux, © de chaque organisme, indiqué sur
la carte.
