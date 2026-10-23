# Sources officielles de chemins pour le calcul BRouter

Rapport du 23 octobre 2026, écrit après la release 0.3.0. En France, hike2gpx ajoute à OpenStreetMap les chemins de la BD TOPO que BRouter ne connaîtrait pas sans elle. La question posée ici est simple : d'autres pays ont-ils une source officielle qui rendrait le même service ? Le rapport y répond par une mesure, puis examine les providers d'affichage par pays et la façon de les organiser.

## Verdict

**L'intérêt est limité hors de France, et la mesure le montre.** Sur les tuiles les plus riches en sentiers de quatre pays, la règle de fusion de hike2gpx garde ce que la source officielle connaît et qu'OSM ignore. En France, la BD TOPO agrandit le réseau routable de 18 % à 100 % ; dans le Var, de 21 % à 72 %. Aux États-Unis, en Suisse et aux Pays-Bas, les sources officielles ajoutent de 0 % à 12 %, et souvent sans dire si l'on peut y passer à pied.

La France n'est pas un cas parmi d'autres : c'est là que se trouve presque toute la valeur. On n'écrira donc pas de connecteur étranger pour l'instant. L'effort ira plutôt à la qualité de la BD TOPO dans hike2gpx. L'Espagne et l'Allemagne, non mesurées faute d'accès simple, restent les seules pistes ouvertes, à condition d'être mesurées avant tout développement.

## La mesure

### Méthode

L'outil `tools/essai_sources_chemins.py` réutilise le code de hike2gpx sans le modifier. Pour chaque massif, il procède en quatre temps.

1. **Trouver une zone dense en chemins.** Une zone pauvre en chemins ne dirait rien : la source officielle et OSM y auraient tous deux peu de chose. L'outil lit donc la source officielle sur la tuile de 0,05° du massif (environ 5,5 × 4 km) et sur ses voisines : 3 × 3 tuiles pour la France et les États-Unis, cinq en croix pour la Suisse et les Pays-Bas, dont les services paginent plus lentement. Il garde la tuile où la source a le plus de kilomètres. En France, seuls les sentiers, chemins et escaliers comptent pour ce classement. Une première passe classée sur toute la BD TOPO avait retenu Fréjus au lieu du massif de l'Estérel : une ville l'emporte sur un massif dès que les routes comptent.
2. **Lire OSM sur cette tuile**, avec 1 km de marge, par la même requête Overpass que le calcul (`franchissements.requete()`), pour ne pas compter comme absent un chemin coupé au bord.
3. **Appliquer la règle de fusion** : un morceau de la source est « nouveau » quand moins de la moitié de sa longueur passe à moins de 12 m d'une voie OSM praticable (`fusion.parts_couvertes()`, seuil `PART_COUVERTE_MAX`). C'est exactement ce que fait `fusion.ajouter_ign()` avec la BD TOPO.
4. **Rapporter les kilomètres nouveaux** à la longueur du réseau OSM praticable de la tuile. Ce « gain du réseau » dit de combien la source agrandirait le réseau que BRouter voit.

Les sources sont la BD TOPO (WFS de la Géoplateforme), les sentiers USGS National Digital Trails (type `Terra Trail` seulement), swissTLM3D « Strassen und Wege » (API de geo.admin.ch) et TOP10NL `wegdeel_hartlijn` (OGC API de PDOK). Les données OSM sont celles d'Overpass le 23 octobre 2026.

### France, dont le Var

