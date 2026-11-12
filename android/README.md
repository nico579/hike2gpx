# Application Android

Le téléphone ne fabrique rien : il prend les lots hors ligne que le serveur
publie sur GitHub (le dépôt nico579/hike2gpx-bundles), ou ceux d'un PC du
réseau local, et calcule l'itinéraire lui-même avec BRouter, sans réseau.

## Ce qu'elle fait

L'écran est celui de la page du PC : la carte d'abord, en plein écran. Un
bouton à trois traits, en bas à gauche, ouvre le menu : « Recherche », « Ma
bibliothèque », « Gestion des cartes », « Gestion des itinéraires »,
« Enregistrer un parcours », « Planifier un itinéraire », « Réglages » et
« Aide ». La carte reste seule tant qu'on n'a pas choisi un mode ; « Aide »
ouvre ce mode d'emploi sur GitHub. Le panneau laisse voir la carte derrière, et
sa poignée du haut se glisse vers le bas pour le refermer. En planification, on
touche la carte pour poser le départ, puis l'arrivée et d'éventuelles étapes ; « Retirer » retire le
dernier point, « Effacer » les retire tous, et « Revenir » ajoute le départ en
fin de parcours pour fermer une boucle. Dès qu'il y a deux points, l'itinéraire
se calcule hors ligne et s'affiche. Un bouton rond rouge au carré, comme celui
de la trace, arrête la planification et propose d'enregistrer le parcours en
GPX ; un second choix de « Planifier un itinéraire » le fait aussi. Les doigts
verts des points disparaissent alors : seule la trace GPX reste sur la carte,
sans être effacée.

Le menu « Recherche » ouvre le champ de la page : il recentre la carte sur
une ville ou sur des coordonnées « lat, lon », sans poser de point. Les
communes françaises répondent d'abord (geo.api.gouv.fr, avec leur
département) ; ailleurs, ou si la France ne connaît rien, Nominatim donne les
villes et villages d'OSM avec leur région et leur pays. Une seule réponse
recadre aussitôt, plusieurs se choisissent dans une liste ; le bandeau de
recherche se referme ensuite, et un tap sur la carte le referme aussi. Le menu
« Recherche » reste disponible en planification ;
pendant l'enregistrement, seul l'état de la trace s'affiche.

Les calques du lot s'affichent sur la carte, comme ceux de la page : les
chemins OSM (sentiers en tirets violets, pistes et routes) avec les barrières
qui gênent un piéton et les franchissements bloquants (rouge) ou à vérifier
(orange), et les chemins du fournisseur national retenu par le lot du secteur
(BD TOPO en France, turquoise), avec sa coche dans la page « Gestion des
cartes » (« IGN », « ATKIS »…), proposée seulement quand ce lot est là. Ils
n'apparaissent qu'à
partir du zoom 14, celui des tuiles vectorielles du lot : en dessous, mieux
vaut ne rien montrer qu'un réseau tronqué. La page rappelle le zoom
courant ; une coche sous ce zoom, ou une vue sans chemin de calque, le dit
plutôt que de laisser croire que la case ne marche pas. Les calques sont lus dans
`calques.mbtiles` (MVT) en arrière-plan, sans gêner le calcul de l'itinéraire ;
un lot ancien qui n'a pas ce fichier n'affiche simplement rien.

Sous la distance, l'itinéraire donne aussi le dénivelé et la durée de marche,
calculés sur un modèle de terrain : altitude échantillonnée tous les 5 m,
lissage gaussien de 20 m, D+/D− avec une hystérésis de 2 m, puis modèle de
Tobler tous les 20 m. Avec le réseau, le MNT IGN LiDAR HD de la Géoplateforme
passe d'abord ; s'il ne couvre pas tout le parcours (hors de France, en mer),
ou sans réseau, Mapterhorn (tuiles Terrarium du zoom 12) est rapatrié à la
demande et gardé en cache ; une tuile déjà là sert aux parcours suivants. Le
PC lit Mapterhorn au zoom 13 : l'écart mesuré sur le D+ reste sous 1 %.
Le calcul du relief est séparé de celui de l'itinéraire : le tracé s'affiche
d'abord, le dénivelé arrive ensuite. Sans relief disponible, la ligne le dit et
la valeur BRouter ne le remplace pas, comme sur le PC. Les bandeaux de
planification et d'enregistrement ne montrent pas de champ de recherche : la
carte, l'état et les commandes suffisent. La légende, elle, reste en haut à
droite si « Afficher la légende » est cochée, dans le même ordre que celle du
PC. La coche « Afficher courbe du
dénivelé » dessine au-dessus des boutons le profil de la page — distance en
abscisse, altitude lissée en ordonnée, aire bleue et bornes d'altitude. La courbe
n'apparaît qu'une fois le relief calculé ;
décochée, elle laisse toute la carte. Comme sur la page, poser le doigt sur la
courbe montre le point du tracé correspondant : un trait vertical, la distance
et l'altitude sous le doigt, et un disque bleu cerclé de blanc sur la carte.
Lever le doigt efface les deux.

