# Sources officielles de chemins pour le calcul BRouter

Analyse du 23 octobre 2026, révisée le même jour après la release 0.3.0. Ce rapport prépare l'extension, hors de France, de ce que la BD TOPO fait aujourd'hui pour le calcul : ajouter à OSM des chemins physiques qu'il ne connaît pas. Il examine les pays qui ont déjà un provider d'affichage dans `hike2gpx/assets/web/providers/`, plus l'Allemagne, qui n'en a pas encore mais possède la source la plus proche de la BD TOPO.

Une première version classait les pays d'après la qualité de leurs données. Cette révision ajoute un critère que la première version négligeait, la **manière d'y accéder**. Elle s'appuie sur des requêtes réelles faites le 23 octobre 2026 contre les services espagnol et américain. Ces requêtes ont inversé l'ordre de réalisation proposé.

Elle examine aussi les providers eux-mêmes. Un pays est aujourd'hui décrit en quatre endroits du code. L'objectif retenu est **un seul fichier par pays, qui regroupe tous ses besoins** : ses fonds, ses calques, leurs libellés, sa détection et sa source de chemins pour le calcul.

## Ce que fait la BD TOPO, et pourquoi elle marche

En France, la chaîne tient en trois modules.

- `bdtopo.py` interroge le WFS de la Géoplateforme (`BDTOPO_V3:troncon_de_route`) autour de la zone demandée, par pages de 5000 tronçons, et garde un cache d'un mois par tuile. Il lit `nature`, `acces_pieton`, `acces_vehicule_leger` et `prive`.
- `fusion.py` ne garde un tronçon IGN que si moins de la moitié de sa longueur passe à moins de 12 m d'une voie OSM : sinon OSM le connaît déjà, et OSM reste juge des accès. Il raccorde les bouts gardés entre eux et à la voie OSM la plus proche quand elle passe à moins de 15 m. Il étiquette chaque tronçon `highway=path` + `hike2gpx=ign`, et traduit un accès piéton restreint en `foot=private`. Il écrit enfin le tout en PBF OSM.
- `maison.py` fabrique les tuiles BRouter à partir de ce PBF et recalcule les franchissements sur le réseau fusionné.

Ce succès vient de quatre qualités réunies. La BD TOPO **comble de vrais trous d'OSM**, surtout en montagne. C'est un **réseau physique** qui dit la nature de chaque voie. Elle est **interrogeable par emprise** : on demande un rectangle, on reçoit ses tronçons, sans rien télécharger d'avance. Elle est enfin **nationale et homogène**. La troisième qualité est la moins visible, et pourtant c'est elle qui fixe l'architecture. hike2gpx travaille à la demande, autour de la carte, comme pour les extraits OSM. Une source livrée seulement en gros fichier impose un autre mécanisme : téléchargement initial, stockage, mise à jour périodique.

Une tuile d'affichage, même vectorielle, n'est donc pas une source de calcul. Le calque swisstopo de randonnée ou les sentiers FEDME se dessinent bien, mais ils ne donnent ni la topologie, ni la nature des voies, ni l'accès.

## Ce qui est aujourd'hui propre à l'IGN

Avant tout connecteur étranger, il faut savoir où la BD TOPO est câblée en dur.

- `fusion.py` : `ajouter_ign()` et l'étiquette constante `{"highway": "path", "hike2gpx": "ign"}`.
- `brouter.py` : la table d'étiquettes ajoute la clé `hike2gpx=ign`, et le profil en tire une pénalité (`ign_penalty`).
- `application.py` : `portions_ign()` cherche `hike2gpx=ign` dans le résultat de BRouter pour signaler les portions « non vérifiées ».
- `providers/fr.js` : `routableOverlay: "bdtopo"` est la seule déclaration d'une capacité de calcul, et elle vit côté page.

Ce dernier point est un défaut de conception, pas un détail. La page active la coche « utiliser pour le calcul » d'après le provider JavaScript, alors que le calcul est fait par le serveur Python. Si quelqu'un déclarait `routableOverlay` dans `es.js`, la coche s'allumerait en Espagne. Le serveur irait chercher la BD TOPO, ne trouverait rien hors de France, et calculerait avec OSM seul sans le dire. Une capacité de calcul doit être annoncée par le côté qui calcule. La section suivante montre qu'un fichier de pays lu par le serveur résout ce défaut sans rien disperser.

