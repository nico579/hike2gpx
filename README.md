# hike2gpx

hike2gpx trace un itinéraire de randonnée sur un fond IGN (SCAN 25, Plan IGN
ou photos aériennes) sans traverser les clôtures, barrières et interdictions
que décrit OpenStreetMap, puis l'exporte en GPX.

Les planificateurs courants, Visorando, Locus Map, brouter-web, ne voient pas
une clôture dessinée en ligne qui coupe un sentier. Ce n'est pas un oubli de
leur part : leurs moteurs de calcul ne lisent que les étiquettes posées sur les
nœuds du chemin, et une clôture est une ligne à part. hike2gpx examine
d'avance le réseau de la zone, repère chaque croisement entre un chemin et une
barrière, le juge, puis interdit ou décourage son passage. À Garéoult (Var),
le profil Randonnée standard de BRouter franchit une clôture en béton pour un
trajet de 69 m ; hike2gpx la contourne par un détour de 435 m.

Version 0.1.0 : premier prototype pour ordinateur. Le téléphone viendra plus
tard, par l'application BRouter pour Android.

## Comment ça marche

Le calcul passe par cinq pièces.

1. **Les franchissements.** Pour la zone du tracé, hike2gpx lit dans
   OpenStreetMap (par Overpass, en tuiles de 0,05° gardées sept jours) les
   chemins praticables à pied, les barrières dessinées en ligne, les nœuds
   barrière et les itinéraires de randonnée balisés. Chaque croisement est jugé
   **bloquant**, **à vérifier** ou **franchissable**, avec les règles de
   [gpx2elev](https://github.com/nico579/gpx2elev), recopiées telles quelles
   dans `regles.py` : une clôture traversée sans ouverture cartographiée
   bloque, un portail sans indication d'accès est à vérifier, `foot=yes` prime
   sur `access=private`, des horaires ou des conditions laissent un doute.
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
   [nico579-commons](https://pypi.org/project/nico579-commons/) : on clique
   pour poser le départ, les étapes et l'arrivée, on déplace les points, et
   l'on exporte le GPX, avec en points de passage les franchissements à
   vérifier sur le tracé. Le tracé standard, qui ignore les barrières, peut
   s'afficher en pointillé pour comparaison. Deux calques à cocher, à partir
   du zoom 14, montrent les chemins que connaît OpenStreetMap (avec ses
   clôtures et murs) et ceux de la BD TOPO de l'IGN : de quoi comparer les
   deux sources.
4. **Le dénivelé.** Une fois l'itinéraire affiché, le moteur de
   [gpx2elev](https://pypi.org/project/gpx2elev/) recalcule son dénivelé :
   tracé échantillonné tous les 5 m, meilleur modèle de terrain disponible
   (IGN LiDAR HD d'abord), lissage gaussien de 20 m, hystérésis de 2 m. Le
   chiffre de BRouter, tiré d'un modèle mondial plus grossier, ne sert que
   d'estimation en attendant.
5. **Les chemins IGN.** Un sentier que la BD TOPO connaît et qu'OpenStreetMap
   ignore n'existe pas pour BRouter, qui ne voit que ses tuiles. hike2gpx
   fabrique donc sa propre tuile BRouter à partir des données déjà lues : les
   voies d'OpenStreetMap, plus les tronçons de la BD TOPO qui n'en doublent
   aucune, raccordés au réseau. La tuile grossit au fil des zones consultées,
   jusqu'à 25 tuiles de 0,05° avant de repartir de la zone demandée, et ne se
   refait que pour une zone nouvelle ou des données relues, en six secondes
   environ pour neuf tuiles. Les franchissements se cherchent
   alors sur le réseau fusionné : un sentier OSM et un chemin IGN arrêtés de
   part et d'autre d'une clôture, une fois raccordés, la traversent. Ces
   chemins coûtent un peu plus que les autres, s'affichent en tirets orange
   sur l'itinéraire et rejoignent les points à vérifier, car rien ne dit
   qu'ils existent encore ni qu'on y passe ; un accès piéton restreint dans la
   BD TOPO les ferme. Une case permet de s'en passer, et si la fabrication
   échoue, le calcul se fait sur OpenStreetMap seul, avec un avertissement.

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

## Limites

hike2gpx ne peut éviter que ce qui est cartographié. Autour de Garéoult, sur
250 km², OpenStreetMap ne recense que 18 clôtures, et la BD TOPO de l'IGN
aucune (voir [ESSAI.md](ESSAI.md)). Une clôture rencontrée sur le terrain et
ajoutée à OpenStreetMap est respectée par hike2gpx dès que son cache de la
zone se renouvelle ; les moteurs des autres planificateurs, eux, continuent de
l'ignorer.

Un calcul examine au plus 100 tuiles de 0,05°, soit environ 55 × 40 km : la
première lecture d'une zone plus grande prendrait des dizaines de minutes. Un
long parcours se découpe en étapes.

## Installation

Il faut Python 3.12, [uv](https://docs.astral.sh/uv/) et Java 11 ou plus pour
BRouter.

```
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -e ".[test]"
.venv\Scripts\hike2gpx installer E5_N40
.venv\Scripts\hike2gpx serve
```

`installer` télécharge BRouter 1.7.10 (archive vérifiée par son empreinte
SHA256) et la tuile de données qui couvre la zone : E5_N40 pour la Provence,
de 5° à 10° E et de 40° à 45° N. La page propose aussi ces téléchargements par
un bouton. Les données vont dans le dossier d'état standard
(`%LOCALAPPDATA%\hike2gpx-data` sous Windows), ou dans celui que désigne la
variable `HIKE2GPX_HOME`.

Le SCAN 25 n'est pas une donnée libre : il demande une clé IGN, à saisir dans
les réglages de la page. Sans clé, la carte utilise le Plan IGN, sous Licence
Ouverte.

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
Node, quand Node est installé. Les outils de `tools/` rejouent l'essai décrit
dans [ESSAI.md](ESSAI.md).

## Licence

GPL-3.0-or-later. BRouter (MIT) est téléchargé à l'installation ; Leaflet 1.9.4
(BSD-2-Clause) est fourni dans `hike2gpx/assets/web/leaflet`. Données ©
contributeurs OpenStreetMap (ODbL), y compris l'extrait de test
`tests/donnees/gareoult_cloture.json` ; BD TOPO © IGN (Licence Ouverte) ;
cartes © IGN.