Un double tap sur la carte masque les deux bandeaux et
laisse la carte seule ; un second double tap les ramène. L'échelle et
l'attribution OSM restent visibles : elles font partie de la carte.

Les deux boutons ronds du bas, à gauche, sont alignés à l'horizontale et
semi-transparents : celui à trois traits ouvre le menu, et celui de la position
recentre la carte sur le GPS, avec le point bleu et son halo de précision. Le
démarrage d'une trace passe par « Enregistrer un parcours » : pendant
l'enregistrement, un bouton rond rouge apparaît en bas à droite pour arrêter
(carré) sans rouvrir le menu, et le GPX est rangé dans
`traces/`, avec l'heure et l'altitude de chaque point. La page « Gestion des
itinéraires » règle l'enregistrement : distance minimale entre deux points
(10 m), durée minimale (10 s) et déviation GPS maximale (100 m). Un point n'est
retenu que si le GPS est plus précis que la déviation, et si la distance et la
durée depuis le point précédent sont toutes deux atteintes ; le premier point
n'a que la précision à respecter. Un changement de réglage s'applique au point
suivant, même pendant un enregistrement. La localisation n'est demandée qu'au
premier appui sur le bouton de position ou au démarrage d'une trace, jamais au
lancement. La trace enregistrée s'affiche en orange, au-dessus de l'itinéraire
bleu.

La trace continue écran éteint, téléphone en poche ou application fermée : un
service de premier plan (type `location`) tient le GPS, avec
une notification « Trace GPS en cours » qui rouvre l'application. Sans lui,
Android ne donne plus que quelques positions par heure à une application en
arrière-plan. Pour ménager la batterie, il ne demande que le GPS, sans le
réseau, et au rythme des réglages de la trace (10 s par défaut) plutôt que
chaque seconde : écran éteint, chaque position reçue réveille le processeur.
Chaque point retenu est aussi écrit aussitôt dans
`traces/<trace>.gpx.journal` et synchronisé sur disque : si Android tue
l'application ou si la batterie lâche, le GPX est refait au lancement suivant,
avec un message « Trace interrompue récupérée ». Sur Android 13 et plus, le
premier enregistrement demande aussi d'autoriser les notifications ; un refus
cache la notification sans arrêter la trace.

Pendant l'enregistrement, le bandeau donne la distance, la durée et le dénivelé
D+/D− calculé sur le modèle de terrain. Le calcul ne lit que le cache de
relief : en randonnée, le téléphone n'a pas de réseau. Si le cache ne couvre pas
encore le parcours, le dénivelé reste absent du bandeau, sans arrêter la trace.
À l'export, le GPX est relu et les altitudes sont remplacées par celles du
modèle de terrain : IGN LiDAR HD si le réseau est là et qu'il couvre la trace,
sinon Mapterhorn, son cache d'abord, puis le réseau s'il le faut ; sans relief
complet, le fichier part tel qu'il a été enregistré. Le D+ du bandeau, lu
hors ligne sur Mapterhorn, peut donc différer de quelques mètres de celui de
l'export. La description du GPX porte alors le D+ et le D− du relief.

« Ma bibliothèque », dans le menu, liste l'historique des traces : chaque
fichier de `traces/` affiche sa date et sa taille réelle, avec un bouton
« GPX » pour le réexporter et un bouton « Supprimer ». Les cases à cocher et
« Supprimer la sélection » effacent plusieurs traces d'un coup, après
confirmation. « Vider le cache » ne touche pas à cet historique.

