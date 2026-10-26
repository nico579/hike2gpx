# Mailles précalculées et mode hors ligne

Cette note fixe la cible avant de reprendre le travail des PR #36 (mode
serveur), #37 (serveur Linux) et #38 (application Android). Ces trois PR ont
prouvé que l'idée tient : un serveur prépare les données, l'application les
télécharge et calcule elle-même l'itinéraire. Elles ont aussi montré où le
chemin suivi s'écartait des formats que l'écosystème connaît. On repart donc
d'un besoin unique, vu d'ensemble.

## Le besoin

Ce qui coûte cher se calcule à l'avance : la fusion d'OSM et des chemins
officiels (BD TOPO en France), les franchissements, les données de routage
BRouter. L'unité de ce calcul, de sa distribution et du choix de
l'utilisateur est la **case RD5 de BRouter**, 5° × 5°. L'utilisateur coche des
cases sur la carte et reçoit, pour chacune, un **lot** : la RD5 enrichie, les
calques OSM et officiels, les franchissements, et un manifeste. Avec ce lot, il
travaille sans réseau.

Le fond de carte fait exception : il est fabriqué **sur l'appareil**, jamais
distribué, et choisi plus finement qu'une case. Une case au zoom 16 compterait
un million de tuiles. Les licences ne permettent pas non plus de le
redistribuer : le SCAN 25 passe par la clé de l'utilisateur, et les serveurs de
tuiles OSM interdisent le téléchargement en masse.

## Trois données, trois formats standard

Chaque donnée a déjà, dans l'écosystème, un format reconnu. On les prend tels
quels plutôt que d'en inventer un.

### Routage : la RD5 de 5° de BRouter

