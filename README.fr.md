*[English](README.md) | **Français***

# hike2gpx

hike2gpx planifie des randonnées et exporte l'itinéraire en GPX. Il existe en
deux versions qui se complètent : une application pour ordinateur (Windows,
macOS, Linux) et une application Android. L'ordinateur prépare ce que le
téléphone emporte : il fabrique des fonds de carte et des zones de routage,
puis les partage en Wi-Fi par QR code. Le téléphone calcule alors ses
itinéraires hors ligne, en pleine randonnée, sans réseau.

Trois choses le distinguent des planificateurs courants (Visorando, Locus Map,
brouter-web).

**Il respecte les clôtures, les barrières et les portails que décrit
OpenStreetMap.** Ces planificateurs ne les voient pas : leurs moteurs de calcul
ne lisent que les étiquettes posées sur les nœuds du chemin, et une clôture est
une ligne à part. hike2gpx examine d'avance le réseau de la zone, repère chaque
croisement entre un chemin et une barrière, le juge, puis interdit ou décourage
son passage. [Un exemple à Garéoult](#les-clôtures-et-les-barrières).

**Il combine OpenStreetMap et les cartes nationales.** Un sentier que l'IGN
connaît et qu'OpenStreetMap ignore n'existe pas pour un moteur qui ne lit que
ce dernier. hike2gpx y ajoute la BD TOPO de l'IGN (France), l'ATKIS
(Allemagne), le swissTLM3D (Suisse), le ZABAGED (Tchéquie) et le BDOT10k
(Pologne, Basse-Silésie seulement). Ce ne sont pas tous les pays, à dessein :
on ne retient que ceux où la carte nationale apporte une part sensible de
chemins nouveaux. [Les chiffres pays par pays](#les-cartes-nationales).

**Il calcule le dénivelé sur le terrain, pas sur la cime des arbres.** Sous une
forêt, un modèle de surface comme SRTM ou Copernicus, tirés d'un radar, mesure
plutôt le haut de la canopée, et fausse les pentes. Le LiDAR, lui, envoie des
impulsions laser dont certaines traversent le feuillage jusqu'au sol : on en
tire un vrai modèle numérique de terrain (MNT), le sol nu. hike2gpx prend le
meilleur modèle de terrain qui couvre tout le parcours : en France le LiDAR HD
de l'IGN ; ailleurs Mapterhorn, qui reprend le LiDAR national dès qu'il en
existe un. [Les sources et leur précision](#le-relief).

![La page de l'ordinateur : un parcours tracé à Garéoult, son relief et sa légende](docs/images/pc-tracer.png)

## Mode d'emploi

### Installer et relancer

**Sur l'ordinateur**, téléchargez l'archive de votre système dans les
[releases](https://github.com/nico579/hike2gpx/releases), décompressez-la et
lancez `hike2gpx` : la page s'ouvre dans le navigateur. Au tout premier
lancement, hike2gpx pose une icône sur le Bureau ; c'est elle qui le relance
ensuite, après un redémarrage de l'ordinateur par exemple.

Tant qu'il tourne, hike2gpx vit dans la zone de notification (près de
l'horloge sous Windows, dans la barre des menus sous macOS). Fermer l'onglet du
navigateur ne l'arrête pas : un double-clic sur son icône rouvre la page. Son
menu propose « Ouvrir », « Mettre à jour vers x.y » quand une version plus
récente existe, « Redémarrer », « Arrêter », et « Créer un raccourci sur le
Bureau » pour remettre l'icône si vous l'avez effacée. Il se met à jour tout
seul ([détail](#installation)).

**Sur le téléphone**, installez `hike2gpx-android.apk`, à prendre dans les
mêmes releases (Android demande d'autoriser l'installation depuis cette
source). L'application se relance comme toutes les autres, par son icône.

### Sur l'ordinateur

**Tracer un parcours.** Ouvrez le menu (le bouton à trois traits, en bas à
gauche) puis « Planifier un itinéraire ». Chaque clic sur la carte pose un
point : le départ, les étapes, l'arrivée. L'itinéraire se calcule aussitôt,
avec sa distance, sa durée et son relief ; un point se déplace en le faisant
glisser. « Revenir » referme la boucle sur le départ, « Exporter le GPX »
l'enregistre. [Tout sur le tracé](#ce-que-fait-hike2gpx).

**Télécharger une zone de carte.** Dans « Gestion des cartes », choisissez le
fond à emporter (SCAN 25, Plan IGN, OpenStreetMap…), puis cliquez sur la carte
les cases de 1° voulues et « Télécharger ». Les zones de routage, elles, se
prennent dans « Gestion des itinéraires », par cases de 5° ; dans les cinq pays à carte nationale, elles
viennent toutes faites du serveur. [Le détail des fonds et des
lots](#lots-hors-ligne).

![Gestion des cartes : la case du Var sélectionnée, prête à télécharger](docs/images/pc-zone-carte.png)

**La partager sur le téléphone.** Sélectionnez les cases déjà présentes sur
l'ordinateur (en vert) et cliquez « Partager » : un QR code s'affiche. Le
téléphone doit être sur le même Wi-Fi. « Arrêter le partage » le referme, et
le code change à chaque ouverture. [Comment le partage est
protégé](#partager-au-téléphone).

![Le QR code du partage, à scanner avec le téléphone](docs/images/pc-partager.png)

### Sur le téléphone

<img src="docs/images/telephone-recuperer.png" alt="Le téléphone propose de récupérer les zones partagées par le PC" width="260" align="right">

**Récupérer la carte.** Dans « Gestion des cartes », touchez « Scanner le QR
code de l'ordinateur » et visez le QR code du PC. Le téléphone dit ce qu'il
lui manque et sa taille, puis télécharge les fonds et les zones de routage,
chaque fichier vérifié à l'arrivée. Les zones publiées par le serveur
(France, Suisse, Allemagne, Tchéquie, Pologne) se téléchargent aussi d'elles-mêmes, sans PC.

**Tracer un parcours.** Menu, puis « Planifier un itinéraire » : chaque
toucher sur la carte pose un point, comme sur l'ordinateur, et le calcul se
fait sur le téléphone, sans réseau dès que la zone est installée. Le bandeau
du relief se replie d'un toucher sur son titre ; un toucher sur un
franchissement en ouvre la fiche. [Tout sur
l'application Android](android/README.md).

<img src="docs/images/telephone-tracer.png" alt="Un parcours tracé sur le téléphone, avec son relief" width="260">

<br clear="right">

## Pourquoi hike2gpx, en détail

### Les clôtures et les barrières

À Garéoult (Var), le profil Randonnée standard de BRouter franchit une clôture
en béton pour un trajet de 69 m ; hike2gpx la contourne par un détour de 435 m.
L'option « Comparer avec le tracé standard (qui ignore les barrières) » de la page superpose ce
tracé standard, pour comparer. La méthode est décrite plus bas, dans
[Comment ça marche](#comment-ça-marche).

### Les cartes nationales

Sur les zones étudiées, la BD TOPO ajoute de 18 % à 100 % de longueur de
chemins candidats, l'ATKIS de 12 % à 127 %, le ZABAGED de 40 % à 66 %, alors
que les États-Unis et les Pays-Bas restent entre 0 % et 12 %. Ces pourcentages
mesurent des longueurs possibles, pas un gain garanti : la méthode et les
réserves sont dans
[RAPPORT_SOURCES_CHEMINS_BROUTER.md](RAPPORT_SOURCES_CHEMINS_BROUTER.md).

### Le relief

Mapterhorn rassemble environ deux cents modèles nationaux et régionaux, de
0,25 m à 10 m de résolution, pour presque toute l'Europe, les États-Unis, le
Canada, le Japon, l'Australie et la Nouvelle-Zélande. Hors de ces zones,
hike2gpx retombe sur le modèle mondial de 30 m de Copernicus, moins précis, et
SRTM reste le tout dernier recours. Le détail pays par pays se lit dans le
[catalogue des fournisseurs](https://github.com/nico579/lidar2map/blob/main/docs/providers.md)
de lidar2map, le projet jumeau, qui interroge directement ces sources LiDAR
nationales, que Mapterhorn rassemble aussi. Comparé au LiDAR natif, Mapterhorn
s'en écarte de 1,6 à 3 cm (RMSE) face au MNT du LiDAR HD de l'IGN sur trois
zones françaises, et de 10 cm face au DGM1 sur un site saxon : négligeable pour
un dénivelé, que le lissage sur 20 m moyenne de toute façon. Ces mesures, avec
leurs limites, sont dans
[l'évaluation de lidar2map](https://github.com/nico579/lidar2map/blob/main/docs/mapterhorn-evaluation.fr.md).

Le relief sert aussi au calcul de l'itinéraire, qui pénalise les pentes. Dans
les zones de routage que hike2gpx fabrique (les cinq pays à carte nationale),
BRouter lit le relief Mapterhorn, rééchantillonné à une seconde d'arc
(environ 30 m) ; ailleurs, il garde celui de ses propres tuiles, tiré de SRTM.

## Ce que fait hike2gpx

Tout se passe dans une page locale, ouverte dans le navigateur, et dans le
menu d'une icône de la zone de notification. La page est celle de
l'application Android : la carte d'abord, en plein écran, et un bouton à trois
traits, en bas à gauche, qui ouvre le menu : « Recherche », « Gestion des
cartes », « Gestion des itinéraires », « Planifier un itinéraire »,
« Réglages » et « Aide ». Chaque entrée ouvre sa page dans un panneau à
gauche, que sa croix referme pour rendre la carte seule (une poignée sur son bord
droit en change la largeur, et la page la retient) ; le menu porte aussi
le choix FR/EN et le voyant du calcul. « Aide » ouvre ce mode d'emploi dans la
langue de la page, pour la version installée.

**La carte.** Elle suit le pays de son centre, y compris quand on la déplace
à la main, et propose les fonds de ce pays ; chaque pays garde son dernier
fond choisi.

- **Partout** : OpenStreetMap, OSM rando (OpenTopoMap) et une vue satellite
  (Esri). Un calque à cocher, à partir du zoom 14, montre les
  chemins d'OpenStreetMap (les sentiers en tirets), avec les clôtures, murs et
  franchissements bloquants ou à vérifier qu'il cartographie. Ces obstacles
  restent visibles même sans itinéraire tracé. Un repère jaune signale aussi
  un chemin non raccordé : il s'arrête à moins de 15 m d'un autre sans le
  toucher dans OpenStreetMap, si bien que le calcul ne passe pas de l'un à
  l'autre ; sa bulle donne la distance et ouvre l'éditeur d'OpenStreetMap.
- **En France** : les fonds de l'IGN, SCAN 25 (avec une clé IGN, voir plus
  bas), Plan IGN, photos aériennes, et le relief du LiDAR HD là où l'IGN l'a
  publié. Un second calque montre les chemins de la BD TOPO de l'IGN ; mis à
  côté de celui d'OpenStreetMap, il montre d'un coup d'œil les sentiers qu'une
  source ignore.
- **Dans dix autres pays** : la carte nationale de l'Espagne, de la Suisse, de
  l'Allemagne (BKG TopPlusOpen), de l'Autriche, des Pays-Bas, du Luxembourg,
  de la Norvège, de la Pologne (Geoportal), de la Tchéquie et des États-Unis.
  Le lien ⓘ, à côté du choix des fonds, ouvre sur GitHub le
  [tableau des pays pris en charge](RAPPORT_SOURCES_CHEMINS_BROUTER.md#pays-pris-en-charge).
  Ses colonnes « fond », « chemins » et « itinéraire » sont générées depuis
  les fichiers providers avec `node tools/generer_couverture_pays.cjs`.

Les fichiers `hike2gpx/assets/web/providers/<pays>.js` regroupent les fonds,
les calques, leurs styles et leurs libellés. Les sources de chemins utilisées
par BRouter ont en plus un lecteur dans `hike2gpx/providers/` (BD TOPO, ATKIS,
ZABAGED, swissTLM3D ou BDOT10k). Le registre de ce dossier relie les pays aux
sources ; la lecture par zone et l'affichage suivent ensuite le même mécanisme.

Le fond et les calques se choisissent dans « Gestion des cartes » ; la légende
s'affiche en haut à droite de la carte, et « Afficher la légende », dans les
réglages, la cache. « Recherche » déplie en haut de la carte un champ qui la recentre sur
une ville : les communes françaises par l'API Géo de l'État, le reste du monde
par Nominatim, le moteur de recherche d'OpenStreetMap. Un bouton passe la
carte en plein écran. Dans le menu, un voyant indique
si le prochain calcul dispose du moteur et des tuiles BRouter ainsi que des
données OSM de la zone (extrait, cache ou Overpass). Son « i » jaune détaille
l'état d'Overpass et des extraits OSM local et régional, par exemple le Var
et la PACA.
Un clic droit sur la carte affiche les coordonnées GPS du point choisi et
permet de les copier.

**Le tracé.** Comme sur le téléphone, on trace dans « Planifier un
itinéraire » : tant que cette page est ouverte, le curseur est une croix et un
clic pose le départ, puis les étapes et l'arrivée ; ailleurs, un clic ne pose
rien. Un point se déplace en le faisant glisser et se retire depuis sa bulle.
Fermer la page laisse les points et le tracé en place. « Revenir » referme la
boucle sur le départ, « Retirer » ôte le dernier point, « Effacer » repart de
zéro. Le calcul est celui de BRouter, en local, avec les barrières
d'OpenStreetMap mises en travers des chemins (voir plus bas). Trois options,
dans « Gestion des itinéraires », le règlent :

- **Inclure les blocages à vérifier** : éviter aussi les passages « à vérifier », pas seulement
  les bloquants ;
- **Inclure les chemins IGN** (ATKIS en Allemagne…) : laisser BRouter
  emprunter aussi les chemins BD TOPO ou ATKIS absents d'OpenStreetMap. Ils
  s'affichent en tirets orange et rejoignent les points à vérifier, car rien
  ne garantit qu'ils existent encore ni qu'on y passe. En Espagne
  et aux États-Unis, la case nomme les sentiers officiels du pays et précise
  qu'ils ne servent qu'à l'affichage ;
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

**Les réglages.** La clé IGN du SCAN 25, le délai de renouvellement des
données téléchargées (30 jours par défaut), la transparence des bandeaux et un
bouton qui vide tous les caches locaux. Ils
s'enregistrent à la fermeture du panneau, sans bouton. Un bouton ouvre
le dossier `logs`, qui contient les journaux de l'application et de BRouter ;
un autre affiche la version installée et vérifie s'il en existe une plus
récente. La page parle français ou anglais, et retrouve à sa réouverture la
vue, le fond, les calques et les options de la fois précédente.
Téléchargements, imports et calculs en cours s'affichent dans un bandeau en
bas de la carte.

## Comment ça marche

Un itinéraire hike2gpx tient en quatre pièces : un moteur de calcul éprouvé,
BRouter ; des tuiles que hike2gpx fabrique pour lui ; des coupes posées en
travers des chemins à chaque calcul, là où une barrière gêne ; et un dénivelé
recalculé sur un vrai modèle de terrain. Les tuiles se fabriquent à l'avance,
sur un serveur GitHub pour les pays à carte nationale, sur votre PC ailleurs.

### Le moteur : BRouter

[BRouter](https://github.com/abrensch/brouter), celui qu'utilise Locus Map,
calcule l'itinéraire en local, sur l'ordinateur comme sur le téléphone, qui
l'embarque. hike2gpx ne le modifie pas. Il lit des tuiles de 5° sur 5°, les
RD5, qui contiennent le réseau des chemins et le relief. Le profil est celui de
la randonnée de BRouter (« hiking-mountain », celui de brouter-web), corrigé
sur un point : une interdiction piétonne (`foot=no` ou `foot=private`) est
respectée même là où un vélo passerait ou qu'un trottoir est indiqué.

### Des tuiles BRouter fabriquées par hike2gpx

Le site de BRouter publie chaque nuit des RD5 tirées d'OpenStreetMap seul. Là où
une carte nationale apporte des chemins, hike2gpx compile les siennes, avec le
créateur de tuiles de BRouter lui-même, à partir de trois ingrédients.

1. **OpenStreetMap**, lu dans l'extrait [Geofabrik](https://download.geofabrik.de/)
   de la région, voies entières.
2. **Les chemins de la carte nationale** (BD TOPO, ATKIS, swissTLM3D, ZABAGED,
   BDOT10k), mais seulement ceux qui ne doublent aucune voie d'OpenStreetMap,
   raccordés au réseau par des nœuds insérés dans les voies voisines. Une case
   de 5° ne tient pas en mémoire d'un bloc : la fusion se fait par mailles de
   0,25°, chacune lue avec une couronne autour, et un registre commun garde
   d'une maille à l'autre les mêmes nœuds aux mêmes endroits. Ces chemins
   portent une marque que le profil rend une fois et demie plus coûteux qu'un
   chemin OSM équivalent : rien ne dit qu'ils existent encore ni qu'on y passe.
   La case « Inclure les chemins IGN » de la page les interdit sans changer de
   tuile. Un accès piéton restreint dans la BD TOPO les ferme.
3. **Le relief**, celui de [Mapterhorn](https://mapterhorn.com) : le sol nu tiré
   du LiDAR là où il existe (en France, le MNT LiDAR HD de l'IGN). hike2gpx
   rapatrie ses tuiles du zoom 12, les rééchantillonne sur la grille d'une
   seconde d'arc (environ 30 m) qu'attend BRouter, et les lui donne à la
   compilation. Le calcul pénalise ainsi les pentes du terrain réel, et non
   celles de la cime des arbres du SRTM que portent les tuiles du site de
   BRouter.

Le lot d'une case réunit cette RD5, les franchissements de la case, les calques
qu'affiche la carte (chemins, barrières, franchissements, chemins non
raccordés) et un manifeste qui donne l'empreinte SHA-256 de chaque fichier.
Ailleurs dans le monde, le lot reprend la RD5 du site de BRouter (voir
[Hors des pays du serveur](#hors-des-pays-du-serveur--le-pc-fabrique)).

### Les franchissements, posés à chaque calcul

Les barrières ne sont pas gravées dans la tuile : elles accompagnent le lot, et
chaque calcul les pose en travers des chemins. hike2gpx lit dans OpenStreetMap
les chemins praticables à pied, les barrières dessinées en ligne, les nœuds
barrière et les itinéraires de randonnée balisés. Chaque croisement est jugé
**bloquant**, **à vérifier** ou **franchissable**, avec les règles de
[gpx2elev](https://github.com/nico579/gpx2elev), recopiées telles quelles dans
`regles.py` : une clôture traversée sans ouverture cartographiée bloque, un
portail sans indication d'accès est à vérifier, `foot=yes` prime sur
`access=private`, des horaires ou des conditions laissent un doute. Sur un
réseau fusionné, un sentier OSM et un chemin IGN arrêtés de part et d'autre
d'une clôture, une fois raccordés, la traversent : les franchissements se
cherchent donc sur le réseau entier, carte nationale comprise.

Chaque franchissement arrive à BRouter comme une petite ligne d'un mètre posée
en travers du chemin (son paramètre `polylines`). Sans poids, elle retire le
tronçon du calcul ; avec un poids, elle le rend coûteux, de sorte qu'un détour
de moins de 300 m environ l'évite. Quand deux coupes tombent sur le même
tronçon, l'interdite l'emporte toujours sur la pondérée ; et si le tracé rendu
par BRouter passait malgré tout une coupe interdite, hike2gpx le refuserait au
lieu de l'afficher.

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

### Le dénivelé, recalculé par gpx2elev

Le dénivelé que donne BRouter vient du relief grossier de ses tuiles. Une fois
l'itinéraire tracé, hike2gpx le recalcule avec le moteur de
[gpx2elev](https://pypi.org/project/gpx2elev/), selon son protocole publié :

1. le tracé est échantillonné tous les 5 m ;
2. l'altitude de chaque point est lue dans le meilleur modèle de terrain qui
   couvre **tout** le parcours, dans cet ordre : IGN LiDAR HD, Mapterhorn,
   FABDEM, Copernicus GLO-30, SRTM. Un seul modèle pour tout le tracé, jamais
   un mélange, pour qu'une couture entre deux modèles ne fabrique pas une
   marche ;
3. le profil est lissé par une gaussienne de 20 m, qui efface le bruit du
   modèle sans aplatir une vraie bosse ;
4. les montées et les descentes se comptent avec une hystérésis de 2 m : une
   variation n'entre dans le total qu'une fois dépassés 2 m dans le même sens.
   Un chemin qui ondule d'un mètre sur un kilomètre n'ajoute donc pas cent
   mètres de montée imaginaires.

La durée suit le modèle de Tobler, appliqué au profil par pas de 20 m : la
vitesse vaut 6 × e<sup>−3,5 × |pente + 0,05|</sup> km/h, soit environ 5 km/h
sur le plat, un peu plus en légère descente, beaucoup moins dans les fortes
pentes. Tant que gpx2elev calcule, le chiffre de BRouter sert d'estimation ; si
aucun modèle ne couvre le parcours, le dénivelé est dit indisponible plutôt que
remplacé par ce chiffre.

### Le serveur de lots, sur GitHub

Chaque dimanche à 02 h 17 UTC, GitHub Actions fabrique les lots des quinze
cases de 5° qui couvrent les pays à carte nationale : la France, la Suisse,
l'Allemagne, la Tchéquie et la Pologne. Chaque case a sa tâche, en parallèle ;
la case du Var (E5_N40) demande environ une heure et demie, 6 Go de mémoire et
35 Go de disque. Une case dont les éditions n'ont pas changé (extrait OSM,
carte nationale) n'est pas refaite. Les lots partent sur la publication fixe
« bundles » du dépôt
[hike2gpx-bundles](https://github.com/nico579/hike2gpx-bundles), avec leur
catalogue `catalog.json`, et chaque fabrication y laisse un compte rendu
horodaté dans `rapports/`. La logique vit dans ce dépôt-ci
(`.github/workflows/bundles.yml`), à côté du code qu'elle exécute ; le dépôt
des lots ne garde qu'un petit appel planifié.

L'ordinateur et le téléphone lisent ce catalogue : un lot se télécharge de
lui-même dès qu'un calcul ou la carte touche sa case, chaque fichier vérifié
par son empreinte avant l'installation, et se renouvelle quand le serveur en
publie un plus récent. Le détail est dans [Lots hors ligne](#lots-hors-ligne).

### Les cartes : fonds et fournisseurs

Chaque pays a son fichier `hike2gpx/assets/web/providers/<pays>.js` : ses fonds
de carte (le SCAN 25, le Plan IGN et les photos de l'IGN, la carte nationale de
swisstopo, TopPlusOpen pour l'Allemagne…), ses calques, leurs styles et leurs
libellés. La carte suit le pays de son centre et propose ses fonds. Les pays
dont les chemins servent au calcul ont en plus un lecteur dans
`hike2gpx/providers/` : la BD TOPO par région, l'ATKIS (les WFS de Bavière et
de Thuringe, ailleurs les tuiles vectorielles de
[basemap.de](https://basemap.de/produkte-und-dienste/web-vektor/), des
géométries de présentation dont la précision reste à vérifier), swissTLM3D et
ZABAGED dans leur édition nationale, la BDOT10k par district. Le registre de ce
dossier relie les pays à leurs sources ; l'affichage et le calcul suivent
ensuite le même mécanisme. Le [tableau des pays pris en
charge](RAPPORT_SOURCES_CHEMINS_BROUTER.md#pays-pris-en-charge) est généré
depuis ces fichiers.

Pour le téléphone, les fonds se gardent hors ligne quand leur licence le
permet : les tuiles du SCAN 25, du Plan IGN, des photos ou du relief LiDAR,
rangées en MBTiles. OpenStreetMap interdit la recopie en masse de ses tuiles :
le PC fabrique donc, depuis l'extrait Geofabrik, une carte vectorielle au
format Mapsforge (celui de Locus Map), que le téléphone dessine lui-même.

### Hors des pays du serveur : le PC fabrique

Pour l'Espagne, l'Italie, la Norvège ou n'importe où ailleurs, le serveur ne
publie rien : c'est votre PC qui prépare le lot, pour la vue affichée ou la case
entière, depuis « Gestion des itinéraires ». Sans carte nationale, il n'y a
rien à compiler : la RD5 est celle que le site de BRouter publie chaque nuit,
et le PC n'y ajoute que ce qu'elle ne contient pas, les franchissements et les
calques, tirés de l'extrait Geofabrik qu'il a téléchargé. Une vue de quelques
kilomètres est prête en trois minutes environ. Le lot se partage ensuite au
téléphone par le Wi-Fi, comme un fond de carte.

Sans lot, la page calcule quand même, à la volée : elle lit OpenStreetMap
(extrait installé ou Overpass) et, en France ou en Allemagne, refait au fil
des zones consultées une petite tuile BRouter maison, jusqu'à 25 tuiles de
0,05°. C'est le mode d'origine de hike2gpx ; un lot installé qui couvre tout le
parcours passe devant lui, sans réseau.

### La page et le journal

La page locale est servie par la bibliothèque commune
[nico579-commons](https://pypi.org/project/nico579-commons/), qui partage avec
les autres applications de nico579 l'icône de la zone de notification, la
langue et la mise à jour. Chaque calcul laisse sa trace dans le journal de la
session (`logs/hike2gpx-<date>.log`, dans le dossier de données ; les dix
dernières sessions sont gardées), avec le temps de chaque étape, ses erreurs et
ses lenteurs.

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
franchissements se jugent de la même façon. Overpass ne sert plus qu'hors des
extraits installés : une tuile à cheval sur une frontière est lue dans les
deux extraits voisins, qui la couvrent ensemble ; et une tuile qui attendait
Overpass au moment où un extrait s'installe bascule aussitôt sur lui. OSM France et Geofabrik refont leurs extraits chaque jour ;
plus vieux que le délai choisi dans les réglages (30 jours par défaut, de 1 à
365), l'extrait se renouvelle de lui-même en tâche de fond, l'ancien servant
jusqu'à la bascule. Les tuiles BRouter suivent le même délai.

### Lots hors ligne

Un extrait épargne Overpass, mais un calcul a encore besoin du réseau pour les
chemins officiels et les tuiles BRouter. Pour partir sans aucune connexion,
hike2gpx travaille avec des lots : tout ce dont une case BRouter de 5° a besoin
(données de routage, chemins officiels, franchissements, calques), chaque
fichier vérifié contre l'empreinte SHA-256 d'un manifeste.

« Gestion des itinéraires » montre sur la carte la grille des cases de 5°,
tant que la page est ouverte : on clique celles qu'on veut, puis « Télécharger ».
Un lot s'obtient de deux façons :

- **le télécharger depuis le serveur.** Les cases de la France, de la Suisse, de
  l'Allemagne, de la Tchéquie et de la Pologne sont fabriquées chaque semaine
  ([comment](#le-serveur-de-lots-sur-github)) et publiées sur
  [hike2gpx-bundles](https://github.com/nico579/hike2gpx-bundles) ; la grille
  les montre en bleu. La case du Var, 247 Mo, arrive en quelques dizaines de
  secondes, reprise après une coupure, chaque fichier vérifié avant
  l'installation. Pas besoin de cliquer : dès qu'un calcul ou les chemins de
  la carte touchent une case publiée, son lot se télécharge de lui-même, et
  le mode à la volée sert en attendant. Un lot venu du serveur se renouvelle
  aussi tout seul quand le serveur en publie un plus récent.
- **le préparer sur ce PC**, pour la vue affichée ou la case entière, partout
  dans le monde. Là où un fournisseur national existe (BD TOPO de l'IGN,
  ATKIS, ZABAGED, swissTLM3D, BDOT10k), ses chemins sont fusionnés dans
  OpenStreetMap et les données de routage compilées avec le relief Mapterhorn ;
  ailleurs, le lot reprend les tuiles BRouter que publie brouter.de. Une vue de
  quelques kilomètres est prête en trois minutes environ.

Une règle s'applique alors : quand un lot installé couvre tout le parcours, il
sert seul, au calcul comme aux calques, sans réseau ; sinon, tout se fait à la
volée comme avant. La case « chemins officiels » garde son sens : décochée, les
chemins officiels restent dans le lot, mais le calcul ne peut pas les
emprunter. Les caches se renouvellent d'eux-mêmes ; un lot plus vieux que le
délai de renouvellement demande d'abord. Une case qui chevauche une frontière
prend tous les fournisseurs dont le pays la touche : E5_N45 réunit les chemins
de l'IGN et de swissTLM3D, chacun lu sur son seul pays.

Une case dont on n'a plus besoin, après un voyage par exemple, se retire par
sa bulle : « Supprimer de cet ordinateur » efface son lot et ses fonds de
carte. Le bouton « Vider le cache » des réglages, lui, repart de zéro : caches, lots et
fonds hors ligne compris. Un lot du serveur se retélécharge en quelques
secondes ; un lot ou un fond préparé sur l'ordinateur est à refaire.

Reste la carte elle-même. En France, « Gestion des cartes » prépare aussi, par
cases de 1° choisies sur la carte, le **fond de carte hors ligne** : les tuiles du fond choisi dans la liste, rangées
sur ce PC dans un fichier MBTiles. Se gardent ainsi les fonds dont la licence
le permet : le SCAN 25 (avec une clé IGN), le Plan IGN, les photos aériennes
et le relief LiDAR HD de l'IGN. OpenStreetMap se garde aussi, mais autrement :
son serveur de tuiles interdit de les recopier en masse, alors que ses données
sont libres. Le PC fabrique donc, depuis l'extrait Geofabrik de la région, une
carte vectorielle au format Mapsforge (celui de Locus Map et d'OpenAndroMaps),
que le téléphone dessine lui-même ; sur le PC, OpenStreetMap reste en ligne.
La première fois, hike2gpx télécharge pour cela Osmosis et son greffon
Mapsforge (20 Mo). OSM rando et la vue satellite restent en ligne : leurs
serveurs interdisent la recopie et leurs données ne sont pas libres. Un fond
téléchargé ne s'affiche pas sur le PC, qui reste en ligne : il sert au
téléphone, à qui le PC le partage. Une vue
d'écran se prend jusqu'au zoom 16, celui des sentiers : autour de Garéoult,
631 tuiles, 12 Mo en SCAN 25 (27 Mo en Plan IGN), un peu plus d'une minute.
Une case entière s'arrête au zoom 13, pour la vue d'ensemble : la case
E5_N40 fait 151 Mo en SCAN 25 et demande environ trois quarts d'heure, car
hike2gpx ménage le service de l'IGN (dix tuiles par seconde au plus). Un fond
interrompu reprend où il s'était arrêté. Le SCAN 25 n'étant pas une donnée
libre, un fond reste sur votre PC : il n'est jamais publié.

### Partager au téléphone

Le téléphone prend les lots du serveur sur GitHub. Ce que seul votre PC
possède, les lots préparés hors des pays du serveur et les fonds de carte, il
le reçoit de lui, par le Wi-Fi. Dans « Gestion des cartes » et « Gestion des
itinéraires », le bouton « Partager » affiche un QR code : scannez-le avec hike2gpx sur le téléphone, connecté au
même réseau. Le PC sert alors ses lots et ses fonds, chaque fichier vérifié
par son empreinte à l'arrivée, repris après une coupure. Le partage est fermé
tant que vous ne l'ouvrez pas, n'écoute que sur le réseau local, et son code
change à chaque ouverture ; « Arrêter le partage » le referme. Le détail du
protocole est dans
[docs/architecture/partage-telephone.md](docs/architecture/partage-telephone.md).

### Fabriquer des lots en ligne de commande

La page et la ligne de commande partagent le même code. C'est ainsi que
travaille le serveur :

```
hike2gpx cells --bulk-only                      # les cases à fabriquer
hike2gpx bundles E5_N40 E5_N45 --bulk --output lots/
hike2gpx catalog lots/ --publish-dir publication/
```

`cells` liste les cases que touchent les pays des fournisseurs.
`bundles --bulk` lit chaque fournisseur dans son téléchargement en bloc (les
archives régionales de la BD TOPO) plutôt que par son service web : une case
entière demanderait sinon des milliers de requêtes. Un lot à jour est sauté, et
une case en échec n'arrête pas les autres. `catalog` écrit le catalogue que lit
l'application. Le serveur hebdomadaire est un
[workflow réutilisable](.github/workflows/bundles.yml) qu'appelle le dépôt des
lots : une machine GitHub Actions par case, environ une heure et demie pour une
case entière.

Une panne passagère (Geofabrik saturé, coupure) ne perd plus une case : chaque
étape se relance, et ne refait que ce qui manque. À la fin de chaque run,
`freshness` vérifie le catalogue publié : une case absente, ou un lot de plus de
14 jours, fait échouer le run. `report` écrit alors son compte rendu, case par
case et étape par étape, avec la cause de chaque échec. Il est gardé, horodaté,
dans le dossier `rapports/` du dépôt des lots : l'historique des fabrications
se lit là, bien après l'effacement des journaux des runs.

## Limites

hike2gpx ne peut éviter que ce qui est cartographié. Autour de Garéoult, sur
250 km², OpenStreetMap ne recense que 18 clôtures, et la BD TOPO de l'IGN
aucune (voir [ESSAI.md](ESSAI.md)). Une clôture rencontrée sur le terrain et
ajoutée à OpenStreetMap est respectée par hike2gpx dès que son cache de la
zone se renouvelle ; les moteurs des autres planificateurs, eux, continuent de
l'ignorer.

En dehors de la France, de l'Allemagne, de la Tchéquie, de la Suisse et de la
Pologne, le calcul ne connaît que les chemins d'OpenStreetMap : un
sentier absent d'OSM n'existe pas pour lui, même si la carte nationale le
dessine. En Allemagne, les chemins ATKIS intégrés n'ont
pas de droit de passage piéton explicite : les portions empruntées restent
à vérifier sur place.

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

Installé depuis une release, hike2gpx se met à jour tout seul, comme les
autres applications de nico579 : quand une version plus récente est publiée,
un bandeau de la page et le menu de son icône proposent de l'installer ; il
la télécharge, la vérifie, puis redémarre dessus. Le bouton « Vérifier les
mises à jour » du panneau Réglages pose la question tout de suite, sans
attendre la vérification périodique. Lancé depuis les sources, hike2gpx se
contente d'ouvrir la page de la nouvelle version.

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
Ouverte. Les autres fonds ne demandent aucune clé.

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
