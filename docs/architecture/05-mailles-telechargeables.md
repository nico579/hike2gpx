# Mailles calculées et téléchargées

## Décision et limites de BRouter

BRouter ouvre une **RD5 nommée par une case de 5° × 5°**. Il sait calculer un
itinéraire qui traverse plusieurs RD5. À l'intérieur d'une RD5, son index
contient **25 sous-cases de 1° × 1°** ; chacune contient une grille de
**32 × 32 microcaches** (pas de 0,03125°). Le moteur lit les données par
microcache. Ces niveaux ont des rôles différents :

| Niveau | Usage prévu |
| --- | --- |
| 5° | Nom et conteneur de fichier que BRouter reconnaît ; assemblage des fragments préparés par maille. |
| 1° | Sous-index natif de la RD5, utile pour assembler et vérifier. |
| 0,25° | **Lot de distribution retenu pour le prototype** : 8 × 8 microcaches, 16 lots par sous-case de 1°. |
| 0,03125° | Plus petite unité binaire ; une requête par microcache multiplierait les fichiers et les appels réseau. |

Une RD5 recomposée avec certaines mailles absentes est techniquement lisible,
mais BRouter traite ces mailles comme vides. **Le manifeste doit donc
enregistrer la couverture réellement téléchargée et le client doit refuser un
calcul qui pourrait sortir de cette couverture.** Une marge fixe autour des
points ne garantit pas tous les détours possibles. En ligne, le client pourra
charger les mailles manquantes et recommencer ; hors ligne il devra annoncer
que les données du parcours sont insuffisantes. L'affichage ne doit jamais
présenter une absence de données comme une absence de chemin.

## Même grille pour les sources et les calques

Le serveur affecte chaque tronçon et chaque franchissement à une maille de
0,25° selon une règle d'appartenance stable. Il lit également une **couronne de
voisinage** lors de la fusion, pour résoudre les raccords et les obstacles à la
limite ; les objets publiés ne sont attribués qu'une fois. Tous les pays
passent par le contrat commun des providers : extraction des chemins officiels,
attributs piétons, géométrie et provenance. OSM suit le même contrat. Les
providers nationaux gardent leurs particularités de téléchargement et de
projection ; la fabrication et la distribution n'ont pas de branche par pays.

Les sources brutes ont des formats différents : OSM est un **PBF** ; la BD TOPO
IGN régionale testée dans la VM est un **GeoPackage**, couche
`troncon_de_route`, géométrie `LINESTRING` en **EPSG:2154**, avec index RTree.
Les autres pays ne doivent pas être présumés identiques : chaque provider
convertit sa source vers le modèle commun. Le GeoPackage PACA extrait occupe
9,73 Gio et n'est pas un format de téléchargement adapté à l'application.
La lecture locale du provider IGN (`bdtopo.troncons_gpkg`) utilise l'index RTree,
reprojette en WGS84 et produit le même modèle de tronçon que le WFS. Sur la
maille de Garéoult `[43,25 ; 6 ; 43,50 ; 6,25]`, elle trouve **30 408 tronçons** :
11 294 857 octets JSON, **2 212 076 octets gzip**. Ce JSON compressé mesure le
volume de la source ; le produit final pour l'application reste à indexer et
à mesurer.

Pour l'application, un lot de 0,25° contiendra deux produits de la même édition :

1. Le fragment binaire RD5, assemblé dans une RD5 locale pour le calcul.
2. Les chemins OSM, les chemins officiels avec leur source, et les
   franchissements finalisés. Le prototype publie deux JSON gzip par maille,
   un pour OSM et un pour la source nationale. Le serveur lit les mailles qui
   touchent la vue, élimine les objets hors de la vue et déduplique ceux qui
   traversent une limite. Un index spatial interne à chaque fichier reste à
   étudier si la lecture devient trop coûteuse.

Une seule RD5 ne suffit pas : elle ne conserve pas directement la distinction
des sources ni les attributs d'affichage et de franchissement dont l'application
a besoin. Un seul **paquet logique** par 0,25° peut toutefois référencer les deux
fichiers et leurs empreintes SHA-256. Les fonds de carte gardent leur propre
système de tuiles et ne sont pas inclus dans ce paquet.

## Mesures et preuve de format