| Zone | Centre de la tuile | Sentiers et chemins BD TOPO | Réseau OSM | Absents d'OSM | Gain du réseau |
| --- | --- | ---: | ---: | ---: | ---: |
| Ariège, Couserans | 42,925 N 1,175 E | 127,8 km | 95,6 km | 96,0 km | **+100 %** |
| Var, massif des Maures | 43,325 N 6,425 E | 119,9 km | 91,4 km | 66,0 km | **+72 %** |
| Var, Sainte-Baume | 43,275 N 5,725 E | 141,4 km | 179,1 km | 72,7 km | **+41 %** |
| Vosges, Hohneck | 47,975 N 6,975 E | 145,0 km | 158,5 km | 59,9 km | **+38 %** |
| Var, sud des gorges du Verdon | 43,675 N 6,375 E | 101,4 km | 99,0 km | 29,5 km | **+30 %** |
| Var, Estérel | 43,475 N 6,775 E | 127,1 km | 201,3 km | 41,9 km | **+21 %** |
| Chartreuse | 45,375 N 5,775 E | 97,9 km | 133,1 km | 23,5 km | **+18 %** |

Les kilomètres absents d'OSM sont presque tous des sentiers et des chemins : 93 des 96 km en Ariège, 66 des 66 km dans les Maures, 64 des 73 km à la Sainte-Baume. La tuile la plus dense de la Sainte-Baume se trouve à cheval sur la limite des Bouches-du-Rhône, vers Cuges-les-Pins et Riboux. Celle du Verdon est au sud des gorges et non dans les gorges elles-mêmes.

Le Var confirme ce que montrent l'Ariège et les Vosges. Le gain est le plus fort là où les randonneurs sont moins nombreux et où OSM est donc plus clairsemé : les Maures plus que l'Estérel, très parcouru. C'est précisément là qu'un calcul sur OSM seul est le plus trompeur.

### États-Unis, Suisse, Pays-Bas

| Zone | Centre de la tuile | Source officielle | Réseau OSM | Absents d'OSM | Gain du réseau |
| --- | --- | ---: | ---: | ---: | ---: |
| US, White Mountains (NH) | 44,225 N 71,425 O | 26,2 km | 59,0 km | 5,7 km | +10 % |
| US, Zion | 37,275 N 112,925 O | 24,5 km | 33,8 km | 1,8 km | +5 % |
| US, Great Smoky Mountains | 35,675 N 83,525 O | 37,6 km | 49,4 km | 2,2 km | +4 % |
| US, Gila National Forest | 33,275 N 108,275 O | 25,7 km | 27,5 km | 0,0 km | 0 % |
| CH, Zermatt | 46,025 N 7,775 E | 105,2 km | 130,8 km | 6,3 km | +5 % |
| CH, Emmental (Napf) | 46,975 N 7,925 E | 133,1 km | 168,5 km | 5,9 km | +4 % |
| NL, Veluwe | 52,025 N 5,875 E | 263,4 km | 284,3 km | 35,5 km | +12 % |

Trois remarques précisent ces chiffres.

- **Aux États-Unis, la source est maigre avant même d'être comparée.** La tuile la plus dense de chaque massif n'a que 25 à 38 km de sentiers USGS, quatre à six fois moins que les sentiers et chemins de la BD TOPO sur une tuile française. L'USGS ne recense que les sentiers officiels des agences, pas tous les chemins physiques. Et ce qu'il ajoute est surtout sans information d'accès : 5,2 des 5,7 km des White Mountains, et les 2,2 km des Smoky Mountains, ont un `hikerpedestrian` vide.
- **En Suisse, OSM et swissTLM3D se recouvrent presque entièrement.** Les quelques kilomètres restants relèvent des classes 15 et 16 de swissTLM3D (`objektart`), que nous n'avons pas décodées.
- **Aux Pays-Bas, le chiffre est un plafond.** Les 35,5 km comprennent 6,5 km de routes rapides (`snelverkeer`) et 0,3 km de voies d'aérodrome. Restent environ 29 km de voies mixtes ou piétonnes, soit +10 %. Le classement néerlandais comptait aussi les routes, et la tuile retenue touche le nord d'Arnhem. Enfin, une ligne médiane de TOP10NL qui s'écarte de plus de 12 m de la voie OSM correspondante est comptée comme nouvelle.

### Fraîcheur des sentiers USGS

