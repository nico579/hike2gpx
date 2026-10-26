# Mailles précalculées et mode hors ligne

Cette note fixe la cible avant de reprendre le travail des PR #36 (mode
serveur), #37 (serveur Linux) et #38 (application Android). Ces trois PR ont
prouvé que l'idée tient : un serveur prépare les données, l'application les
télécharge et calcule elle-même l'itinéraire. Elles ont aussi montré où le
chemin suivi s'écartait des formats que l'écosystème connaît. On repart donc
d'un besoin unique, vu d'ensemble.

## Le besoin

Le serveur calcule par **pays entier** ce qui coûte cher : la fusion d'OSM et
des chemins officiels (BD TOPO en France), les franchissements, les données de
routage BRouter. L'application, sur le bureau comme sur Android, laisse
l'utilisateur **choisir des mailles sur la carte** et rapatrie de quoi
travailler sans réseau dans ces mailles : données de routage, calque OSM,
calque des chemins officiels, fond de carte.

Le fond de carte fait exception : il est fabriqué **sur l'appareil**, jamais
sur le serveur. Il pèse lourd, et les licences ne permettent pas de le
redistribuer (le SCAN 25 passe par la clé de l'utilisateur, les serveurs de
tuiles OSM interdisent le téléchargement en masse).

## Trois données, trois formats standard

Chaque donnée a déjà, dans l'écosystème, un format reconnu. On les prend tels
quels plutôt que d'en inventer un.

### Routage : la RD5 de 5° de BRouter

BRouter range ses données dans des fichiers RD5 qui couvrent chacun une case
de 5° × 5°. C'est l'unité que télécharge son application Android, et BRouter
sait calculer un itinéraire à travers plusieurs cases. Le serveur publie donc
une **RD5 complète et enrichie par case** : tout l'OSM de la case, y compris
les parties étrangères, plus les chemins officiels qui manquent à OSM. La
France métropolitaine touche neuf cases. Pour l'ordre de grandeur, la RD5 OSM
seule de `E5_N40` (Provence, Alpes du Sud) pèse 69 Mo, ce qu'un téléphone
accepte sans peine.

PR #37 avait choisi un découpage au quart de degré, avec un format `.rd5q` et
un réassembleur écrit deux fois, en Python et en Java. La preuve était solide
(reconstruction identique au SHA-256 près), mais ce découpage oblige à
contrôler la couverture avant chaque calcul : une RD5 à trous fait croire à
BRouter qu'il n'y a pas de chemin là où il manque seulement des données. Avec
des cases entières, ce contrôle se réduit à une seule question : la case
est-elle présente ? On abandonne donc `.rd5q`.

Les franchissements interdits restent transmis à BRouter sous forme de coupes
(`polylines`) au moment du calcul, comme aujourd'hui. Ils sont lus dans le
calque de la case, décrit plus bas.

### Calques OSM et chemins officiels : GeoPackage

Un GeoPackage est un fichier SQLite normalisé par l'OGC (2014). Il contient
des tables d'objets géographiques et un index spatial RTree. QGIS et GDAL le
lisent, tout comme le `sqlite3` de Python (RTree compris) et le SQLite
d'Android. La BD TOPO arrive déjà sur le serveur sous cette forme.

Le serveur publie un GeoPackage **par maille de 0,25°**, fichier statique
servi tel quel. Il contient trois tables : `chemins_osm`, `chemins_officiels`
(avec leur source) et `franchissements`. Chaque objet appartient à une seule
maille, selon la règle déjà définie dans #37 ; la fusion lit une couronne de
voisinage pour résoudre les raccords. L'application verse les mailles reçues
dans **un seul GeoPackage local** (`ATTACH` puis `INSERT`). Elle y interroge la
vue courante par l'index RTree, en ligne comme hors ligne.

Pourquoi pas les JSON gzip de #37 ? Ils conviennent au transport, mais il faut
les décompresser et les parcourir en entier pour chaque vue, et rien ne les
relie entre eux. Le GeoPackage garde les objets avec leurs attributs (le
contrôle des franchissements en a besoin), se lit par morceaux et s'ouvre dans
QGIS pour vérifier un résultat.

Les mesures de #37 donnent un ordre de grandeur : 1,5 à 2,5 Mo par maille
après épuration, calques OSM et officiels réunis. Le Var touche 25 mailles,
soit environ 50 Mo de calques.

### Fond de carte : MBTiles