## Les providers : un seul fichier par pays

### Ce qu'il faut toucher aujourd'hui pour ajouter un pays

Le provider JavaScript donne l'impression qu'un pays tient dans un fichier. En réalité, il est éparpillé en quatre endroits :

- `providers/<code>.js` : les fonds et les calques, sous forme de code Leaflet ;
- `app.js` : les libellés FR/EN de ces fonds et calques (`fond.espagne`, `calque.senderos`, `calque.usgsSentiers`…), dans les tables de traduction de la page ;
- `application.py` : `PAYS_CARTES`, qui fait correspondre l'identifiant Geofabrik au code pays (`"spain": "es"`), pour suivre le pays du centre de la carte ;
- `web.py` : `TUILES_VECTORIELLES`, l'adresse amont des tuiles relayées par le serveur, aujourd'hui pour les seuls sentiers FEDME.

Pour la France s'ajoutent les quatre emplacements de la BD TOPO vus plus haut. Oublier l'un de ces endroits ne casse rien de visible. Un libellé manquant affiche sa clé brute, et un pays absent de `PAYS_CARTES` n'est jamais choisi quand on déplace la carte à la main. Ce sont des oublis silencieux, du même genre que le dossier `providers/` oublié dans le spec PyInstaller avant la 0.3.0.

### Le principe : un fichier de données, lu des deux côtés

Le fichier d'un pays doit être lu par la page, pour dessiner, et par le serveur, pour détecter le pays, relayer les tuiles et calculer. Il ne peut donc plus être du JavaScript : Python ne sait pas lire un objet littéral JavaScript. Il devient un fichier **JSON**, `providers/<code>.json`, que la bibliothèque standard lit des deux côtés sans dépendance. Le serveur continue de servir le registre à la page, comme il concatène aujourd'hui les `.js`.

JSON n'accepte pas de commentaires. Chaque fichier et chaque couche portent donc un champ `description`, comme dans le catalogue décrit ci-dessous.

Pour les couches, inutile d'inventer un vocabulaire. L'écosystème OSM en a un, celui de l'**[Editor Layer Index](https://github.com/osmlab/editor-layer-index)** (ELI). Ce catalogue d'imagerie, ouvert en mars 2013 par osmlab, alimente aujourd'hui iD, Vespucci, Go Map!!, MapComplete, Every Door, Potlatch 3 et, en option, JOSM. Son [schéma](https://github.com/osmlab/editor-layer-index/blob/gh-pages/schema.json) décrit chaque fond par `id`, `name`, `type` (`tms`, `wms`, `wmts`…), `url` avec les gabarits `{zoom}`, `{x}` et `{y}`, `min_zoom`, `max_zoom`, `attribution` (`text`, `url`, `required`), `overlay`, `category`, `country_code` et `license_url`. L'IGN y figure déjà : l'entrée `fr.ign.bdortho` décrit la BD ORTHO avec ces mêmes champs.

Reprendre ces noms de champs a deux avantages. N'importe qui venant d'OSM lit le fichier sans explication, et une couche peut passer de l'ELI à hike2gpx, ou l'inverse, presque telle quelle. `max_zoom` y désigne le dernier niveau que la source fournit réellement ; c'est le `maxNativeZoom` de Leaflet, et le zoom maximal de la carte reste un réglage commun de la page.

Trois écarts à l'ELI sont assumés, et seront documentés dans le dépôt :

- `name` porte les deux langues de la page, `{"fr": …, "en": …}`, au lieu d'une chaîne traduite ailleurs ;
- une couche qui exige la clé IGN de l'utilisateur l'indique par `"cle": "ign"` et le gabarit `{cle}` dans son `url` ; la page l'omet quand aucune clé n'est saisie, comme elle omet aujourd'hui le SCAN 25 ;
- deux types s'ajoutent à ceux de l'ELI, `mvt` pour les tuiles vectorielles et `arcgis_export` pour l'export dynamique d'un MapServer ArcGIS (voir plus bas).