BRouter range ses données dans des fichiers RD5 qui couvrent chacun une case
de 5° × 5°. C'est l'unité que télécharge son application Android, et BRouter
sait calculer un itinéraire à travers plusieurs cases. BRouter ne lit qu'un
fichier par case : une RD5 doit donc contenir **tout l'OSM de sa case**, y
compris les parties étrangères (l'Italie dans `E5_N40`), sinon elle
remplacerait la RD5 officielle par une version trouée.

Pour l'OSM seul, on prend les **RD5 officielles de brouter.de**, refaites
chaque nuit à partir de la planète : 805 Mo pour les huit cases qui touchent
la France, sans aucun calcul. On ne fabrique que les cases **enrichies** par
les chemins officiels. Une RD5 étant compilée, on ne peut pas y ajouter des
chemins après coup : on recompile la case entière, à partir d'OSM et des
chemins IGN déjà raccordés (`hike2gpx/case.py`).

Une RD5 compilée par nos soins reçoit son **relief** de Mapterhorn : en
France, le MNT LiDAR de l'IGN (`deploy/linux/relief_case.py`). Sans relief,
le dénivelé calculé par BRouter est nul.

PR #37 avait choisi un découpage au quart de degré, avec un format `.rd5q` et
un réassembleur écrit deux fois, en Python et en Java. La preuve était solide
(reconstruction identique au SHA-256 près), mais ce découpage oblige à
contrôler la couverture avant chaque calcul : une RD5 à trous fait croire à
BRouter qu'il n'y a pas de chemin là où il manque seulement des données. Avec
des cases entières, ce contrôle se réduit à une seule question : la case
est-elle présente ? On abandonne donc `.rd5q`.

Les franchissements interdits restent transmis à BRouter sous forme de coupes
(`polylines`) au moment du calcul, comme aujourd'hui. Ils sont livrés à part,
dans un fichier par case, avec leurs coupes exactes : ils servent au calcul et
au contrôle du tracé, pas seulement à l'affichage. Les graver dans la RD5
imposerait le mode strict à tous, alors que le mode souple laisse passer les
franchissements « à vérifier ».

### Calques OSM et chemins officiels : tuiles vectorielles en MBTiles

La RD5 est compacte parce qu'elle range des coordonnées entières, codées en
écart par rapport au point précédent, puis compressées. On ne peut pas y loger
les calques : seul le code Java de BRouter la lit, elle ne garde que les
étiquettes utiles au routage, et les franchissements n'y ont pas de place. Mais
l'affichage a son format standard construit sur la même idée : la **tuile
vectorielle MVT** (Mapbox, 2014). Les coordonnées y sont entières dans la
tuile, codées en écarts, en protobuf. Rangées dans un **MBTiles**, ces tuiles
forment un fichier SQLite où chaque tuile se lit d'une seule requête.

Le serveur fabrique les tuiles du **zoom 14** (précision d'environ 0,5 m),
avec trois couches : `chemins_osm`, `chemins_officiels` (avec leur source) et
`barrieres`. L'affichage les agrandit au-delà du zoom 14. La page sait déjà
lire ce format : le provider espagnol affiche les sentiers FEDME avec
`L.vectorGrid.protobuf`. Sur Android, osmdroid ne lit que des tuiles d'image ;
il faudra une bibliothèque qui dessine les tuiles vectorielles, MapLibre étant
la référence.

Les calques suivent la case : **un MBTiles par case**, dont les objets sont
coupés à ses bords. La limite d'une case ne tombe pas sur la grille des tuiles,
si bien qu'une tuile de bord appartient à deux cases. On ne fusionne donc pas
les MBTiles : l'application affiche un calque vectoriel par case présente,
comme Leaflet et MapLibre savent le faire avec plusieurs sources, et les deux
moitiés d'une tuile de bord se juxtaposent sans couture.

Le serveur ne fabrique pas de format intermédiaire à lui. Il lit les sources
telles qu'elles arrivent : le PBF d'OSM, et le GeoPackage dans lequel l'IGN
livre la BD TOPO, par son index RTree. La fusion se fait en mémoire et écrit
trois sorties : un PBF pour le créateur de RD5 de BRouter, du GeoJSON ligne à
ligne pour les tuiles, et les franchissements. Les tuiles sortent de
tippecanoe (Mapbox, aujourd'hui maintenu par Felt), l'outil standard qui prend
ce GeoJSON en entrée. Pour vérifier un résultat, QGIS ouvre aussi bien le
MBTiles vectoriel que ce GeoJSON.

Les mesures, plus bas, justifient ce choix : pour une maille, les tuiles
pèsent deux fois moins que le JSON gzip de #37 et huit fois moins qu'un
GeoPackage, et une vue ne lit que les quelques tuiles qu'elle couvre.

### Fond de carte : MBTiles

MBTiles est une convention lancée par Mapbox en 2011 : des tuiles d'image dans
une table SQLite. C'est la norme de fait du hors ligne. osmdroid, la
bibliothèque de carte de l'application Android, la lit directement, QGIS aussi.
Sur le bureau, le serveur Python local sert ces tuiles à Leaflet.

L'application remplit son MBTiles en demandant les tuiles de la zone choisie,
entre les niveaux de zoom utiles à la randonnée (à fixer, sans doute 12 à 16),
avec les droits de l'utilisateur : Plan IGN, SCAN 25 avec sa clé, fonds
nationaux dont la licence le permet. Le fond OSM standard n'est pas proposé au
hors ligne.

## Traiter la France : importer par région, fabriquer par case

Le serveur garde le moins de fichiers possible. L'IGN livre la BD TOPO en
treize archives régionales (21 Go compressés ; PACA seule fait 9,8 Go une
fois extraite). On sépare donc deux étapes qui n'ont pas la même unité.

**L'import se fait région par région.** Pour chaque archive, on la
télécharge, on en tire avec `ogr2ogr` les seuls tronçons utiles (chemins,
sentiers, escaliers, routes empierrées) qu'on ajoute à un **fichier national
allégé**, dans le format de l'IGN, puis on efface l'archive et le GeoPackage
régional avant de passer à la suivante. Le disque ne porte jamais plus d'une
région à la fois.

**Les jonctions entre régions se règlent à l'import, par l'identifiant.**
Chaque tronçon BD TOPO porte un identifiant national (`cleabs`). Les
livraisons régionales se chevauchent : celle de PACA (édition 2026-09, 1 593 561
tronçons) en contient environ 93 000 rattachés aux départements voisins, dont
44 475 dans la Drôme et 40 231 dans le Gard. Un même tronçon arrive donc par
deux régions, et l'ajout au fichier national dédoublonne sur `cleabs`. Une fois l'import
fini, il n'y a plus de régions, seulement une source continue.

**La fabrication se fait par case RD5, et en interne par maille de 0,25°**,
pour tenir en mémoire. Chaque maille lit OSM et la source nationale avec une
couronne de voisinage, et chaque tronçon n'est ajouté que par la maille de son
premier point. Un registre commun à la case garde le réseau d'un seul tenant :
identifiants uniques, bouts partagés aux limites, raccords réunis sur les voies
OSM longues. Une maille à cheval sur deux régions ne voit donc aucune
frontière. La RD5, les calques et les franchissements d'une case sortent de la
même fusion : on affiche le réseau sur lequel on calcule.

**Ce qui reste à demeure** : les lots publiés (par case : RD5, calques,
franchissements, manifeste), le catalogue, et le fichier IGN allégé, qu'on
renouvelle à chaque édition de la BD TOPO. Les PBF Geofabrik se
retéléchargent à chaque édition, puisqu'ils sont refaits chaque jour, et les
intermédiaires sont effacés après succès.

## Le geste de l'utilisateur

L'utilisateur coche des cases RD5 sur la carte, puis, à l'intérieur, la zone
dont il veut le fond. L'application affiche la taille totale, obtient le lot
de chaque case et vérifie chaque fichier par son SHA-256. Une case n'est
déclarée utilisable hors ligne qu'une fois son lot complet.

Le **manifeste** d'un lot est le contrat commun : la liste des fichiers avec
leurs tailles et empreintes, la version du format, et l'édition des sources
(date d'OSM, édition de la BD TOPO, relief). Il est identique quel que soit le
producteur. Un **catalogue**, petit fichier JSON, réunit les manifestes des
cases disponibles ; l'application le compare à ce qu'elle détient et propose
les mises à jour.

## Qui fabrique, qui partage

Le **même code** fabrique un lot sur le PC et sur le serveur. Les rôles :

- le **serveur**, s'il existe, fabrique et publie les lots ; le PC et le
  téléphone les téléchargent ;
- le **PC** obtient une case en la téléchargeant au serveur, ou en la
  fabriquant lui-même. Il la garde pour son propre mode hors ligne et la
  partage au téléphone, et à lui seul ;
- le **téléphone** ne fabrique jamais : il reçoit des lots du serveur ou du
  PC, et calcule ses itinéraires avec BRouter embarqué.

Le partage du PC au téléphone suit le schéma de LocalSend ou Syncthing. Le PC
affiche un **QR code** qui porte son adresse sur le réseau local et un jeton
à usage unique, valable quelques minutes. Le téléphone le scanne et télécharge
le lot par le Wi-Fi, en vérifiant les empreintes du manifeste. Le serveur de
l'application ne s'ouvre au réseau local que le temps du partage, et seulement
pour les routes de lecture protégées par le jeton.

En ligne, le PC garde aussi le mode actuel : la fusion à la volée autour du
parcours (Overpass, WFS ou extraits locaux), sans rien préparer. Il cherche
d'abord une case présente sur le disque, puis, faute de mieux, fusionne à la
volée. Les deux donnent le même réseau, puisqu'ils passent par `fusion.py` ;
seule la fraîcheur des sources diffère.

Le **serveur est facultatif**. Pour un usage personnel, le PC suffit. Pour
partager plus largement sans serveur de calcul, les lots fabriqués sur un PC
peuvent être publiés comme fichiers statiques (par exemple en releases
GitHub) : OSM (ODbL, attribution et partage à l'identique) et la BD TOPO
(Licence Ouverte Etalab) le permettent. Un serveur de calcul ne se justifie
que pour rafraîchir automatiquement les lots chaque semaine.

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
serveur à l'application de bureau. Elle reste en service tant que la nouvelle
chaîne ne l'a pas remplacée, et les PR #36 à #38 ne seront fermées qu'à ce
moment. Voici ce qui y tourne, relevé le 26 octobre 2026.

**Le service.** La VM est sous Ubuntu 26.04, que l'installateur de #37 refuse
(il vise 24.04) : il n'y a donc ni `/var/lib/hike2gpx`, ni Caddy en service, ni
timer de renouvellement. Un seul service tourne, `hike2gpx-vmtest`, sous
l'utilisateur `vboxuser`, sur le port 8796 de la VM. Le bureau l'atteint par un
tunnel SSH (`127.0.0.1:2222` vers la VM, puis `127.0.0.1:8796`). Son
environnement Python est une copie installée le 25 octobre depuis le dossier
partagé `/media/sf_Documents/hike2gpx`, c'est-à-dire le checkout Windows. Pour
les routes serveur, cette copie équivaut à la pointe de
`feat/linux-server-deploy` ; elle ne diffère que par les replis du client
cloud, que le serveur n'emprunte pas. Changer de branche sur le PC ne touche
pas le service, une réinstallation si.

**Les données servies** (`~/hike2gpx-data-clean`, 114 Mo) couvrent deux
mailles près de Garéoult, `173_24` et `173_25`, soit `[43,25 ; 6,00 ; 43,50 ;
6,50]`. Chacune a un calque OSM (environ 0,85 Mo gzip) et un calque IGN
(environ 1,6 Mo gzip). Deux paquets de routage existent :

- un paquet **format 1**, qui livre la RD5 OSM standard entière de `E5_N40`
  (69 Mo), avec profil et franchissements. C'est déjà le mode de distribution
  que retient cette note, moins l'enrichissement par la BD TOPO ;
- un paquet **format 2** (IGN, strict), avec les deux fragments `.rd5q`
  (0,6 Mo chacun) et un `chemins-officiels.json` de 23,9 Mo non compressé
  pour ces deux seules mailles.

**Les sources** (`~/hike2gpx-data-france`, 16 Go) sont celles dont la
fabrication nationale aura besoin : le PBF France de Geofabrik (4,8 Go),
l'archive BD TOPO de la région R93 (PACA) extraite en GeoPackage (9,8 Go),
l'extrait OSM de `E5_N40` (373 Mo) et son index SQLite (347 Mo). Deux tâches
lancées par `systemd-run` restent en échec dans la liste des services :
l'index OSM national, arrêté le 25 octobre, et la première extraction de
`E5_N40`, tuée faute de mémoire avant la seconde tentative, réussie avec du
swap. Le disque a 61 Go libres sur 99.

**Ce que disent les journaux.** Pour une vue de quelques centaines de mètres,
le service met 1,2 à 3,3 s à répondre le calque IGN et renvoie 0,7 à 1,9 Mo
de JSON. L'essai qui suit isole la part du format dans ce temps.

La première PR à venir s'installe donc sur cette VM plutôt que de repartir de
zéro. La bascule se fait case par case : la VM publie les nouveaux fichiers
(les lots par case et le catalogue) à côté des paquets actuels,
puis les anciennes routes et les anciens paquets disparaissent quand le bureau
lit le nouveau format.

## Essais de format des calques

Le 26 octobre, les calques des deux mailles servies par la VM (`173_24` et
`173_25`) ont été convertis tels quels en GeoPackage, avec GDAL 3.12 par
pyogrio et un index RTree par table. Les scripts sont dans
`tools/essai_geopackage/`. La lecture d'une vue passe par le seul `sqlite3`
de Python et son index, comme le ferait un client, puis par un test
d'intersection exact. On la compare à ce que fait le service : décompresser
les JSON des mailles touchées et garder les objets dont un point tombe dans
la vue. Les vues sont celles des journaux ; on retient le meilleur de cinq
essais.

| Vue (degrés) | Calque | JSON gzip | GeoPackage | Objets |
| --- | --- | ---: | ---: | ---: |
| 0,024 × 0,073 | IGN | 926 ms | 7,5 ms | 512 |
| 0,006 × 0,018 | IGN | 895 ms | 1,0 ms | 40 |
| 0,0015 × 0,0046 | IGN | 1 100 ms | 0,3 ms | 5 |
| 0,024 × 0,073 | OSM | 420 ms | 2,0 ms | 166 |
| 0,006 × 0,018 | OSM | 533 ms | 0,3 ms | 12 |

Les deux méthodes trouvent le même nombre d'objets. Le JSON coûte près d'une seconde
quelle que soit la vue, puisqu'il faut tout décompresser ; le GeoPackage ne
lit que ce que l'index désigne.

La taille va dans l'autre sens. La maille `173_24` fait 10,7 Mo en
GeoPackage et 5,4 Mo une fois gzippée, contre 2,4 Mo pour ses deux JSON
gzip. Les géométries occupent 7,3 Mo de ce total : le format WKB de la norme
range chaque point en deux nombres de 8 octets, qui se compressent mal, alors
que le texte « 43.385359 » se compresse très bien. L'index RTree pèse 1,3 Mo
et il n'y a pas d'espace libre à récupérer.

Le levier standard est de simplifier les tracés destinés à l'affichage
(Douglas-Peucker, `shapely.simplify`). Avec une tolérance de 2 m, invisible
puisqu'un pixel du zoom 16 couvre déjà 1,7 m à cette latitude, on garde 65 %
des points OSM et 43 % des points IGN. Le GeoPackage reviendrait alors autour
de la moitié de sa taille, soit environ 5 à 6 Mo par maille.

La même maille a ensuite été découpée en tuiles vectorielles MVT
(`mapbox-vector-tile`, grille de 4096 par tuile, chaque tuile gzippée comme
dans un MBTiles), sans simplification préalable :

| Format, maille `173_24` | Taille |
| --- | ---: |
| GeoPackage | 10,7 Mo |
| GeoPackage gzippé | 5,4 Mo |
| JSON gzip de #37 (OSM + IGN) | 2,4 Mo |
| MVT zoom 15 (1 148 tuiles) | 1,8 Mo |
| **MVT zoom 14** (315 tuiles d'environ 4 Ko) | **1,3 Mo** |

Le zoom 14 l'emporte sur tous les plans : le plus petit, une lecture d'une
seule ligne SQLite par tuile, et une précision de 0,5 m qui suffit à
l'affichage. C'est ce qui a fait abandonner le GeoPackage, en distribution
comme sur le serveur. Pour le Var, cela représente une trentaine de Mo de calques.

## Mesures sur la case E5_N40, enrichie sur le Var

Fabriquée le 26 octobre 2026 sur la VM (2 cœurs, 6 Go de mémoire, 8 Go de
swap), à partir de six extraits Geofabrik du même instantané et du GeoPackage
BD TOPO de PACA, filtré sur le département 83 :

| Étape | Durée |
| --- | ---: |
| Découpe et fusion des extraits OSM à la case | 662 s |
| Index OSM de la case | 302 s |
| Fusion des 30 mailles du Var | 454 s |
| Écriture du PBF enrichi | 501 s |
| Relief Mapterhorn de la case (4 524 tuiles, 187 Mo) | 303 s |
| Compilation de la RD5 | 176 à 187 s |

La fusion ajoute 66 293 chemins IGN, raccorde 21 832 voies OSM et donne 20 035
franchissements (1,1 Mo en JSON gzip). Une maille dense prend une demi-minute.

| RD5 `E5_N40` | Taille |
| --- | ---: |
| OSM seule, sans relief | 55,97 Mo |
| Enrichie, sans relief | 58,02 Mo |
| **Enrichie, relief Mapterhorn** | **68,83 Mo** |
| Officielle brouter.de | 69,3 Mo |

L'enrichissement du Var coûte 3,7 %, et le relief près de 11 Mo.

Ces chiffres ont été vérifiés avec BRouter, à l'aide de
`deploy/linux/verifier_case.py`. Les trajets entre les extrémités de chemins
IGN ajoutés les empruntent entièrement ; sans enrichissement, il faut des
détours de 1,5 à 9 fois leur longueur. Les franchissements bloquants sont
respectés : 10 sur 10 sur les chemins IGN, 10 sur 10 sur les voies OSM.

Sur deux randonnées des Maures, le relief Mapterhorn donne les mêmes
altitudes que le RGE ALTI de l'IGN, à environ 1 m près, comme la RD5
officielle. Sans relief, l'écart dépasse 180 m et le dénivelé est nul. Sous ce
maquis, qui suit des pistes, le LiDAR ne fait pas mieux que SRTM ; un
avantage sous futaie haute reste à mesurer.

Deux postes restent à réduire. L'écriture du PBF fait passer chaque objet en
Python ; un petit fichier de corrections combiné par `osmium merge` serait bien
plus rapide. La découpe OSM, elle, gagnerait à partir d'un extrait Europe tenu
à jour par différences quotidiennes (`pyosmium-up-to-date`), découpé en une
passe pour toutes les cases.

## Système du serveur public

Le serveur public sera sous **Ubuntu 24.04 LTS**. La raison est concrète :
`pyproject.toml` fixe `requires-python = ">=3.12,<3.13"`, le build tourne en
3.12, et Ubuntu 24.04 livre Python 3.12 dans ses paquets. L'installateur peut
donc s'en tenir à `apt` et au fichier de verrouillage. Ubuntu 26.04 livre
Python 3.14 et plus de paquet `python3.12`. Pour faire tourner le service, la
VM de test a dû recevoir un Python 3.12 installé à part par `uv`, que
l'installateur devrait reproduire. Les hébergeurs proposent les deux versions,
et la 24.04 reste maintenue jusqu'en 2029. On passera à la 26.04 le jour où le
projet passera lui-même à Python 3.13 ou 3.14. La VM de test peut rester en
26.04 : elle ne sert qu'à fabriquer et à essayer.

## Ordre des PR à venir

Chaque brique est fusionnée dès qu'elle est complète, testée et sans effet sur
ce qui marche déjà.

1. **Fabrication d'une case enrichie** : fait, #42.
2. **Relief Mapterhorn et tas Java réglable** : #43.
3. **Le lot d'une case** : manifeste, calques en tuiles vectorielles et
   franchissements, fabriqués par le même code sur le PC et le serveur.
4. **Bureau, hors ligne** : sélection des cases, fabrication ou
   téléchargement, stockage, calcul sans réseau, partage par QR code.
5. **Bureau, fond** : MBTiles local du fond de carte, sur une zone choisie.
6. **Android** : les mêmes lots, avec MapLibre pour les tuiles vectorielles et
   BRouter embarqué.
7. **Serveur**, si l'usage le justifie : fabrication et publication planifiées.
   Les PR #36 à #38 seront fermées quand la VM servira les nouveaux lots.

## Questions ouvertes

- La taille d'une case enrichie sur toute sa partie française (le Var n'en est
  qu'un département), et celle de ses calques en MBTiles.
- Le temps de fabrication d'une case sur un PC ordinaire, qui décidera si le
  mode hors ligne fabrique à la demande ou télécharge d'abord.
- Le choix de la bibliothèque de carte Android : MapLibre remplace-t-il
  osmdroid, ou s'y ajoute-t-il pour les seules tuiles vectorielles ?
- Les licences des autres fonds nationaux au hors ligne, à vérifier pays par
  pays avant de les proposer.
- La durée de vie d'une édition : à quel rythme republier, et combien de
  temps garder l'ancienne pendant le remplacement.