Le jeu USGS est toujours alimenté. Sur 607 202 tronçons, 443 690 ont été chargés en 2026, le dernier le 14 septembre 2026. Les années précédentes donnent 19 433 tronçons en 2022, aucun en 2023, 34 173 en 2024 et 13 256 en 2025. Mais `loaddate` est la date d'entrée dans la base nationale, non celle d'un relevé de terrain. L'USGS agrège ce que lui transmettent le National Park Service, le Forest Service, le BLM et les États, et le chargement massif de 2026 ressemble à un rechargement complet. La fraîcheur réelle dépend de ces agences, et rien dans la donnée ne permet de juger l'effet des restrictions budgétaires fédérales.

### Limites de la mesure

- **Une tuile par massif**, soit une vingtaine de km² chacune. Sept zones françaises et sept étrangères suffisent à séparer un gain de 20 à 100 % d'un gain de 0 à 12 %. Elles ne suffiraient pas à départager deux pays proches.
- **« Absent d'OSM » est un plafond.** Un tracé officiel décalé de plus de 12 m de son équivalent OSM compte comme nouveau. Cela vaut aussi pour la BD TOPO : le gain français est peut-être un peu surestimé, l'écart entre la France et les autres pays non.
- **Un chemin nouveau n'est pas forcément praticable.** hike2gpx affiche déjà les chemins IGN comme « non vérifiés », et la mesure ne dit rien de leur état sur le terrain.
- **L'Espagne et l'Allemagne ne sont pas mesurées.** Les sentiers de la BTN ne s'obtiennent qu'en téléchargeant des feuilles, et l'ATKIS Basis-DLM dépend de chaque Land. On les mesurera en ajoutant une fonction de lecture à l'outil, sur le modèle des quatre existantes.

Pour refaire la mesure :

```
python tools/essai_sources_chemins.py            toutes les zones
python tools/essai_sources_chemins.py US Var     un pays, ou les zones dont le nom contient « Var »
```

## Ce que fait la BD TOPO, et pourquoi elle marche

La chaîne française tient en trois modules.

- `bdtopo.py` interroge le WFS de la Géoplateforme (`BDTOPO_V3:troncon_de_route`) autour de la zone demandée, par pages de 5000 tronçons, et garde un cache d'un mois par tuile. Il lit `nature`, `acces_pieton`, `acces_vehicule_leger` et `prive`.
- `fusion.py` ne garde un tronçon IGN que si moins de la moitié de sa longueur passe à moins de 12 m d'une voie OSM : sinon OSM le connaît déjà, et OSM reste juge des accès. Il raccorde les bouts gardés entre eux, et à la voie OSM la plus proche quand elle passe à moins de 15 m. Il étiquette chaque tronçon `highway=path` + `hike2gpx=ign`, traduit un accès piéton restreint en `foot=private`, et écrit le tout en PBF OSM.
- `maison.py` fabrique les tuiles BRouter à partir de ce PBF et recalcule les franchissements sur le réseau fusionné.

Ce succès tient à quatre qualités réunies. La BD TOPO **comble de vrais trous d'OSM** ; la mesure en donne maintenant l'ampleur. C'est un **réseau physique**, qui dit la nature de chaque voie. Elle est **interrogeable par emprise** : on demande un rectangle, on reçoit ses tronçons, sans rien télécharger d'avance. Elle est enfin **nationale et homogène**.

La première qualité est celle qui manque ailleurs. Les trois autres se retrouvent en partie : les services américain, suisse et néerlandais répondent tous par emprise. Mais une source bien servie qui n'ajoute rien n'apporte rien au calcul.

## Ce qui est aujourd'hui propre à l'IGN

La BD TOPO est câblée en dur à quatre endroits :

- `fusion.py` : `ajouter_ign()` et l'étiquette constante `{"highway": "path", "hike2gpx": "ign"}` ;
- `brouter.py` : la table d'étiquettes ajoute la clé `hike2gpx=ign`, et le profil en tire une pénalité (`ign_penalty`) ;
- `application.py` : `portions_ign()` cherche `hike2gpx=ign` dans le résultat de BRouter pour signaler les portions « non vérifiées » ;
- `providers/fr.js` : `routableOverlay: "bdtopo"` est la seule déclaration d'une capacité de calcul, et elle vit côté page.