MBTiles est une convention lancée par Mapbox en 2011 : des tuiles d'image dans
une table SQLite. C'est la norme de fait du hors ligne. osmdroid, la
bibliothèque de carte de l'application Android, la lit directement, QGIS aussi.
Sur le bureau, le serveur Python local sert ces tuiles à Leaflet.

L'application remplit son MBTiles en demandant les tuiles des mailles choisies,
entre les niveaux de zoom utiles à la randonnée (à fixer, sans doute 12 à 16),
avec les droits de l'utilisateur : Plan IGN, SCAN 25 avec sa clé, fonds
nationaux dont la licence le permet. Le fond OSM standard n'est pas proposé au
hors ligne.

## Le geste de l'utilisateur

L'utilisateur dessine ou coche des mailles sur la carte. L'application en
déduit trois listes : les cases RD5 qui les contiennent, les GeoPackage de
mailles, les tuiles de fond. Elle affiche la taille totale avant de télécharger,
puis vérifie chaque fichier par son SHA-256. Une zone n'est déclarée
utilisable hors ligne qu'une fois les trois listes complètes.

Un **catalogue par pays**, petit fichier JSON publié par le serveur, décrit
l'édition en cours : pour chaque case RD5 et chaque maille, le nom, la taille,
l'empreinte et la date des sources. L'application compare ce catalogue à ce
qu'elle détient et propose les mises à jour.

## Ce qu'on reprend des PR #36 à #38

On garde :

- le registre commun des providers, partagé entre serveur et application ;
- la lecture locale du GeoPackage BD TOPO par son index RTree
  (`bdtopo.troncons_gpkg`) ;
- l'installation du serveur (Caddy, systemd, renouvellement planifié) et les
  mesures faites sur la VM ;
- le client cloud du bureau, avec son repli sur le calcul local ;
- l'intégration de BRouter dans l'application Android et l'affichage osmdroid.

On abandonne :

- les fragments `.rd5q` et leurs deux réassembleurs ;
- le contrôle de couverture maille par maille ;
- les calques en JSON gzip et leur cache `cloud-paquets/calques/` ;
- la route `/api/paquet-zone`, qui composait des paquets rectangulaires à la
  demande. Le catalogue et des fichiers statiques la remplacent.

Les trois PR seront fermées sans supprimer leurs branches, qui restent la
référence pour reprendre du code.

## La VM Ubuntu en service

La VM Ubuntu de #37 n'est pas un simple banc d'essai : elle sert déjà de
serveur à l'application de bureau, par tunnel SSH, avec le code de la branche
`feat/linux-server-deploy`. Elle reste en service tant que la nouvelle chaîne
ne l'a pas remplacée, et les PR #36 à #38 ne seront fermées qu'à ce moment.

La première PR à venir s'appuie sur elle plutôt que de repartir de zéro. La VM
détient déjà ce que la fabrication nationale demande : le PBF France de
Geofabrik (4,8 Gio), le GeoPackage BD TOPO de PACA, l'index OSM de la case
`E5_N40`, Caddy, systemd et le renouvellement planifié. La bascule se fait
case par case : la VM publie les nouveaux fichiers (RD5 complète, GeoPackage
de mailles, catalogue) à côté des paquets actuels, puis les anciennes routes et les
anciens paquets disparaissent quand le bureau lit le nouveau format.

## Ordre des PR à venir

1. **Serveur.** Fabriquer et publier pour la France les neuf RD5 complètes,
   les GeoPackage de mailles et le catalogue. Mesurer les tailles réelles, case
   par case.
2. **Bureau, données.** Sélection des mailles sur la carte, téléchargement
   vérifié, GeoPackage local, lecture des calques et calcul sans réseau.
3. **Bureau, fond.** Fabrication du MBTiles local et service des tuiles à
   Leaflet.
4. **Android.** Les mêmes trois formats, lus par osmdroid, SQLite et BRouter
   embarqué.

## Questions ouvertes

- La taille réelle d'une RD5 enrichie de la BD TOPO, et celle des GeoPackage
  dans les régions denses (les mesures actuelles viennent du Var).
- Les sources OSM des parties étrangères des cases frontalières : extraits
  Geofabrik voisins, ou extrait Europe borné à la case.
- Les licences des autres fonds nationaux au hors ligne, à vérifier pays par
  pays avant de les proposer.
- La durée de vie d'une édition : à quel rythme republier, et combien de
  temps garder l'ancienne pendant le remplacement.
