# Sources officielles de chemins pour le calcul BRouter

Rapport du 23 octobre 2026, écrit après la release 0.3.0. En France, hike2gpx ajoute à OpenStreetMap les chemins de la BD TOPO que BRouter ne connaîtrait pas sans elle. La question posée ici est simple : d'autres pays ont-ils une source officielle qui rendrait le même service ? Le rapport y répond par une mesure, puis examine les providers d'affichage par pays et la façon de les organiser.

Mise à jour du 24 octobre 2026 : comparaison avec deux autres sources officielles.

## Verdict

**L'Allemagne et la Tchéquie sont deux autres cas où une source topographique nationale comble beaucoup de lacunes géométriques d'OSM.** La BD TOPO ajoute 18 % à 100 % de longueur potentielle sur les tuiles françaises étudiées. En Bavière, le Basis-DLM ajoute 12 % à 37 % ; à Rosa, en Thuringe, 79 % sur la tuile du village et 127 % sur la tuile voisine la plus dense. Quatre zones tchèques ZABAGED donnent 40 % à 66 %. Les États-Unis, la Suisse et les Pays-Bas restent à 0 % à 12 %. Les essais dans deux parcs canadiens donnent 2 % à 15 % et ceux de trois itinéraires néo-zélandais 0 % à 20 %.

Ces pourcentages mesurent des **longueurs de voies candidates**, pas un gain garanti pour une randonnée. À Rosa, presque tout le supplément est classé `Fahrwegachse` (chemins agricoles) et le WFS ne donne pas de permission piétonne explicite. La PR ajoute donc un calque ATKIS et permet la fusion pour BRouter en marquant les portions utilisées « à vérifier ». Les WFS natifs couvrent la Bavière et la Thuringe ; les tuiles vectorielles ATKIS dérivées de basemap.de couvrent les quatorze autres Länder, toujours par petite emprise. TopPlusOpen reste le fond de carte allemand pour tout le pays.

## La mesure

### Méthode

L'outil `tools/essai_sources_chemins.py` réutilise le code de hike2gpx sans le modifier. Pour chaque massif, il procède en quatre temps.

1. **Trouver une zone dense en chemins.** Une zone pauvre en chemins ne dirait rien : la source officielle et OSM y auraient tous deux peu de chose. L'outil lit donc la source officielle sur la tuile de 0,05° du massif (environ 5,5 × 4 km) et sur ses voisines : 3 × 3 tuiles pour la France, les États-Unis, la Bavière et Rosa ; cinq en croix pour la Suisse et les Pays-Bas, dont les services paginent plus lentement. Il garde la tuile où la source a le plus de kilomètres. La tuile qui contient Rosa est également mesurée séparément. En France, seuls les sentiers, chemins et escaliers comptent pour le classement. Une première passe classée sur toute la BD TOPO avait retenu Fréjus au lieu du massif de l'Estérel : une ville l'emporte sur un massif dès que les routes comptent.
2. **Lire OSM sur cette tuile**, avec 1 km de marge, par la même requête Overpass que le calcul (`franchissements.requete()`), pour ne pas compter comme absent un chemin coupé au bord.
3. **Appliquer la règle de fusion** : un morceau de la source est « nouveau » quand moins de la moitié de sa longueur passe à moins de 12 m d'une voie OSM praticable (`fusion.parts_couvertes()`, seuil `PART_COUVERTE_MAX`). C'est exactement ce que fait `fusion.ajouter_ign()` avec la BD TOPO.
4. **Rapporter les kilomètres nouveaux** à la longueur du réseau OSM praticable de la tuile. Ce « gain du réseau » est un potentiel géométrique : l'accessibilité et la continuité doivent être vérifiées avant d'en déduire un itinéraire supplémentaire.