Tant qu'aucune source étrangère n'est justifiée, ce câblage n'est pas un problème : il n'y a qu'une source, et elle est française. Généraliser la fusion serait une abstraction sans second cas.

Le dernier point reste pourtant un défaut latent. La page active la coche « utiliser pour le calcul » d'après le provider JavaScript, alors que le calcul est fait par le serveur Python. Si quelqu'un déclarait `routableOverlay` dans `es.js`, la coche s'allumerait en Espagne. Le serveur irait chercher la BD TOPO, ne trouverait rien hors de France, et calculerait avec OSM seul sans le dire. Une capacité de calcul doit être annoncée par le côté qui calcule. La section suivante montre comment.

## Les providers : un seul fichier par pays

Cette partie vaut indépendamment du verdict. Les providers servent d'abord à l'affichage, et un pays ajouté pour ses fonds de carte doit être simple à ajouter.

### Ce qu'il faut toucher aujourd'hui pour ajouter un pays

Le provider JavaScript donne l'impression qu'un pays tient dans un fichier. En réalité, il était éparpillé en quatre endroits, et l'est encore en trois :

- `providers/<code>.js` : les fonds et les calques, sous forme de code Leaflet ;
- `app.js` : les libellés FR/EN de ces fonds et calques (`fond.espagne`, `calque.senderos`, `calque.usgsSentiers`…), dans les tables de traduction de la page ;
- `application.py` : `PAYS_CARTES`, qui fait correspondre l'identifiant Geofabrik au code pays (`"spain": "es"`), pour suivre le pays du centre de la carte ;
- jusqu'au retrait du proxy FEDME (voir plus bas), `web.py` portait aussi `TUILES_VECTORIELLES`, l'adresse amont des tuiles relayées par le serveur.

Oublier l'un de ces endroits ne casse rien de visible. Un libellé manquant affiche sa clé brute, et un pays absent de `PAYS_CARTES` n'est jamais choisi quand on déplace la carte à la main. Ce sont des oublis silencieux, du même genre que le dossier `providers/` oublié dans le spec PyInstaller avant la 0.3.0.

### Le principe : un fichier de données, lu des deux côtés

Le fichier d'un pays doit être lu par la page, pour dessiner, et par le serveur, pour détecter le pays, relayer les tuiles et annoncer ce qu'il sait calculer. Il ne peut donc plus être du JavaScript : Python ne sait pas lire un objet littéral JavaScript. Il devient un fichier **JSON**, `providers/<code>.json`, que la bibliothèque standard lit des deux côtés sans dépendance. Le serveur continue de servir le registre à la page, comme il concatène aujourd'hui les `.js`. JSON n'accepte pas de commentaires : chaque fichier et chaque couche portent donc un champ `description`, comme dans le catalogue décrit ci-dessous.

Pour les couches, inutile d'inventer un vocabulaire. L'écosystème OSM en a un, celui de l'**[Editor Layer Index](https://github.com/osmlab/editor-layer-index)** (ELI). Ce catalogue d'imagerie, ouvert en mars 2013 par osmlab, alimente aujourd'hui iD, Vespucci, Go Map!!, MapComplete, Every Door, Potlatch 3 et, en option, JOSM. Son [schéma](https://github.com/osmlab/editor-layer-index/blob/gh-pages/schema.json) décrit chaque fond par `id`, `name`, `type` (`tms`, `wms`, `wmts`…), `url` avec les gabarits `{zoom}`, `{x}` et `{y}`, `min_zoom`, `max_zoom`, `attribution` (`text`, `url`, `required`), `overlay`, `category`, `country_code` et `license_url`. L'IGN y figure déjà : l'entrée `fr.ign.bdortho` décrit la BD ORTHO avec ces mêmes champs.