### Ce que contient le fichier

Le fichier d'un pays répond à quatre questions.

1. **Quel pays, et où ?** `code` (ISO 3166-1, en minuscules) et `geofabrik`, la liste des régions Geofabrik dont le contour définit le pays. Ce champ remplace `PAYS_CARTES` : le serveur choisit le premier pays dont une région contient le centre de la carte. La France garde pour l'instant son cas particulier, puisque ses contours OSM-FR plus fins décident de `hors_france`. On ne généralisera ce mécanisme que si un deuxième pays en a besoin.
2. **Quels fonds ?** `fonds`, la liste des fonds au vocabulaire ELI, et `fond_defaut`.
3. **Quels calques ?** `calques`, la liste des calques d'affichage, au même vocabulaire. Si un calque doit vraiment passer par le serveur, une marque `proxy` le dit, et `web.py` construit sa liste blanche d'adresses à partir des fichiers au lieu d'une table à part.
4. **Quels chemins pour le calcul ?** Un bloc `chemins`, absent tant qu'aucune source n'est prête. Il donne le protocole de la source (`wfs`, `arcgis_query`, `fichier`), son adresse et sa couche, l'étiquette de source (`ign`, `usgs`) que la fusion, le profil BRouter et le résultat partagent, les règles de filtrage et de traduction vers les étiquettes OSM, l'attribution et la licence.

Le défaut de `routableOverlay` disparaît de lui-même. Le bloc `chemins` est lu par le serveur, qui ne l'annonce à la page que s'il possède un connecteur pour ce protocole. La page active la coche d'après cette réponse. Un fichier ne peut donc plus promettre un calcul que le serveur ne sait pas faire.

Voici le fichier des États-Unis, tel qu'il serait une fois le connecteur USGS écrit. Les fonds et le calque reprennent exactement ce que fait `us.js` aujourd'hui.

```json
{
  "code": "us",
  "description": "États-Unis : carte topographique USGS, sentiers du National Digital Trails pour l'affichage et le calcul.",
  "geofabrik": ["us"],
  "fond_defaut": "usgs-topo",
  "fonds": [
    {
      "id": "usgs-topo",
      "name": {"fr": "Carte topographique (USGS)", "en": "Topographic map (USGS)"},
      "type": "tms",
      "url": "https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{zoom}/{y}/{x}",
      "max_zoom": 16,
      "attribution": {"text": "USGS The National Map", "url": "https://www.usgs.gov/programs/national-geospatial-program/national-map", "required": true}
    }
  ],
  "calques": [
    {
      "id": "usgs-sentiers",
      "name": {"fr": "Sentiers recensés par l'USGS", "en": "Trails mapped by USGS"},
      "type": "arcgis_export",
      "url": "https://partnerships.nationalmap.gov/arcgis/rest/services/USGSTrails/MapServer",
      "max_zoom": 16,
      "couleur": "#d22f2f",
      "attribution": {"text": "USGS National Digital Trails", "url": "https://www.usgs.gov/national-digital-trails", "required": true}
    }
  ],
  "chemins": {
    "protocole": "arcgis_query",
    "url": "https://partnerships.nationalmap.gov/arcgis/rest/services/USGSTrails/MapServer/0",
    "etiquette": "usgs",
    "name": {"fr": "sentiers USGS", "en": "USGS trails"},
    "filtre": {"trailtype": ["Terra Trail"]},
    "traduction": {"hikerpedestrian": {"Yes": {"foot": "yes"}, "No": {"foot": "no"}}},
    "attribution": {"text": "USGS National Digital Trails", "url": "https://www.usgs.gov/national-digital-trails", "required": true},
    "license_url": "https://www.usgs.gov/national-digital-trails/qas-about-usgs-trail-data"
  }
}
```

Les règles de `traduction` restent une simple table, valeur par valeur. La BD TOPO a besoin de plus : elle combine `nature`, `acces_pieton` et `prive` pour décider de `foot=private`. On ne construira pas un moteur de règles pour autant. Une source dont la traduction dépasse une table garde une petite fonction Python dans son connecteur, et son fichier de pays la nomme. On ne généralisera qu'à l'arrivée d'une deuxième source du même protocole qui en aurait besoin.