Les sources sont la BD TOPO (WFS de la Géoplateforme), les sentiers USGS National Digital Trails (type `Terra Trail` seulement), swissTLM3D « Strassen und Wege » (API de geo.admin.ch), TOP10NL `wegdeel_hartlijn` (OGC API de PDOK), puis les objets `AX_WegPfadSteig` et `AX_Fahrwegachse` du [WFS bavarois](https://geodatenonline.bayern.de/geodatenonline/seiten/wfs_atkis) et du [WFS de Thuringe](https://geoportal.thueringen.de/media/Download/Geoproxy/Allgemeine_Beschreibung_der_frei_verfuegbaren_Dienste_WFS_opendata_Geobasisdaten-TLBG.pdf). Les données OSM sont celles d'Overpass le 23 octobre 2026.

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

### Allemagne : Bavière et Rosa (Thuringe)

| Zone | Centre de la tuile | Voies Basis-DLM | Réseau OSM | Retenues comme absentes d'OSM | Gain géométrique potentiel |
| --- | --- | ---: | ---: | ---: | ---: |
| Rosa, tuile du village | 50,725 N 10,275 E | 149,8 km | 96,8 km | 76,6 km | **+79 %** |
| Rosa, tuile voisine la plus dense | 50,675 N 10,325 E | 186,8 km | 89,4 km | 113,4 km | **+127 %** |
| Bavière, forêt franconienne | 50,275 N 11,475 E | 201,4 km | 179,2 km | 66,7 km | **+37 %** |
| Bavière, forêt bavaroise | 48,975 N 13,275 E | 99,0 km | 105,6 km | 32,5 km | **+31 %** |
| Bavière, Berchtesgaden | 47,625 N 12,925 E | 124,5 km | 145,5 km | 29,6 km | **+20 %** |
| Bavière, Allgäu | 47,575 N 10,275 E | 100,1 km | 154,2 km | 18,2 km | **+12 %** |

La tuile du centre de Rosa est mesurée en plus de la règle habituelle « choisir la voisine la plus dense », afin de contrôler précisément le lieu signalé. Parmi ses 76,6 km retenus, 76,3 km sont des `AX_Fahrwegachse` et 0,3 km des `AX_WegPfadSteig`. Dans la voisine dense, les 113,4 km retenus sont tous des `AX_Fahrwegachse`. Cette classe comprend des axes de chemins agricoles ; le service ne donne pas de droit de passage piéton fiable. Le résultat confirme une différence de contenu avec OSM, pas que chaque voie constitue un sentier ouvert et raccordable.

Les requêtes sont limitées à une emprise de 0,05° par [WFS ATKIS de Bavière](https://geodatenonline.bayern.de/geodatenonline/seiten/wfs_atkis) et [WFS Basis-DLM de Thuringe](https://geoportal.thueringen.de/media/Download/Geoproxy/Allgemeine_Beschreibung_der_frei_verfuegbaren_Dienste_WFS_opendata_Geobasisdaten-TLBG.pdf), avec pagination. Les coordonnées GML bavaroises sont renvoyées latitude puis longitude, celles de Thuringe longitude puis latitude ; l'outil les remet toutes en `[latitude, longitude]` avant la comparaison. Les filtres FES explicites ont été nécessaires, car les requêtes `BBOX` KVP testées ne rendaient pas correctement les tronçons sur ces services. Le serveur local applique le même découpage par tuiles et le même cache de trente jours que BD TOPO.
Les deux WFS annoncent une licence CC BY 4.0 ; le service thuringien demande la mention « © GDI-Th ». Le calque affiche les deux producteurs et la licence dans l'attribution Leaflet.

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

### Tchéquie : ZABAGED, essais du 24 octobre 2026

La [base topographique nationale ZABAGED](https://ags.cuzk.gov.cz/opendata/) est accessible par emprise. Le [service officiel ArcGIS REST/WFS](https://ags.cuzk.gov.cz/arcgis/rest/services/ZABAGED_POLOHOPIS/MapServer) expose séparément les sentiers `Pěšina` (couche 82) et les chemins `Cesta` (couche 83). Le test a additionné ces deux classes, puis appliqué exactement la règle de recouvrement utilisée pour la BD TOPO : moins de la moitié du tracé à 12 m ou moins d'une voie OSM praticable. Pour chaque massif, la tuile la plus dense en chemins officiels parmi neuf tuiles de 0,05° est retenue.

| Zone | Centre de la tuile | Sentiers et chemins ZABAGED | Réseau OSM | Retenus comme absents d'OSM | Gain du réseau | Dont `Pěšina` |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Šumava | 49,125 N 13,475 E | 101,7 km | 84,7 km | 39,2 km | **+46,3 %** | 8,1 km |
| Krkonoše | 50,675 N 15,775 E | 122,7 km | 96,7 km | 38,3 km | **+39,6 %** | 23,1 km |
| České Švýcarsko | 50,875 N 14,425 E | 140,0 km | 96,8 km | 63,4 km | **+65,5 %** | 27,8 km |
| Moravský kras | 49,425 N 16,775 E | 135,7 km | 114,1 km | 50,8 km | **+44,6 %** | 0,0 km |

Un contrôle de sensibilité avec une tolérance de **20 m** au lieu de 12 m retient encore 34,1 km à Šumava, 35,3 km à Krkonoše, 60,8 km en Suisse bohémienne et 49,1 km dans le Karst morave. Un simple écart de quelques mètres entre les deux jeux ne suffit donc pas à expliquer l'essentiel des différences. Ce contrôle n'établit toutefois ni le droit de passage, ni la continuité des tracés ; `Cesta` comprend aussi des chemins non entretenus et des voies de parc ou de cimetière. Aucune intégration au calcul ou au calque n'est faite sur la seule base de ces ratios.

Deux autres bases nationales méritent un essai, sans ratio à ce stade : la [BDOT10k polonaise](https://www.geoportal.gov.pl/en/data/topographic-objects-database-bdot10k/), disponible gratuitement en vecteur mais principalement distribuée par paquets ou classes, et le [DLM Verkehr autrichien](https://www.bev.gv.at/Services/Produkte/Digitales-Landschaftsmodell/Verkehr.html), disponible en téléchargement sans accès en ligne par emprise. Leur mode de diffusion demande une extraction préalable pour un essai comparable.

### Canada et Nouvelle-Zélande : essais du 24 octobre 2026

Le même outil a comparé deux jeux de données supplémentaires aux voies OSM praticables. Il a choisi la tuile de 0,05° la plus riche en voies officielles parmi les neuf tuiles autour de chaque lieu. La colonne « part absente » rapporte les kilomètres nouveaux à ceux de la source officielle ; le « gain du réseau » les rapporte aux kilomètres OSM, comme dans les tableaux précédents.

| Zone | Centre de la tuile | Source officielle | Réseau OSM | Absents d'OSM | Part absente de la source | Gain du réseau |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| CA, Yoho | 51,425 N 116,525 O | 14,5 km | 20,8 km | 3,0 km | 21 % | **+14,6 %** |
| CA, Banff | 51,175 N 115,525 O | 46,5 km | 105,9 km | 2,4 km | 5 % | **+2,3 %** |
| NZ, Routeburn | 44,725 S 168,175 E | 9,0 km | 11,9 km | 2,3 km | 26 % | **+19,6 %** |
| NZ, Tongariro | 39,225 S 175,525 E | 20,8 km | 27,9 km | 0,0 km | 0 % | **0 %** |
| NZ, Kepler | 45,475 S 167,675 E | 24,4 km | 47,1 km | 0,0 km | 0 % | **0 %** |

Au Canada, la requête sur le [jeu de Parcs Canada](https://open.canada.ca/data/en/dataset/64a90e8d-5bc0-4027-8645-b5881b4068d4) garde les sentiers officiels sans interdiction estivale (`Official_Officiel=1`, `Restr_Sum_Ete_Interd=0`). Ce jeu porte sur les lieux gérés par Parcs Canada : ces ratios locaux ne valent pas pour toutes les provinces canadiennes. En Nouvelle-Zélande, la [couche DOC « Walking and Tramping Experiences routes »](https://services1.arcgis.com/3JjYDyG3oajxU6HO/ArcGIS/rest/services/DOC_Walking_Experiences/FeatureServer/1) regroupe les itinéraires de marche gérés par le DOC, pas tous les chemins du pays. À Routeburn, les 2,3 km retenus portent la classe de difficulté `Expert`. Le service indique que certains parcours peuvent être fermés et renvoie aux alertes du DOC ; ce test géométrique ne contrôle pas leur ouverture.

Ces cinq essais montrent un apport local jusqu'à 20 %, mais ne justifient pas encore une source de calcul nationale comparable à la BD TOPO ou à ATKIS. En particulier, un tracé décalé de plus de 12 m peut être compté comme nouveau sans l'être sur le terrain. La [base topographique finlandaise](https://www.maanmittauslaitos.fi/en/maps-and-spatial-data/datasets-and-interfaces/product-descriptions/topographic-database) est une piste de couverture nationale, mais son [API nécessite une clé](https://www.maanmittauslaitos.fi/en/maastotietokannan-kyselypalvelu/tekninen-kuvaus) ; aucun ratio finlandais n'est avancé sans interrogation du jeu de données. Les sentiers BTN25 espagnols sont distribués par feuilles et n'ont pas été mesurés ici.

### Fraîcheur des sentiers USGS

Le jeu USGS est toujours alimenté. Sur 607 202 tronçons, 443 690 ont été chargés en 2026, le dernier le 14 septembre 2026. Les années précédentes donnent 19 433 tronçons en 2022, aucun en 2023, 34 173 en 2024 et 13 256 en 2025. Mais `loaddate` est la date d'entrée dans la base nationale, non celle d'un relevé de terrain. L'USGS agrège ce que lui transmettent le National Park Service, le Forest Service, le BLM et les États, et le chargement massif de 2026 ressemble à un rechargement complet. La fraîcheur réelle dépend de ces agences, et rien dans la donnée ne permet de juger l'effet des restrictions budgétaires fédérales.

### Limites de la mesure

- **Une tuile par massif**, soit une vingtaine de km² chacune, et deux tuiles autour de Rosa. Sept zones françaises, sept zones américaines/suisses/néerlandaises et cinq zones allemandes donnent des exemples concrets, pas une moyenne nationale.
- **Les cinq nouveaux essais sont également locaux.** Deux parcs canadiens et trois itinéraires néo-zélandais ne donnent ni une moyenne nationale ni une mesure des chemins hors des espaces couverts par Parcs Canada et le DOC.
- **Les quatre essais tchèques sont locaux eux aussi.** ZABAGED couvre le pays, mais le ratio de ces massifs ne se généralise pas sans échantillonnage d'autres régions. Une validation sur le terrain et des attributs d'accès seront nécessaires avant d'utiliser ces voies pour le routage.
- **« Absent d'OSM » est un plafond.** Un tracé officiel décalé de plus de 12 m de son équivalent OSM compte comme nouveau. Cela vaut aussi pour la BD TOPO : le gain français est peut-être un peu surestimé, l'écart entre la France et les autres pays non.
- **Un chemin nouveau n'est pas forcément praticable.** hike2gpx affiche déjà les chemins IGN comme « non vérifiés », et la mesure ne dit rien de leur état sur le terrain.
- **Les chemins agricoles allemands demandent un contrôle.** `Fahrwegachse` fournit l'essentiel du gain à Rosa et dans les massifs bavarois. La présence géométrique ne prouve ni l'accès public ni le bon raccordement à OSM. Les tuiles BRouter ajoutées gardent donc une pénalité et signalent leurs portions « à vérifier ».
- **Les sources ATKIS n'ont pas toutes la même précision géométrique.** Les mesures ci-dessus utilisent les WFS natifs de Bavière et de Thuringe. Dans les autres Länder, l'application lit les tuiles vectorielles de présentation de basemap.de au zoom maximal 15 : elles couvrent le pays, mais leur généralisation et leurs raccordements peuvent différer des objets natifs. Aucun pourcentage de gain OSM n'est extrapolé à ces Länder. L'Espagne reste non mesurée : les sentiers BTN exigent des feuilles à télécharger.

Pour refaire la mesure :

```
python tools/essai_sources_chemins.py            toutes les zones
python tools/essai_sources_chemins.py US Var     un pays, ou les zones dont le nom contient « Var »
python tools/essai_sources_chemins.py DE Rosa    Bavière et Rosa (Thuringe)
python tools/essai_sources_chemins.py CA         Banff et Yoho
python tools/essai_sources_chemins.py NZ         Tongariro, Kepler et Routeburn
python tools/essai_sources_chemins.py CZ         quatre massifs tchèques
```

## Ce que fait la BD TOPO, et pourquoi elle marche

La chaîne française tient en trois modules.

- `bdtopo.py` interroge le WFS de la Géoplateforme (`BDTOPO_V3:troncon_de_route`) autour de la zone demandée, par pages de 5000 tronçons, et garde un cache d'un mois par tuile. Il lit `nature`, `acces_pieton`, `acces_vehicule_leger` et `prive`.
- `fusion.py` ne garde un tronçon IGN que si moins de la moitié de sa longueur passe à moins de 12 m d'une voie OSM : sinon OSM le connaît déjà, et OSM reste juge des accès. Il raccorde les bouts gardés entre eux, et à la voie OSM la plus proche quand elle passe à moins de 15 m. Il étiquette chaque tronçon `highway=path` + `hike2gpx=ign`, traduit un accès piéton restreint en `foot=private`, et écrit le tout en PBF OSM.
- `maison.py` fabrique les tuiles BRouter à partir de ce PBF et recalcule les franchissements sur le réseau fusionné.

Ce succès tient à quatre qualités réunies. La BD TOPO **comble de vrais trous d'OSM** ; la mesure en donne maintenant l'ampleur. C'est un **réseau physique**, qui dit la nature de chaque voie. Elle est **interrogeable par emprise** : on demande un rectangle, on reçoit ses tronçons, sans rien télécharger d'avance. Elle est enfin **nationale et homogène**.

La première qualité est celle qui manque ailleurs. Les trois autres se retrouvent en partie : les services américain, suisse et néerlandais répondent tous par emprise. Mais une source bien servie qui n'ajoute rien n'apporte rien au calcul.

## Une deuxième source pour les tuiles BRouter maison

La mesure allemande donne maintenant un second cas réel. La chaîne conserve ses interfaces historiques (`ajouter_ign()`, `portions_ign()`), mais accepte une source `atkis` en plus de `ign` :

- `atkis.py` interroge les WFS de Bavière et de Thuringe par tuiles de 0,05°, avec pagination, et `basemap_atkis.py` lit uniquement les tuiles vectorielles qui touchent la zone sélectionnée dans les quatorze autres Länder. Le cache dure trente jours ;
- `maison.py` choisit le cache officiel selon la source demandée et ne mélange jamais des tuiles françaises et allemandes dans une fabrication ;
- `fusion.py` applique le même seuil de recouvrement et les mêmes raccordements, avec l'étiquette `hike2gpx=atkis` ; les extrémités coupées par les tuiles vectorielles se rejoignent à moins de 1,5 m, seulement dans le même Land et au même niveau ;
- `brouter.py` pénalise également `ign` et `atkis` ; `application.py` lit la source dans les messages de BRouter et nomme correctement les portions à vérifier ;
- `providers/de.js` propose le calque ATKIS et la coche de calcul. Le serveur accepte uniquement les identifiants de sources connus.

Le calque et le calcul portent sur les mêmes voies dans toute l'Allemagne. Aucun GeoPackage de Land entier n'est téléchargé : le service [basemap.de Web Vektor](https://basemap.de/produkte-und-dienste/web-vektor/) fournit les petits fichiers PBF officiels à la demande. Seules les classes de voies pédestres ou agricoles du calque `Verkehrslinie` sont retenues, avec découpage sur les limites de la zone demandée. Le contrôle d'accès piéton reste celui d'OSM et la pénalité « à vérifier » reste appliquée.

Une tuile de 0,05° a été lue directement dans chacun des quatorze Länder desservis par basemap.de : Berlin, Bade-Wurtemberg, Brême, Hesse, Hambourg, Mecklembourg-Poméranie-Occidentale, Basse-Saxe, Rhénanie-du-Nord-Westphalie, Rhénanie-Palatinat, Sarre, Saxe, Brandebourg, Saxe-Anhalt et Schleswig-Holstein. Chaque lecture a rendu des voies de son Land (de 125 à 2 996 fragments après découpage). Ce contrôle valide l'accès aux données, pas la continuité du réseau ni un gain mesuré face à OSM.

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

**Ce qui est fait.** Sans attendre la refonte, deux tests gardent déjà contre les oublis silencieux. Dans `tests/page.test.cjs`, chaque fond et chaque calque de chaque provider doit avoir son libellé en français et en anglais, et le fond par défaut doit exister. Dans `tests/test_application.py`, `PAYS_CARTES` doit couvrir exactement les providers présents. On a vérifié qu'ils échouent bien sur un oubli : un libellé anglais retiré au fond suisse, une entrée retirée de `PAYS_CARTES`.

**La refonte des providers attendra une PR dédiée.** Deux sources de calcul rendent désormais utile le bloc `chemins` proposé ci-dessus, surtout pour déclarer précisément leur aire de couverture côté serveur. Cette PR ajoute le connecteur allemand au mécanisme actuel afin de livrer et tester les chemins de Rosa sans convertir tous les providers. La migration devra vérifier que chaque `type` de couche est connu de la page et chaque `chemins.protocole` du serveur, et déclarer les Länder couverts plutôt que seulement le pays.

## Sources candidates, pays par pays

| Pays | Source | Accès par emprise | Gain mesuré | Verdict |
| --- | --- | --- | --- | --- |
| États-Unis | USGS National Digital Trails | Oui, requête ArcGIS | 0 à 10 %, accès piéton souvent inconnu | Affichage seulement |
| Suisse | swissTLM3D | Oui, API geo.admin.ch | 4 à 5 % | Affichage seulement |
| Pays-Bas | TOP10NL (PDOK) | Oui, OGC API Features | 10 à 12 %, plafond | Affichage seulement |
| Espagne | BTN du CNIG | Non pour les sentiers ; fichiers par feuille | Non mesuré | À mesurer avant un connecteur |
| Allemagne | ATKIS Basis-DLM, WFS natifs et basemap.de Web Vektor | Oui, petites emprises dans les 16 Länder | +12 à +37 % en Bavière ; +79 % sur la tuile du village de Rosa, autres Länder non mesurés | Calque et calcul BRouter dans toute l'Allemagne, voies à vérifier |
| Luxembourg | BD-L-GeoBase | Non ; un seul GeoPackage | Non mesuré ; OSM réputé complet | Affichage seulement |
| Autriche | GIP | Non ; export national | Non mesuré ; sentiers alpins mal couverts par le GIP | Affichage seulement |
| Norvège | N50 | Non ; fichiers | Non mesuré ; réseau généralisé | Affichage seulement |

### États-Unis : USGS National Digital Trails

Sur le plan technique, c'est la source la plus proche de la BD TOPO. La couche `USGSTrails/MapServer/0` déclare les capacités `Map,Query,Data`, rend jusqu'à 2000 tronçons par requête, et dit pour chacun si les randonneurs y sont admis (`hikerpedestrian`). Les données sont du [domaine public](https://www.usgs.gov/national-digital-trails/qas-about-usgs-trail-data).

La mesure la disqualifie pourtant pour le calcul. Elle ne recense que les sentiers officiels des agences, peu nombreux, et OSM les a déjà presque tous : de 0 % à 10 % de gain sur quatre massifs, dont une forêt reculée (la Gila) où rien ne manquait. Le calque d'affichage `usgsSentiers` reste utile pour voir les sentiers officiels sur la carte.

### Espagne : BTN du CNIG

La [BTN](https://centrodedescargas.cnig.es/CentroDescargas/btn) est un vrai réseau physique, sous [licence d'attribution](https://centrodedescargas.cnig.es/CentroDescargas/detalleArchivo?sec=10318930), et l'on dit OSM moins complet en Espagne rurale. C'est une impression, pas une mesure.

Le mode d'accès est défavorable. Le WFS INSPIRE des réseaux de transport, `servicios.idee.es/wfs-inspire/transportes` ([datos.gob.es](https://datos.gob.es/es/catalogo/e0dat0002-redes-de-transporte-de-espana), CC BY 4.0), n'a rendu que 6 tronçons routiers du réseau `ES.SCNE.IGR-RT` sur 4 × 5 km dans le Val d'Aran, sans nature de voie. Les sentiers de la BTN ne s'obtiennent qu'en téléchargeant des feuilles. Avant tout connecteur, il faut télécharger une feuille sur une zone pyrénéenne et une autre en Espagne intérieure, ajouter une fonction de lecture à l'outil de mesure, et ne poursuivre que si le gain approche celui de la BD TOPO.

Les [sentiers FEDME](https://centrodedescargas.cnig.es/CentroDescargas/senderos-fedme) restent un calque d'affichage. Un itinéraire balisé GR, PR ou SL suit plusieurs chemins, dont beaucoup sont déjà dans OSM : l'ajouter comme voie indépendante créerait des doublons et des raccordements faux.

### Allemagne : ATKIS Basis-DLM

Par sa structure, l'ATKIS Basis-DLM est le cousin le plus direct de la BD TOPO : un modèle topographique national au 1:25 000, avec un réseau de voies qui distingue routes, chemins agricoles et sentiers. La cartographie allemande est l'affaire des Länder : la Bavière et la Thuringe fournissent ici leurs WFS natifs, tandis que [basemap.de Web Vektor](https://basemap.de/produkte-und-dienste/web-vektor/) assemble les voies des seize Länder dans un modèle dérivé, disponible par tuiles vectorielles. La [description du modèle](https://basemap.de/data/produkte/web_vektor/meta/bm_web_vektor_datenmodell.html) identifie les chemins dans la couche `Verkehrslinie`.

La comparaison contredit l'hypothèse selon laquelle OSM serait partout aussi complet que le Basis-DLM : les tuiles bavaroises vont de +12 % à +37 %, et Rosa atteint +79 % sur la tuile du village. Une autre réserve apparaît : presque tout ce gain est porté par `AX_Fahrwegachse`, sans permission piétonne explicite. Le calque sert à voir ces voies et le calcul les propose avec pénalité et signalement, sans les présenter comme des passages garantis.

### Suisse, Pays-Bas, Luxembourg, Autriche, Norvège

- **Suisse** : [swissTLM3D](https://www.swisstopo.admin.ch/en/landscape-model-swisstlm3d) est une donnée excellente, en [réutilisation libre](https://www.swisstopo.admin.ch/en/faq-free-geodata), et son API répond par emprise. Mais OSM l'égale presque : 4 à 5 % de gain.
- **Pays-Bas** : [TOP10NL](https://www.pdok.nl/downloadviewer/-/article/basisregistratie-topografie-brt-topnl) est servi par l'[OGC API Features de PDOK](https://api.pdok.nl/brt/top10nl/ogc/v1?f=html&lang=en), sous CC BY 4.0. Le gain de 10 à 12 % sur la Veluwe est un plafond, gonflé par des routes et des écarts de tracé.
- **Luxembourg** : le [thème transport de la BD-L-GeoBase](https://data.public.lu/fr/datasets/bd-l-geobase/) est un seul GeoPackage en CC0, mais OSM y est réputé complet.
- **Autriche** : le [GIP](https://www.gip.gv.at/) est un graphe de transport ; [AWIS.GIP](https://awisgip.at/daten.html) indique que sa base de sentiers alpins est encore en constitution, alors que c'est là qu'un ajout aurait du sens.
- **Norvège** : [N50](https://kartkatalog.geonorge.no/metadata/uuid/ea192681-d039-42ec-b1bc-f3ce04c189ac) est généralisé, donc moins précis qu'OSM, et la base fine [FKB-TraktorvegSti](https://dokument.geonorge.no/produktark/fkb-traktorvegsti/2025-01-07/fkb-traktorvegsti.pdf) n'est pas librement téléchargeable.

Tous gardent leurs fonds d'affichage. On ne reviendra sur leur cas que si un utilisateur signale un manque précis d'OSM.

## Plan

1. **Tester la connexion et l'accès à pied autour de Rosa.** La comparaison géométrique est forte, mais des itinéraires BRouter doivent confirmer la continuité et l'utilisateur doit vérifier les chemins agricoles sur le terrain.
2. **Étendre les Länder par services de données par emprise**, après contrôle de leur licence, de leur schéma et de leurs attributs d'accès. Le fond TopPlusOpen, national, ne suffit pas à construire un réseau de routage précis.
3. **Comparer les chemins basemap.de aux données natives dans d'autres Länder** et contrôler sur le terrain les raccordements des tuiles vectorielles avant d'interpréter les gains d'itinéraire.
4. **Continuer la qualité de la BD TOPO française**, notamment ses règles d'accès et ses raccordements ; mesurer l'Espagne sur deux feuilles BTN avant d'envisager le calcul.

**État : cinq zones allemandes mesurées, calque et calcul ATKIS disponibles par zone dans les seize Länder.** Les WFS natifs servent la Bavière et la Thuringe ; basemap.de Web Vektor sert les autres. Aux États-Unis, en Suisse et aux Pays-Bas, les calques restent pour l'affichage seul.