La RD5 OSM `E5_N40` présente dans la VM fait **69 262 700 octets**. Parmi ses
25 sous-cases, 18 sont non vides ; la plus grosse fait **12 027 364 octets**.
Le script `deploy/linux/rd5_shards.py` l'a découpée puis reconstituée : le
SHA-256 du résultat est identique à celui de la RD5 d'origine
(`842dc85e462bb1739041b1f6306d44b300e6413d5c41c311ae5a2eee0f8342e9`).
Une recomposition avec quatre sous-cases pèse 23 841 378 octets. Cela prouve le
découpage et l'indexation binaire.

Le prototype `deploy/linux/rd5_quarts.py` descend au **quart de degré** :
200 lots non vides sur 400 positions, le plus gros faisant **1 941 006
octets**. La recomposition de tous les lots donne encore exactement le même
SHA-256 que la RD5 d'origine. La RD5 reconstruite avec le seul lot contenant
Garéoult fait **546 946 octets**, et le BRouter réel a calculé le trajet témoin
dans cette maille. Un essai vers un point hors de sa couverture a rendu « point
d'arrivée isolé » : le contrôle préalable de couverture est une condition
fonctionnelle, pas seulement une optimisation.

La tentative `osmium extract --strategy complete_ways` de la France vers
`E5_N40` a dépassé la RAM de la VM (3,3 Gio disponibles, aucun swap initial).
Une seconde tentative avec 6 Gio de swap temporaire a été lancée. Le serveur
ne doit pas indexer toute la France pour une seule RD5 : le PBF de 4,8 Gio est
conservé comme source réutilisable, les 12 Gio d'index national partiel ont
été effacés. À terme, l'import doit être borné par case et pouvoir reprendre
sans recommencer les autres cases.

La seconde tentative a réussi en **10 min 21 s**, avec **2,5 Gio de RAM** et
**2,6 Gio de swap** au pic. Le PBF `E5_N40` extrait de France fait **373 Mo**.
Le créateur BRouter a ensuite produit la RD5 principale en **2 min 31 s**,
avec **2 Gio de RAM** au pic et **32 073 783 octets** de RD5 `E5_N40` ; les
intermédiaires de fabrication ont été effacés après succès. Cette RD5 est
**OSM seul et limitée à l'extrait France** : elle sert à dimensionner le job,
pas encore à publier un paquet complet pour cette case.

Le même PBF borné a été indexé localement en **3 min 04 s** :
**1 035 442 voies**, **0,34 Gio** de SQLite final, **1,1 Gio** de RAM au pic.
L'index permet de relire les petites mailles OSM de la case sans redemander
Overpass ni reparcourir les 373 Mo de PBF pour chaque maille.

Deux fabrications indépendantes OSM + BD TOPO ont été faites sur les mailles
`[43,25 ; 6,00 ; 43,50 ; 6,25]` et `[43,25 ; 6,25 ; 43,50 ; 6,50]`, avec un
halo de 0,05° pour lire les raccords. La première a lu 43 327 voies OSM et
54 613 tronçons IGN, conservé 12 196 chemins IGN nouveaux, calculé 253
franchissements et produit une RD5 de 1 456 360 octets en **50 s** (pic RAM
1,1 Gio). Le fragment distribuable ciblé fait environ **600 Ko** et sa RD5
reconstituée **618 092 octets**. Un trajet local a réussi avec et sans les
coupes des franchissements. La maille est lue depuis l'index OSM et le RTree
IGN, sans Overpass ni WFS.

La seconde a conservé 16 342 chemins IGN nouveaux et calculé 241
franchissements en **56 s** (pic RAM 1 Gio). `rd5_mosaic.py` a assemblé les
deux fragments sélectionnés en une RD5 de **1 248 993 octets**. Le BRouter
réel a calculé un trajet de **86 m franchissant le méridien 6,25°** sur un
chemin OSM, avec et sans les coupes strictes des deux mailles. Ce test
montre qu'une frontière entre **ces deux** fabrications se raccorde. Il reste
à tester les chemins officiels qui franchissent la frontière, les coins de
quatre mailles, une limite de RD5 et les autres providers.