### Ce qui reste hors du fichier, volontairement

- **Le nom du pays** vient de `Intl.DisplayNames`, c'est-à-dire du navigateur, dans la langue de la page. C'est déjà le cas dans `presentation.js`, et c'est bien ainsi.
- **Les altitudes** sont entièrement gérées par gpx2elev : le choix du modèle de terrain selon le lieu, sa couverture et son protocole. hike2gpx ne fait qu'afficher le modèle que gpx2elev renvoie dans son résultat (`modele`). Ajouter un pays dans hike2gpx ne demande donc rien pour l'altitude, et un modèle plus fin pour un pays s'ajoute dans gpx2elev. Le déclarer aussi dans le fichier du pays créerait deux propriétaires pour une même décision.
- **Le code des types de couche** (`tms`, `mvt`, `arcgis_export`) vit une fois dans `app.js`, et **le code des connecteurs**, un par protocole et non un par pays, vit côté Python. Le fichier du pays ne fait que les paramétrer. Le WFS de la BD TOPO devient ainsi le premier connecteur `wfs`. La Bavière ou les Pays-Bas pourraient le réutiliser, si un jour le gain le justifiait.

### Trois cas particuliers vérifiés le 23 octobre 2026

- **L'export ArcGIS des sentiers USGS est justifié.** L'USGS publie bien un WMS de ses sentiers (`USGSTrails/MapServer/WMSServer`, WMS 1.3.0), qui serait la voie standard avec `L.tileLayer.wms`. Mais ce WMS ne propose que CRS:84, EPSG:4269 et EPSG:4326, pas le Web Mercator (EPSG:3857) de la carte. L'`export` ArcGIS, lui, reprojette à la demande (`imageSR=3857`) : c'est le bon choix. Il devient le type générique `arcgis_export` dans `app.js`, au lieu d'un `getTileUrl` écrit dans le fichier du pays.
- **Le proxy des sentiers FEDME n'a pas de raison démontrée.** Le serveur `vt-fedme.idee.es` répond `Access-Control-Allow-Origin: *`, si bien que le navigateur peut lire ses tuiles directement. Ni hike2gpx ni le serveur commun `nico579_commons` n'imposent de politique CSP qui l'interdirait, et le commit d'origine ne donne aucune raison. Il faut vérifier dans le navigateur que le calque se charge sans le proxy, puis supprimer `TUILES_VECTORIELLES` et sa route. Le fichier de l'Espagne n'aura alors plus rien à déclarer côté serveur pour l'affichage.
- **Leaflet.VectorGrid n'est plus maintenu depuis 2017.** Il fonctionne et il est figé dans le dépôt, donc sans risque immédiat. Si les tuiles vectorielles se multiplient, il faudra regarder du côté de MapLibre, qui est aujourd'hui la référence du vectoriel. Pour un seul calque, la question ne se pose pas.

### Garde-fous et migration

Un test lit chaque fichier de `providers/` et vérifie que les champs obligatoires sont présents, que chaque libellé existe dans les deux langues, que `fond_defaut` désigne un fond déclaré, que chaque `type` est connu de la page et que chaque `chemins.protocole` est connu du serveur. Les oublis silencieux décrits plus haut deviennent ainsi des tests en échec.

La migration est mécanique : huit fichiers à convertir, `PAYS_CARTES` et les libellés des fonds et calques à retirer d'`app.js` et d'`application.py`, une fabrique de couches à écrire dans `app.js`. Elle se fait en une PR, sans changement visible pour l'utilisateur, et **avant** tout connecteur étranger, puisque c'est elle qui donne au serveur l'information « ce pays a une source de calcul ».

## Sources candidates, pays par pays

Chaque pays est jugé sur les quatre qualités de la BD TOPO. Le gain attendu dépend surtout des trous d'OSM : là où OSM est déjà complet, une source officielle n'apporte que des doublons à éliminer.