Les lots du serveur se téléchargent d'eux-mêmes : l'application lit les
catalogues à son lancement, et quand un parcours touche une case dont le lot
manque, ou dont le dépôt a une édition plus récente, ce lot part aussitôt.
S'arrêter sur une région compte aussi comme un usage : une recherche de ville,
un recentrage sur la position GPS, ou l'affichage d'un calque du lot au zoom
14 proposent aussitôt le lot de la case du centre, sans attendre un geste sur
la carte. Sur le Wi-Fi, sans rien demander ; sur un
réseau facturé (données mobiles), après confirmation. Un échec ou un refus
n'est pas repris avant une heure, et un lot supprimé à la main ne revient pas
de la séance. Les lots et les fonds installés affichent leur taille réelle,
jamais un « 0 Mo » trompeur.

La page « Gestion des cartes », dans le menu, réunit tout ce qui touche au fond
et aux chemins, sorti des réglages. On y choisit le fond dans « En ligne » : les
mêmes cartes que la page du PC. Les cartes nationales proposées suivent le pays
du centre de la carte : en France le Plan IGN par défaut, le SCAN 25 (IGN), les
photos aériennes (IGN) et le relief LiDAR HD (IGN) ; en Suisse la carte
swisstopo, en Allemagne la carte du BKG, en Autriche basemap.at, en Tchéquie
ČÚZK, en Espagne l'IGN, au Luxembourg l'ACT, aux Pays-Bas PDOK, en Norvège
Kartverket, aux États-Unis l'USGS et en Pologne le Geoportal. OpenTopoMap,
OpenStreetMap et le satellite (Esri) servent partout. Une carte nationale suit
le pays : en passant en Suisse, le Plan IGN laisse la place à swisstopo, et
hors des pays couverts la carte revient à OpenStreetMap. Un fond du monde
(OpenStreetMap, OpenTopoMap, satellite) ou un fond hors ligne reste en place
quand on change de pays. Le SCAN 25 n'est pas une donnée libre : il
n'apparaît qu'une fois la clé IGN renseignée dans les réglages, et sans elle la
carte reste sur le Plan IGN. Les cartes reçues d'un PC (le SCAN 25 ou le Plan
IGN qu'il a fabriqués, ou sa carte OpenStreetMap vectorielle) forment le
chapitre « Hors ligne », après « En ligne ». Une seule carte est choisie :
cocher une carte d'un chapitre décoche celle de l'autre, même quand elles
portent le même nom. Les fonds qu'un PC partage et qui manquent au téléphone y
sont proposés, avec leur taille et un bouton de téléchargement ; le QR code du
PC (« Partager au téléphone » dans ses réglages) l'ajoute, sur le même Wi-Fi.
« Superposition des chemins » coche les chemins OSM, toujours proposés, et ceux
du fournisseur national du lot qui couvre la vue (IGN, ATKIS…) : la coche du
pays n'apparaît que si ce lot est installé, et elle ne suit que le pays
affiché, pas les autres fournisseurs d'un lot frontalier (à Genève,
swissTLM3D, pas l'IGN) ; elle disparaît dès que la carte sort de sa zone. En fin
de page, « Zones stockées localement » liste les fonds installés avec leur
taille et « Supprimer », après confirmation ; si le fond supprimé était
affiché, la carte revient en ligne. Un fond est un MBTiles rangé sous
`hors-ligne/fonds/`, comme sur le PC ; une carte OpenStreetMap vectorielle y
est un fichier `.map` Mapsforge. Tous ceux d'une même source s'affichent
ensemble, et la carte agrandit les MBTiles au-delà de leur zoom le plus fin. Le
bandeau de planification ne garde que « Retirer », « Effacer » et « Revenir ».