Reprendre ces noms de champs a deux avantages. N'importe qui venant d'OSM lit le fichier sans explication, et une couche peut passer de l'ELI à hike2gpx, ou l'inverse, presque telle quelle. Dans l'ELI, `max_zoom` désigne le dernier niveau que la source fournit réellement ; c'est le `maxNativeZoom` de Leaflet, et le zoom maximal de la carte reste un réglage commun de la page.

Trois écarts à l'ELI sont assumés, et seront documentés dans le dépôt :

- `name` porte les deux langues de la page, `{"fr": …, "en": …}`, au lieu d'une chaîne traduite ailleurs ;
- une couche qui exige la clé IGN de l'utilisateur l'indique par `"cle": "ign"` et le gabarit `{cle}` dans son `url` ; la page l'omet quand aucune clé n'est saisie, comme elle omet aujourd'hui le SCAN 25 ;
- deux types s'ajoutent à ceux de l'ELI, `mvt` pour les tuiles vectorielles et `arcgis_export` pour l'export dynamique d'un MapServer ArcGIS (voir plus bas).

### Ce que contient le fichier

Le fichier d'un pays répond à quatre questions.

1. **Quel pays, et où ?** `code` (ISO 3166-1, en minuscules) et `geofabrik`, la liste des régions Geofabrik dont le contour définit le pays. Ce champ remplace `PAYS_CARTES` : le serveur choisit le premier pays dont une région contient le centre de la carte. La France garde pour l'instant son cas particulier, puisque ses contours OSM-FR plus fins décident de `hors_france`.
2. **Quels fonds ?** `fonds`, la liste des fonds au vocabulaire ELI, et `fond_defaut`.
3. **Quels calques ?** `calques`, les calques d'affichage, au même vocabulaire. Si un calque doit vraiment passer par le serveur, une marque `proxy` le dit, et `web.py` construit sa liste blanche à partir des fichiers au lieu d'une table à part.
4. **Quels chemins pour le calcul ?** Un bloc `chemins`, qui n'existe aujourd'hui que pour la France. Il nomme le protocole de la source (`wfs` pour la BD TOPO), son adresse et sa couche, l'étiquette de source (`ign`) que partagent la fusion, le profil BRouter et le résultat, l'attribution et la licence.

Le défaut de `routableOverlay` disparaît alors de lui-même. Le bloc `chemins` est lu par le serveur, qui ne l'annonce à la page que s'il possède un connecteur pour ce protocole. La page active la coche d'après cette réponse : un fichier ne peut plus promettre un calcul que le serveur ne sait pas faire.

Voici, par exemple, le fichier de l'Espagne. Il reprend exactement ce que font aujourd'hui `es.js`, les libellés de `app.js` et l'entrée `"spain"` de `PAYS_CARTES`. Il n'a pas de bloc `chemins`, puisqu'aucune source espagnole n'est routée.

```json
{
  "code": "es",
  "description": "Espagne : carte topographique de l'IGN espagnol et sentiers balisés FEDME, pour l'affichage seulement.",
  "geofabrik": ["spain"],
  "fond_defaut": "ign-es-mtn",
  "fonds": [
    {
      "id": "ign-es-mtn",
      "name": {"fr": "Carte topographique (IGN Espagne)", "en": "Topographic map (Spanish IGN)"},
      "type": "tms",
      "url": "https://www.ign.es/wmts/mapa-raster?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=MTN&STYLE=default&TILEMATRIXSET=GoogleMapsCompatible&FORMAT=image/jpeg&TILEMATRIX={zoom}&TILECOL={x}&TILEROW={y}",
      "max_zoom": 18,
      "attribution": {"text": "IGN España", "url": "https://www.ign.es/", "required": true}
    }
  ],
  "calques": [
    {
      "id": "fedme-senderos",
      "name": {"fr": "Sentiers balisés GR/PR/SL (IGN Espagne)", "en": "Waymarked GR/PR/SL trails (Spanish IGN)"},
      "type": "mvt",
      "url": "https://vt-fedme.idee.es/vt.senderogr,vt.senderopr,vt.senderosl/{zoom}/{x}/{y}.pbf",
      "min_zoom": 8,
      "style": {
        "vt.senderogr": {"color": "#d32f2f", "weight": 3, "opacity": 0.9},
        "vt.senderopr": {"color": "#e6a000", "weight": 3, "opacity": 0.9},
        "vt.senderosl": {"color": "#29935d", "weight": 3, "opacity": 0.9}
      },
      "attribution": {"text": "IGN España / FEDME", "url": "https://www.ign.es/", "required": true}
    }
  ]
}
```