| Pays | Source | Accès par emprise | Accès piéton | Trous d'OSM | Verdict |
| --- | --- | --- | --- | --- | --- |
| États-Unis | USGS National Digital Trails | Oui, requête ArcGIS (vérifié) | Champ `hikerpedestrian` | Réels hors des parcs les plus fréquentés | **Premier connecteur** |
| Espagne | BTN du CNIG | Non pour les sentiers ; fichiers par feuille | À établir dans les classes BTN | Les plus importants des pays étudiés | **Deuxième**, avec un mécanisme de téléchargement |
| Allemagne | ATKIS Basis-DLM (par Land) | Selon le Land | Attributs de voie détaillés | Faibles en moyenne, variables | **À qualifier** Land par Land |
| Luxembourg | BD-L-GeoBase | Non ; un seul GeoPackage | `Track`/`Path` sans droit de passage | Faibles | Pilote technique éventuel |
| Suisse | swissTLM3D | Non confirmé ; fichier national ou STAC | Classes de voie détaillées | Très faibles | Différé |
| Pays-Bas | TOP10NL (PDOK) | Oui, OGC API Features | À documenter | Quasi nuls | Écarté du calcul |
| Autriche | GIP | Non ; export national | Graphe multimodal | Faibles en plaine, sentiers alpins mal couverts par le GIP | Écarté du calcul |
| Norvège | N50 | Non ; fichiers | Réseau généralisé | Faibles | Écarté du calcul |

### États-Unis : USGS National Digital Trails

C'est la source qui ressemble le plus à la BD TOPO par sa manière de servir les données. La couche `USGSTrails/MapServer/0` (« TrailsSegment ») déclare les capacités `Map,Query,Data` et rend jusqu'à 2000 tronçons par requête. On peut donc l'interroger par rectangle et paginer, comme `bdtopo.py` interroge le WFS français. Les données sont du [domaine public](https://www.usgs.gov/national-digital-trails/qas-about-usgs-trail-data) : il n'y a pas de licence à respecter, seulement la mention de la source, par courtoisie et pour la traçabilité.

L'essai du 23 octobre 2026 autour de Springdale (Utah), à l'entrée de Zion, sur un rectangle d'environ 8 × 7 km, a rendu **46 tronçons**. Tous étaient de type `Terra Trail`, tous portaient `hikerpedestrian = Yes`, et tous provenaient du National Park Service. Le schéma distingue l'accès des randonneurs, des vélos, des chevaux et des engins motorisés, ainsi que les pistes de neige ou d'eau. Il dit donc plus clairement que la BD TOPO si le passage à pied est autorisé.

Points à vérifier :

- la couverture varie selon l'agence qui a fourni la donnée (NPS, Forest Service, BLM, États) ; mesurer la part de `hikerpedestrian` vide hors des parcs nationaux ;
- exclure les types autres que terrestres (`Snow Trail`, `Water Trail`) ;
- traduire `hikerpedestrian = No` en `foot=no`, et une valeur vide en accès inconnu, signalé « à vérifier » comme les tronçons IGN.

Le calque d'affichage `usgsSentiers` existe déjà : on peut comparer à l'œil, sur la même vue, le parcours calculé et la donnée source.

### Espagne : BTN du CNIG