Les calques de ces deux mailles ont ensuite été publiés directement depuis
l'index OSM local et le GeoPackage IGN. Une première publication contenait
aussi les routes carrossables : **1 452 101** et **1 682 730 octets** gzip côté
OSM, **2 189 983** et **2 029 314 octets** côté IGN. Les calques ont été
épurés pour ne garder que les chemins et pistes OSM, les chemins, sentiers,
escaliers et routes empierrées IGN, les barrières OSM et les franchissements
bloquants ou à vérifier. Les routes restent disponibles dans les données RD5
servant au calcul. Les fichiers réduits font **823 449** et **867 995 octets**
pour OSM, **1 603 709** et **1 534 541 octets** pour IGN, soit une réduction
de 24 à 48 % selon la source et la maille. Dans la première maille, cela
représente 6 788 voies OSM (2 698 sentiers et 4 090 pistes), 278 barrières,
253 franchissements et 16 971 chemins IGN (8 144 chemins, 5 080 routes
empierrées, 3 657 sentiers, 90 escaliers). Les 253 franchissements sont
conservés dans le fichier OSM pour générer les coupes BRouter ; la copie en
double a été retirée du fichier IGN. La vue `[43,30 ; 6,24 ; 43,31 ; 6,26]`,
à cheval sur la limite, renvoie **1 035 chemins OSM**, **33 barrières**,
**18 franchissements** et uniquement les chemins IGN. L'application de bureau
a obtenu ces réponses du service de la VM par un tunnel SSH. Une maille absente
produit une erreur explicite : elle ne donne pas un calque vide trompeur.

Le paquet de routage **format 2** distribue à présent les fragments `.rd5q`,
un manifeste de 400 positions avec leurs empreintes, les franchissements
finalisés, le profil et les chemins officiels. La publication est effectuée
par SSH à partir d'une mosaïque vérifiée et refuse les trous dans la couverture
rectangulaire. Le serveur conserve une RD5 reconstruite pour le calcul de
secours, mais l'API ne la livre pas au client. Bureau et Android téléchargent
les seuls fragments du paquet, contrôlent SHA-256, puis recomposent localement
une RD5 utilisable par BRouter. Le serveur ne fabrique rien sur requête.
La VM a livré **deux fragments pour 1 245 096 octets** ; le client a reconstruit
une RD5 de **1 248 993 octets**, identique octet pour octet à la référence, et
calculé localement un itinéraire strict de **109 m** franchissant leur limite.
Le téléchargement partiel HTTP `Range` d'un fragment renvoie bien `206`.

Le contour OSM France du Var touche **25 mailles** de 0,25° ; le contour
Geofabrik de la France métropolitaine en touche **1 608**. Au volume mesuré
sur les deux mailles témoins (environ 3,04 Mo par maille pour RD5q et calques
compressés après épuration), cela représente **environ 76 Mo pour le Var et
4,9 Go pour la France** de produits distribuables. C'est une extrapolation, pas une mesure
nationale : elle exclut les PBF/GeoPackage sources, les fichiers de secours
et la variation de densité des chemins.

Le bureau conserve les réponses des calques cloud dans
`cloud-paquets/calques/<serveur>/<calque>/`. La zone reçue est comprimée en
gzip et relue depuis ce cache avant affichage, y compris hors connexion.
Elle est redemandée après 24 heures si le serveur répond ; les paquets RD5
restent dans les autres sous-dossiers de `cloud-paquets`. Les caches locaux
Overpass, des providers et BRouter restent séparés. Le fond cartographique
utilise toujours le cache HTTP du navigateur. L'API
`/api/mailles-disponibles` donne l'inventaire des quarts publiés (OSM,
source nationale, itinéraire) ; une case des réglages dessine ce quadrillage
sur la carte. L'indicateur de calque affiche la provenance effective
`cloud` ou `local`, sans distinguer la lecture du cache cloud.

## Étapes de validation avant généralisation

1. Produire une RD5 **complète** sur une case témoin, avec tout l'OSM de sa
   case, y compris les pays voisins, et les chemins nationaux présents. Une
   RD5 issue du seul extrait France ne serait pas complète dans les portions
   italiennes ou espagnoles de sa case.
2. Étendre l'essai de raccord aux chemins officiels, aux coins de quatre
   mailles et aux limites de RD5 ; vérifier les identifiants synthétiques,
   les chemins et les franchissements après assemblage.
3. Mesurer la durée de téléchargement sur mobile et le coût de lecture des
   JSON gzip. Grouper les téléchargements des mailles voisines pour limiter
   le nombre de requêtes ; conserver l'assemblage local atomique.
4. Relier les mailles publiées en paquets de couverture rectangulaire et
   conserver l'historique lors du remplacement. Le format 2 actuel publie
   atomiquement chaque paquet et contient les empreintes RD5q ; un catalogue
   national commun aux calques et aux fragments reste à faire.

Références : [format et génération des RD5](https://github.com/abrensch/brouter/blob/master/docs/developers/build_segments.md),
[extraction OSM et coût mémoire](https://docs.osmcode.org/osmium/latest/osmium-extract.html).