### Ce qui reste hors du fichier, volontairement

- **Le nom du pays** vient de `Intl.DisplayNames`, c'est-à-dire du navigateur, dans la langue de la page. C'est déjà le cas dans `presentation.js`, et c'est bien ainsi.
- **Les altitudes** sont entièrement gérées par gpx2elev : le choix du modèle de terrain selon le lieu, sa couverture et son protocole. hike2gpx ne fait qu'afficher le modèle que gpx2elev renvoie dans son résultat (`modele`). Ajouter un pays dans hike2gpx ne demande donc rien pour l'altitude, et un modèle plus fin pour un pays s'ajoute dans gpx2elev. Le déclarer aussi dans le fichier du pays créerait deux propriétaires pour une même décision.
- **Le code des types de couche** (`tms`, `mvt`, `arcgis_export`) vit une fois dans `app.js`, et **le code des connecteurs de chemins**, un par protocole, vit côté Python. Le fichier du pays ne fait que les paramétrer.

### Trois cas particuliers vérifiés le 23 octobre 2026

- **L'export ArcGIS des sentiers USGS est justifié.** L'USGS publie bien un WMS de ses sentiers (`USGSTrails/MapServer/WMSServer`, WMS 1.3.0), qui serait la voie standard avec `L.tileLayer.wms`. Mais ce WMS ne propose que CRS:84, EPSG:4269 et EPSG:4326, pas le Web Mercator (EPSG:3857) de la carte. L'`export` ArcGIS, lui, reprojette à la demande (`imageSR=3857`) : c'est le bon choix. Il devient le type générique `arcgis_export` dans `app.js`, au lieu d'un `getTileUrl` écrit dans le fichier du pays.
- **Le proxy des sentiers FEDME ne servait à rien, et il est retiré.** Le serveur `vt-fedme.idee.es` répond `Access-Control-Allow-Origin: *`. Ni hike2gpx ni le serveur commun `nico579_commons` n'imposent de politique CSP, et le commit d'origine ne donnait aucune raison. L'essai dans Chrome, sur une page servie par `127.0.0.1`, l'a confirmé le 23 octobre 2026 : sur le Val d'Aran, le calque a chargé 46 tuiles directement depuis le serveur FEDME, toutes en statut 200, dont 28 avec des sentiers dessinés, sans erreur dans la console. `es.js` lit donc les tuiles en direct, et `web.py` a perdu `TUILES_VECTORIELLES` et la route `/tuiles/`.
- **Leaflet.VectorGrid n'est plus maintenu depuis 2017.** Il fonctionne et il est figé dans le dépôt, donc sans risque immédiat. Si les tuiles vectorielles se multipliaient, il faudrait regarder du côté de MapLibre, aujourd'hui la référence du vectoriel. Pour un seul calque, la question ne se pose pas.

### Garde-fous et migration

Un test lit chaque fichier de `providers/` et vérifie que les champs obligatoires sont présents, que chaque libellé existe dans les deux langues, que `fond_defaut` désigne un fond déclaré, que chaque `type` est connu de la page et que chaque `chemins.protocole` est connu du serveur. Les oublis silencieux décrits plus haut deviennent ainsi des tests en échec.

La migration est mécanique : huit fichiers à convertir, `PAYS_CARTES` et les libellés à retirer d'`application.py` et d'`app.js`, une fabrique de couches à écrire dans `app.js`. Elle se fait en une PR, sans changement visible pour l'utilisateur. Rien ne presse : elle s'impose au prochain pays ajouté, pour qu'il ne s'ajoute qu'en un endroit.

