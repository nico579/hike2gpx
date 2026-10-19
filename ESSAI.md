# Essai du 18 octobre 2026 autour de Garéoult

L'essai devait répondre à trois questions avant d'aller plus loin : les
franchissements calculés sont-ils justes, BRouter les évite-t-il vraiment, et
combien de clôtures OpenStreetMap connaît-il là où l'on randonne ?

## Zone

Neuf tuiles de 0,05°, de 43,25° à 43,40° N et de 5,95° à 6,10° E, soit environ
250 km² autour de Garéoult. Lecture Overpass : 25 à 37 s par tuile la première
fois, rien ensuite (cache de sept jours, environ 1 Mo par tuile).

## Ce qu'OpenStreetMap connaît

- 4 851 voies praticables à pied ;
- 89 barrières dessinées en ligne : 50 haies, 18 clôtures, 12 murs, 4 murs de
  soutènement, 3 remparts et 2 portails ;
- 97 nœuds barrière ;
- 81 franchissements, dont 23 bloquants et 58 à vérifier.

Les 58 franchissements à vérifier sont surtout des portails sans indication
d'accès (37), puis des barrières levantes (9) et pivotantes (4). Les
23 bloquants sont surtout des portails privés ou interdits (16), deux clôtures
traversées sans ouverture, une clôture privée et un portail verrouillé.

La BD TOPO de l'IGN ne comble pas le manque : sur la tuile de Garéoult, ses
constructions linéaires sont 53 ruines, 52 murs de soutènement, 22 ponts,
1 barrage et 1 mur, sans aucune clôture. Ses 468 haies (contre 20 dans OSM)
ne disent rien des passages.

## Ce que fait le calcul

Pour chaque franchissement bloquant dont le chemin le permettait, deux points
à 60 m de part et d'autre, le long du chemin :

- le profil Randonnée standard de BRouter (celui de brouter-web) ne traverse
  qu'un des huit cas testés : la clôture en béton de la way 1558904264, pour
  un trajet de 69 m ;
- hike2gpx la contourne par 435 m ; les portails privés, BRouter les évitait
  déjà grâce à `access=private` ;
- un cas aboutit à « aucun itinéraire » : les deux points étaient sur une
  piste privée fermée par trois portails interdits, d'où hike2gpx refuse de
  sortir.

Chaque calcul prend de 0,03 à 0,07 s avec une trentaine de coupes ; une
première demande dans une zone nouvelle attend Overpass.

Un cas réel a corrigé la page : un trottoir et un sentier en passage inférieur
croisent la même clôture à 1,3 m l'un de l'autre. Les franchissements « sur le
tracé » se reconnaissent désormais à ce que le tracé coupe leur coupe, et non
à leur simple proximité.

## Rejouer l'essai

Les mesures viennent des outils de `tools/`, données dans `HIKE2GPX_HOME` :

```
$env:HIKE2GPX_HOME = 'D:\hike2gpx'
.venv\Scripts\hike2gpx installer E5_N40
.venv\Scripts\python.exe tools\essai_zone.py 43.25 5.95 43.3999 6.0999
.venv\Scripts\python.exe tools\essai_routage.py 43.25 5.95 43.3999 6.0999 --statuts blocked
.venv\Scripts\python.exe tools\essai_bdtopo.py 43.30 6.00 43.35 6.05
```

Les chiffres suivront les mises à jour d'OpenStreetMap. Le cas de la clôture
en béton, lui, est figé dans `tests/donnees/gareoult_cloture.json` (extrait
par `tools/extraire_cas.py`) et rejoué à chaque lancement des tests par
`tests/test_integration.py`, avec le vrai BRouter : sans les coupes, le
profil hike2gpx franchit la clôture en 93 m ; avec elles, il la contourne.

## Ce qu'on en tire

1. **Le moteur est prêt, les données manquent.** Quand OpenStreetMap connaît
   une clôture, hike2gpx l'évite là où le profil standard la traverse. Mais
   autour de Garéoult il n'en connaît que 18, et aucune donnée ouverte n'en
   décrit davantage. Les clôtures que Locus fait traverser sont sans doute
   absentes d'OSM : aucun logiciel ne peut alors les éviter. Les ajouter à
   OSM (StreetComplete, iD, JOSM) les rend visibles pour hike2gpx dès le
   renouvellement du cache.
2. **Pas de mode strict par défaut.** Il interdirait 58 passages, dont
   37 portails ordinaires : le poids de 300 m, qui évite un portail douteux
   quand un détour court existe, est le bon réglage par défaut ; le mode
   strict reste une case à cocher.
3. **Les nœuds suffisent souvent, les lignes font la différence.** BRouter
   seul gère déjà les portails privés ; ce que hike2gpx apporte, ce sont les
   clôtures en ligne, les portails verrouillés (`locked=yes`, absent de la
   table de BRouter) et les horaires.

