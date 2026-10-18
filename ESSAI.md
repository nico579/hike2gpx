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