## Sources candidates, pays par pays

| Pays | Source | Accès par emprise | Gain mesuré | Verdict |
| --- | --- | --- | --- | --- |
| États-Unis | USGS National Digital Trails | Oui, requête ArcGIS | 0 à 10 %, accès piéton souvent inconnu | Affichage seulement |
| Suisse | swissTLM3D | Oui, API geo.admin.ch | 4 à 5 % | Affichage seulement |
| Pays-Bas | TOP10NL (PDOK) | Oui, OGC API Features | 10 à 12 %, plafond | Affichage seulement |
| Espagne | BTN du CNIG | Non pour les sentiers ; fichiers par feuille | Non mesuré | Seule piste ouverte, à mesurer d'abord |
| Allemagne | ATKIS Basis-DLM (par Land) | Selon le Land | Non mesuré | À mesurer en Bavière, sans provider à ce jour |
| Luxembourg | BD-L-GeoBase | Non ; un seul GeoPackage | Non mesuré ; OSM réputé complet | Affichage seulement |
| Autriche | GIP | Non ; export national | Non mesuré ; sentiers alpins mal couverts par le GIP | Affichage seulement |
| Norvège | N50 | Non ; fichiers | Non mesuré ; réseau généralisé | Affichage seulement |

### États-Unis : USGS National Digital Trails