# Phase 2, premier essai : un chemin de la BD TOPO dans une tuile BRouter

Le même jour, Nico a buté sur un itinéraire impossible : le seul chemin
entre ses deux points n'existait que dans la BD TOPO. BRouter ne connaît que
les tuiles qu'on lui donne, faites d'OSM ; la phase 2 consiste à fabriquer
nos propres tuiles, OSM plus les chemins IGN qui y manquent.

L'essai (`tools/essai_phase2.py`) le fait sur 2 × 2,4 km à l'est de
Garéoult, autour d'un chemin IGN de 254 m absent d'OSM mais relié au réseau
à ses deux bouts. Le chemin est raccordé par un nœud commun à la voie OSM la
plus proche (à 2,5 m et 0,3 m), puis trois jeux de tuiles sont comparés :

- entre les deux bouts du chemin, 1 028 m sur les tuiles standard comme sur
  nos tuiles OSM seul, **255 m** sur nos tuiles OSM + IGN : BRouter emprunte
  le chemin ajouté ;
- sur un témoin de 2,5 km sans chemin IGN, 4 223 m sur les tuiles de
  brouter.de, 4 158 m sur les nôtres : l'écart (1,5 %) vient des pseudo-tags
  (bruit, forêt, rivière, que le profil de randonnée utilise 30 fois) et du
  relief, absents de nos tuiles ;
- fabrication et itinéraires en 7 s.

Deuxième mesure, à la question de Nico : peut-on fabriquer la tuile au fil
des zones consultées ? Oui. Un fichier `.rd5` n'a pas besoin d'être plein,
et les tuiles Overpass gardées pour les franchissements contiennent tout ce
dont BRouter a besoin (voies avec leurs nœuds numérotés et leur géométrie,
nœuds étiquetés, itinéraires balisés). Sur les neuf tuiles en cache autour
de Garéoult (250 km², 58 359 nœuds, 4 739 voies) : PBF écrit en 0,6 s,
tuile fabriquée en 2,4 s (166 Ko). Mêmes itinéraires que brouter.de sur
2,5 km (4 223 m) et 5 km (5 932 m) : l'écart du premier essai venait des
itinéraires balisés, absents de l'export XML, pas des pseudo-tags. Une
traversée de 12 km diffère encore (23 216 m contre 24 343 m). Ce n'est pas le
relief, que le profil ignore (`consider_elevation=false`) : les deux tracés
ont un coût presque égal (35 320 contre 35 071), et le moindre détail de
données fait basculer le choix. Le relief n'a d'ailleurs pas sa place dans
nos tuiles : c'est gpx2elev qui donne le dénivelé.

# Phase 2 complète : la tuile maison dans hike2gpx (19 octobre)

Les tuiles maison sont désormais le calcul par défaut. Pour la zone d'un
itinéraire, hike2gpx reprend les tuiles Overpass et BD TOPO déjà en cache,
ajoute les tronçons IGN qu'aucune voie OSM ne double (moins de la moitié de
leur longueur à moins de 12 m d'OSM, mesurée tous les 10 m le long de la
ligne), les raccorde, et fait fabriquer la tuile par le créateur de tuiles
de BRouter. Un second serveur BRouter la sert, avec un profil où
`hike2gpx=ign` coûte un peu plus. Mesures sur le PC de Nico, données en
cache :

- le chemin IGN de l'essai (deux tuiles) : préparation en 8,4 s la première
  fois, 0,1 s ensuite ; 255 m dont 254 m sur le chemin IGN, qui ressort à
  vérifier, contre 1 028 m pour le tracé standard sur OSM seul ;
- une traversée de 12 km sur neuf tuiles, fabrication comprise : réponse en
  20,6 s, 16,4 km dont 163 m sur un chemin IGN ;
- sur ces neuf tuiles, 1 908 chemins IGN ajoutés. La fusion prend 14 s,
  l'essentiel du temps ; l'analyse des franchissements du réseau entier,
  0,7 s, et 5 franchissements bloquants y touchent un chemin IGN.

Trois règles de la fusion méritent d'être dites. Les franchissements se
calculent sur le réseau fusionné, pas sur OSM et les chemins IGN pris à
part : un sentier OSM et un chemin IGN arrêtés de part et d'autre d'une
clôture ne la traversent ni l'un ni l'autre, mais leur raccord la traverse
(test `test_integration_maison.py`). Un accès piéton de la BD TOPO autre que
« Libre », « A péage » ou vide ferme le chemin (`foot=private`) ; autour de
Garéoult, sur 10 226 tronçons, on ne trouve que « Libre » (435) et des
valeurs vides. Enfin la part couverte par OSM ne dépend plus du découpage du
tronçon en sommets.

Reste à voir : la fusion est le poste à accélérer si l'on consulte beaucoup
de zones, puisque la tuile les contient toutes et se refait entière à chaque
zone nouvelle.
