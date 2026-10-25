# Mailles calculées et téléchargées

## Décision et limites de BRouter

BRouter ouvre une **RD5 nommée par une case de 5° × 5°**. Il sait calculer un
itinéraire qui traverse plusieurs RD5. À l'intérieur d'une RD5, son index
contient **25 sous-cases de 1° × 1°** ; chacune contient une grille de
**32 × 32 microcaches** (pas de 0,03125°). Le moteur lit les données par
microcache. Ces trois niveaux ont des rôles différents :

| Niveau | Usage prévu |
| --- | --- |
| 5° | Nom de fichier et couverture que BRouter reconnaît ; fabrication au plus d'une RD5 par job serveur. |
| 1° | Premier lot de distribution et de cache sur l'appareil ; assemblage local en RD5. |
| 0,03125° | Plus petite unité binaire ; candidat à une distribution ultérieure si les requêtes et l'assemblage restent efficaces. |

Une RD5 recomposée avec certaines sous-cases absentes est techniquement lisible,
mais BRouter traite ces sous-cases comme vides. **Le manifeste doit donc
enregistrer la couverture réellement téléchargée et le client doit refuser un
calcul qui pourrait sortir de cette couverture.** Une marge fixe autour des
points ne garantit pas tous les détours possibles. En ligne, le client pourra
charger les sous-cases manquantes et recommencer ; hors ligne il devra annoncer
que les données du parcours sont insuffisantes. L'affichage ne doit jamais
présenter une absence de données comme une absence de chemin.

## Même grille pour les sources et les calques

Le serveur affecte chaque tronçon et chaque franchissement à une sous-case de
1° selon une règle d'appartenance stable. Il lit également une **couronne de
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

Pour l'application, un lot de 1° contiendra deux produits de la même édition :

1. Le fragment binaire RD5, assemblé dans une RD5 locale pour le calcul.
2. Un fichier de données **indexé spatialement**, contenant chemins OSM,
   chemins officiels avec leur source, et franchissements finalisés. Le client
   interrogera uniquement l'emprise visible pour le calque et la zone du
   parcours pour les coupes BRouter. Un SQLite avec RTree et coordonnées WGS84
   reste un candidat ; son schéma et sa taille doivent être mesurés sur un lot.

Une seule RD5 ne suffit pas : elle ne conserve pas directement la distinction
des sources ni les attributs d'affichage et de franchissement dont l'application
a besoin. Un seul **paquet logique** par 1° peut toutefois référencer les deux
fichiers et leurs empreintes SHA-256. Les fonds de carte gardent leur propre
système de tuiles et ne sont pas inclus dans ce paquet.

## Mesures et preuve de format

La RD5 OSM `E5_N40` présente dans la VM fait **69 262 700 octets**. Parmi ses
25 sous-cases, 18 sont non vides ; la plus grosse fait **12 027 364 octets**.
Le script `deploy/linux/rd5_shards.py` l'a découpée puis reconstituée : le
SHA-256 du résultat est identique à celui de la RD5 d'origine
(`842dc85e462bb1739041b1f6306d44b300e6413d5c41c311ae5a2eee0f8342e9`).
Une recomposition avec quatre sous-cases pèse 23 841 378 octets. Cela prouve le
découpage et l'indexation binaire ; le routage sur une RD5 incomplète et la
politique de couverture demandent encore des essais.

La tentative `osmium extract --strategy complete_ways` de la France vers
`E5_N40` a dépassé la RAM de la VM (3,3 Gio disponibles, aucun swap initial).
Une nouvelle tentative avec 6 Gio de swap temporaire est en cours. Le serveur
ne doit pas indexer toute la France pour une seule RD5 : le PBF de 4,8 Gio est
conservé comme source réutilisable, les 12 Gio d'index national partiel ont
été effacés. À terme, l'import doit être borné par case et pouvoir reprendre
sans recommencer les autres cases.

## Étapes de validation avant généralisation

1. Produire une RD5 **complète** sur une case témoin, avec tout l'OSM de sa
   case, y compris les pays voisins, et les chemins nationaux présents. Une
   RD5 issue du seul extrait France ne serait pas complète dans les portions
   italiennes ou espagnoles de sa case.
2. Tester un itinéraire qui franchit deux sous-cases puis deux RD5, vérifier
   que le nombre de chemins et les franchissements ne changent pas après
   découpage et assemblage.
3. Mesurer la taille de l'index de calques par 1° et la durée de téléchargement
   sur mobile. Étudier des paquets plus fins (par exemple 0,25°) seulement si
   l'économie de bande passante dépasse le coût des requêtes et du nouvel
   assemblage des microcaches.
4. Publier un manifeste de version commun aux RD5, calques et franchissements,
   avec couverture, empreintes et état `complet`. Ne rendre visible que la
   version entièrement préparée ; garder l'ancienne pendant le remplacement.

Références : [format et génération des RD5](https://github.com/abrensch/brouter/blob/master/docs/developers/build_segments.md),
[extraction OSM et coût mémoire](https://docs.osmcode.org/osmium/latest/osmium-extract.html).