Sur le plan technique, c'est la source la plus proche de la BD TOPO. La couche `USGSTrails/MapServer/0` déclare les capacités `Map,Query,Data`, rend jusqu'à 2000 tronçons par requête, et dit pour chacun si les randonneurs y sont admis (`hikerpedestrian`). Les données sont du [domaine public](https://www.usgs.gov/national-digital-trails/qas-about-usgs-trail-data).

La mesure la disqualifie pourtant pour le calcul. Elle ne recense que les sentiers officiels des agences, peu nombreux, et OSM les a déjà presque tous : de 0 % à 10 % de gain sur quatre massifs, dont une forêt reculée (la Gila) où rien ne manquait. Le calque d'affichage `usgsSentiers` reste utile pour voir les sentiers officiels sur la carte.

### Espagne : BTN du CNIG

C'est la seule piste qui reste ouverte. La [BTN](https://centrodedescargas.cnig.es/CentroDescargas/btn) est un vrai réseau physique, sous [licence d'attribution](https://centrodedescargas.cnig.es/CentroDescargas/detalleArchivo?sec=10318930), et l'on dit OSM moins complet en Espagne rurale. C'est une impression, pas une mesure.

Le mode d'accès est défavorable. Le WFS INSPIRE des réseaux de transport, `servicios.idee.es/wfs-inspire/transportes` ([datos.gob.es](https://datos.gob.es/es/catalogo/e0dat0002-redes-de-transporte-de-espana), CC BY 4.0), n'a rendu que 6 tronçons routiers du réseau `ES.SCNE.IGR-RT` sur 4 × 5 km dans le Val d'Aran, sans nature de voie. Les sentiers de la BTN ne s'obtiennent qu'en téléchargeant des feuilles. Avant tout connecteur, il faut télécharger une feuille sur une zone pyrénéenne et une autre en Espagne intérieure, ajouter une fonction de lecture à l'outil de mesure, et ne poursuivre que si le gain approche celui de la BD TOPO.

Les [sentiers FEDME](https://centrodedescargas.cnig.es/CentroDescargas/senderos-fedme) restent un calque d'affichage. Un itinéraire balisé GR, PR ou SL suit plusieurs chemins, dont beaucoup sont déjà dans OSM : l'ajouter comme voie indépendante créerait des doublons et des raccordements faux.

### Allemagne : ATKIS Basis-DLM

Par sa structure, l'ATKIS Basis-DLM est le cousin le plus direct de la BD TOPO : un modèle topographique national au 1:25 000, avec un réseau de voies qui distingue routes, chemins agricoles et sentiers. Mais la cartographie allemande est l'affaire des Länder. Selon sa [lettre d'information de juin 2024](https://geodaten.bayern.de/odd/m/3/pdf/newsletter_archiv/2024_06.pdf), la Bavière publie son Basis-DLM en open data, en téléchargement et par WFS. La Rhénanie-Palatinat réserve [son WFS](https://lvermgeo.rlp.de/fileadmin/lvermgeo/pdf/produktblaetter/BASIS_DLM_WFS.pdf) aux utilisateurs enregistrés, et la situation des autres Länder n'est pas établie.

OSM est très complet en Allemagne. Vu les résultats suisses et néerlandais, un gain important serait une surprise. Une mesure en Bavière, par son WFS, coûterait peu et trancherait.

### Suisse, Pays-Bas, Luxembourg, Autriche, Norvège

- **Suisse** : [swissTLM3D](https://www.swisstopo.admin.ch/en/landscape-model-swisstlm3d) est une donnée excellente, en [réutilisation libre](https://www.swisstopo.admin.ch/en/faq-free-geodata), et son API répond par emprise. Mais OSM l'égale presque : 4 à 5 % de gain.
- **Pays-Bas** : [TOP10NL](https://www.pdok.nl/downloadviewer/-/article/basisregistratie-topografie-brt-topnl) est servi par l'[OGC API Features de PDOK](https://api.pdok.nl/brt/top10nl/ogc/v1?f=html&lang=en), sous CC BY 4.0. Le gain de 10 à 12 % sur la Veluwe est un plafond, gonflé par des routes et des écarts de tracé.
- **Luxembourg** : le [thème transport de la BD-L-GeoBase](https://data.public.lu/fr/datasets/bd-l-geobase/) est un seul GeoPackage en CC0, mais OSM y est réputé complet.
- **Autriche** : le [GIP](https://www.gip.gv.at/) est un graphe de transport ; [AWIS.GIP](https://awisgip.at/daten.html) indique que sa base de sentiers alpins est encore en constitution, alors que c'est là qu'un ajout aurait du sens.
- **Norvège** : [N50](https://kartkatalog.geonorge.no/metadata/uuid/ea192681-d039-42ec-b1bc-f3ce04c189ac) est généralisé, donc moins précis qu'OSM, et la base fine [FKB-TraktorvegSti](https://dokument.geonorge.no/produktark/fkb-traktorvegsti/2025-01-07/fkb-traktorvegsti.pdf) n'est pas librement téléchargeable.

Tous gardent leurs fonds d'affichage. On ne reviendra sur leur cas que si un utilisateur signale un manque précis d'OSM.

## Plan

1. **Ne pas écrire de connecteur de chemins étranger.** La mesure ne justifie aucun des trois pays testés. Le câblage IGN de la fusion reste en l'état : le généraliser serait une abstraction sans second cas.
2. **Investir dans la BD TOPO**, qui porte la valeur : dans le Var, en Ariège et dans les Vosges, elle agrandit le réseau de 21 % à 100 %. Les pistes sont dans le code existant : règles d'accès, raccordements, signalement des chemins « non vérifiés ».
3. **Mesurer avant de rouvrir le chantier.** L'Espagne (une feuille BTN pyrénéenne, une en Espagne intérieure) et la Bavière (WFS du Basis-DLM) se mesurent en ajoutant une fonction de lecture à `tools/essai_sources_chemins.py`. Un connecteur ne se discute qu'au-delà d'environ 20 % de gain, le bas de la fourchette française.
4. **Passer aux fichiers JSON par pays au prochain pays ajouté**, pour que l'affichage d'un pays ne se déclare qu'en un endroit et que la coche de calcul soit annoncée par le serveur.
5. ~~Vérifier le proxy FEDME dans le navigateur, puis le supprimer s'il ne sert à rien.~~ Fait : vérifié dans Chrome et retiré.

**État : analyse et mesure. Seul le proxy FEDME, inutile, a été retiré du code.** Hors de France, les calques de sentiers sont marqués « affichage seul », et le calcul utilise OSM seul.