C'est là qu'OSM manque le plus de chemins parmi les pays étudiés, et la [BTN](https://centrodedescargas.cnig.es/CentroDescargas/btn) est un vrai réseau physique, publié avec une [licence d'attribution](https://centrodedescargas.cnig.es/CentroDescargas/detalleArchivo?sec=10318930). La valeur est donc la plus grande. Le mode d'accès, en revanche, est moins favorable que la première version de ce rapport ne le laissait espérer.

Un WFS existe : le service INSPIRE des réseaux de transport, `servicios.idee.es/wfs-inspire/transportes`, [décrit sur datos.gob.es](https://datos.gob.es/es/catalogo/e0dat0002-redes-de-transporte-de-espana) sous CC BY 4.0. L'essai du 23 octobre 2026 sur un rectangle d'environ 4 × 5 km dans le Val d'Aran n'a pourtant rendu que **6 tronçons** `RoadLink`, du réseau `ES.SCNE.IGR-RT`. Aucun ne portait de nature de voie dans la réponse. C'est le réseau routier national, pas la densité de sentiers de la BTN. Ce WFS ne remplace donc pas le téléchargement.

Le connecteur espagnol devra télécharger la BTN par feuille (Shapefile ou GeoPackage), la garder en cache et la relire par emprise. C'est le modèle des extraits Geofabrik plutôt que celui de la BD TOPO : plus de code, plus de disque, une mise à jour à gérer. Il faudra aussi identifier dans la BTN les classes de chemin et de sentier, et ce qu'elles disent de l'accès.

Les [sentiers FEDME](https://centrodedescargas.cnig.es/CentroDescargas/senderos-fedme) restent un calque d'affichage. Un itinéraire balisé GR, PR ou SL suit plusieurs chemins, dont beaucoup sont déjà dans OSM. L'ajouter comme voie indépendante créerait des doublons et des raccordements faux.

### Allemagne : ATKIS Basis-DLM

Par sa structure, l'ATKIS Basis-DLM est le cousin le plus direct de la BD TOPO : un modèle topographique national, au 1:25 000, avec un réseau de voies qui distingue routes, chemins agricoles et sentiers. Mais la cartographie allemande est l'affaire des Länder, et leurs conditions diffèrent.

- **Bavière** : selon la [lettre d'information de juin 2024](https://geodaten.bayern.de/odd/m/3/pdf/newsletter_archiv/2024_06.pdf), le Basis-DLM est publié en open data, en téléchargement NAS, Shape et GeoPackage pour toute la Bavière, et par WFS.
- **Rhénanie-Palatinat** : le [WFS du Basis-DLM](https://lvermgeo.rlp.de/fileadmin/lvermgeo/pdf/produktblaetter/BASIS_DLM_WFS.pdf) n'est ouvert qu'aux utilisateurs enregistrés. Ce n'est pas un accès libre.
- **Autres Länder** : la situation n'est pas établie ; il faut consulter le géoportail et la licence de chacun.

OSM est très complet en Allemagne, et le gain se limiterait probablement aux massifs (Alpes bavaroises, forêts de moyenne montagne). Avant tout connecteur, il faut mesurer ce gain sur une zone bavaroise, en comptant les tronçons qui survivent à la déduplication. Cela suppose aussi un provider d'affichage `de.js`.

### Luxembourg : BD-L-GeoBase

Le [thème transport de la BD-L-GeoBase](https://data.public.lu/fr/datasets/bd-l-geobase/) est un seul [GeoPackage](https://data.public.lu/fr/datasets/r/f789de46-1c3e-45db-afc6-7afe096a0ad8), en EPSG:2169, sous CC0. Le [catalogue d'attributs](https://download.data.public.lu/resources/bd-l-geobase/20240925-163507/contentsdescription-bd-l-geobase-v1.pdf) distingue `Track` et `Path`, sans dire si le passage est autorisé.

Son petit volume en fait un banc d'essai commode pour le mécanisme de téléchargement que l'Espagne exigera. Mais OSM y est déjà presque complet, et le gain sur les parcours serait faible. On ne le fera que si l'on veut éprouver ce mécanisme avant d'affronter la BTN.

### Suisse : swissTLM3D

[swissTLM3D](https://www.swisstopo.admin.ch/en/landscape-model-swisstlm3d) est une donnée excellente, en [réutilisation libre avec mention de swisstopo](https://www.swisstopo.admin.ch/en/faq-free-geodata). Elle se télécharge en GeoPackage, Shapefile ou géodatabase, en projection LV95. Une [collection STAC](https://data.geo.admin.ch/api/stac/v0.9/collections/ch.swisstopo.swisstlm3d) existe, mais nous n'y avons pas trouvé de découpage en tuiles exploitable par emprise ; l'accès par zone reste à confirmer.

Le réseau suisse de chemins est cependant parmi les mieux cartographiés au monde, dans OSM comme chez swisstopo. Le gain d'un connecteur serait faible pour un coût réel. Le calque WMTS de randonnée déjà affiché suffit pour l'instant.

### Pays-Bas, Autriche, Norvège : affichage seulement

- **Pays-Bas** : [TOP10NL](https://www.pdok.nl/downloadviewer/-/article/basisregistratie-topografie-brt-topnl) est même interrogeable par emprise, via l'[OGC API Features de PDOK](https://api.pdok.nl/brt/top10nl/ogc/v1?f=html&lang=en), sous CC BY 4.0. Mais OSM est quasi complet aux Pays-Bas : un connecteur n'ajouterait presque rien.
- **Autriche** : le [GIP](https://www.gip.gv.at/) est un graphe de transport multimodal, publié en export national. [AWIS.GIP](https://awisgip.at/daten.html) indique que sa base de sentiers alpins est encore en constitution, alors que c'est précisément là qu'un ajout aurait du sens.
- **Norvège** : [N50](https://kartkatalog.geonorge.no/metadata/uuid/ea192681-d039-42ec-b1bc-f3ce04c189ac) est généralisé, donc moins précis qu'OSM. La base fine [FKB-TraktorvegSti](https://dokument.geonorge.no/produktark/fkb-traktorvegsti/2025-01-07/fkb-traktorvegsti.pdf) n'est pas librement téléchargeable pour les utilisateurs extérieurs à Norge digitalt.

Ces trois pays gardent leurs fonds d'affichage. On ne reviendra sur leur cas que si un utilisateur signale un manque précis d'OSM.

## Plan de réalisation

1. **Passer à un fichier JSON par pays, lu par le serveur** (voir « Les providers : un seul fichier par pays »). Les huit providers deviennent des fichiers de données. `PAYS_CARTES`, les libellés des fonds et calques et, s'il survit à la vérification, `TUILES_VECTORIELLES` y sont absorbés. `routableOverlay` cède la place au bloc `chemins`, que le serveur n'annonce que s'il sait le calculer. Aucun changement n'est visible pour l'utilisateur, mais une coche ne peut plus promettre ce que le calcul ne fait pas.
2. **Généraliser la fusion.** `ajouter_ign()` devient l'ajout de tronçons déjà exprimés en étiquettes OSM (`highway=path` ou `track`, `foot=yes`, `no` ou absent), avec une étiquette de source générique, par exemple `hike2gpx=ign` ou `hike2gpx=usgs`, que le profil BRouter, la table d'étiquettes et `portions_ign()` traitent de la même façon. Chaque connecteur se contente de traduire sa source en étiquettes OSM. C'est la pratique ordinaire des imports dans OSM, avec des règles de traduction par source à la manière d'ogr2osm. On évite ainsi de créer un modèle d'attributs maison, et la fusion parle déjà ce langage. La déduplication à 12 m, le raccordement à 15 m et la règle « OSM juge des accès » restent communs.
3. **Écrire le connecteur `arcgis_query`, jumeau du connecteur `wfs` issu de `bdtopo.py`**, et le paramétrer par le bloc `chemins` du fichier des États-Unis. Même structure : requête par emprise paginée, cache par tuile avec la même durée de vie, filtre et traduction lus dans le fichier du pays (`Terra Trail` seulement, `hikerpedestrian` vers `foot`). Les deux connecteurs étant jumeaux, on les comparera ligne à ligne pour ne garder que les différences voulues.
4. **Valider sur Springdale avant d'activer.** Compter les tronçons USGS qui survivent à la déduplication, mesurer leurs raccordements à OSM, comparer un parcours OSM seul et un parcours enrichi dans Zion, et vérifier qu'aucun parcours n'emprunte un tronçon `foot=no`. Faire de même sur une zone hors parc national, où la donnée vient d'une autre agence.
5. **Espagne ensuite**, avec le connecteur `fichier` : téléchargement des feuilles BTN, mises en cache puis relues par emprise. Même validation ensuite sur une zone pyrénéenne. Le Luxembourg ne sert de banc d'essai que si ce mécanisme mérite d'être éprouvé à petite échelle d'abord.
6. **Allemagne à qualifier** : mesurer le gain sur une zone bavaroise avant de décider d'un provider et d'un connecteur.

Dans tous les cas, si la source officielle ne répond pas, le calcul retombe sur OSM seul. Le résultat et l'export nomment la source réellement utilisée.

**État du chantier : analyse seulement.** Aucun chemin étranger n'est encore injecté dans les tuiles BRouter. Hors de France, les calques de sentiers sont marqués « affichage seul », et le calcul utilise OSM seul.