La page « Gestion des itinéraires », dans le menu, réunit le calcul et
l'enregistrement, sortis des réglages. « Mode de calcul » y coche « Inclure les
blocages à vérifier » et les chemins officiels, nommés d'après les lots
installés (« Inclure les chemins IGN », « ATKIS »…). « Télécharger depuis
l'ordinateur » propose les zones que seul un ordinateur calcule, avec « Scanner
le QR code de l'ordinateur » ; un lot est pris au premier PC qui le sert, et un
PC éteint ne bloque rien. Le volet « Enregistrement de trace GPS » y règle la
distance minimale, la durée minimale et la déviation GPS maximale. En fin de
page, « Zones stockées localement » liste les zones installées avec leur taille,
« Mettre à jour » quand le serveur en a une plus récente et « Supprimer » après
confirmation, sans décaler les réglages du dessus quand la liste s'allonge. Les réglages
ne gardent que l'affichage, la clé IGN, le cache et la mise à jour ; « Vider le
cache » efface comme sur le PC les lots, les fonds, les téléchargements
interrompus, les
tuiles en ligne gardées et les tuiles de relief ; les lots du serveur reviennent
d'eux-mêmes.

L'application parle anglais ou français selon la langue du téléphone. Les deux
versions portent les mêmes textes et les mêmes arguments.

## Mise à jour

L'application se met à jour depuis les releases GitHub. Au lancement, et à la
demande dans les réglages (« Vérifier les mises à jour »), elle cherche une
version plus récente et la propose. L'APK est téléchargé en HTTPS, vérifié par
sa taille, son empreinte SHA-256, son paquet, sa version et sa signature, puis
confié à l'installateur d'Android. La première fois, Android demande
l'autorisation d'installer des applications ; la mise à jour reprend au retour.
Les lots, les fonds et les réglages sont conservés.

Le catalogue des lots décrit chaque fichier avec sa taille et son empreinte
SHA-256. Un lot se télécharge fichier par fichier ; une coupure reprend là où
elle s'est arrêtée, et chaque fichier est contrôlé, puis le lot entier une
seconde fois à l'installation. Les fichiers sont rangés ainsi :

```text
hors-ligne/segments/E5_N40.rd5          RD5 des lots enrichis
hors-ligne/segments-osm/E5_N40.rd5      RD5 officielles des lots OSM
hors-ligne/E5_N40/manifest.json, franchissements.json.gz, calques.mbtiles
```

Les tuiles de relief sont gardées en cache, à la racine des fichiers de
l'application, sous le même nom que sur le PC (`mapterhorn_12_x_y.webp`) : un
cache recopié d'un PC sert tel quel.

Le calcul suit la même règle que la page du PC : un parcours dont la zone tient
dans un lot se calcule sur ce lot seul. Les franchissements de la zone
deviennent des coupes dans BRouter (interdites ou pondérées), la zone s'élargit
si le tracé en sort, et un dernier contrôle refuse un tracé qui passerait encore
une coupe interdite. Le tracé s'exporte en GPX.

BRouter 1.7.10 est compilé dans l'APK, avec ses profils de randonnée.

## Un PC pour les fonds et les lots

Le PC affiche un QR code qui porte un lien
`hike2gpx://depot?url=<adresse du catalogue, encodée>&jeton=<jeton>`.
L'appareil photo du téléphone l'ouvre dans l'application (le lien est déclaré
dans le manifeste Android), qui demande confirmation avant d'ajouter le PC.
Toutes les requêtes vers ce PC portent
`Authorization: Bearer <jeton>`, et seulement vers l'origine de son catalogue.
Le HTTP simple n'est accepté que vers le réseau local.

Les lots du serveur se lisent sur GitHub au lancement et se téléchargent
d'eux-mêmes. Un PC sert au téléphone ses fonds de carte (MBTiles) et ses
cartes vectorielles OpenStreetMap (`.map` Mapsforge), plus les lots de routage
qu'il a calculés : son catalogue ne se lit qu'à la demande, sur les pages
Cartes et Itinéraires ou quand on ajoute le PC, si bien qu'un PC éteint ne
retarde jamais le lancement. Les lots d'un PC ne sont proposés que s'ils
manquent au téléphone et au catalogue GitHub, qui les publie déjà.

## Construire

```text
git submodule update --init android/brouter
powershell -File android/build-local.ps1
```

Le script lance les tests unitaires puis construit l'APK, avec le JDK et le SDK
d'Android Studio. Le workflow GitHub fait de même à chaque demande de fusion
qui touche `android/`.
