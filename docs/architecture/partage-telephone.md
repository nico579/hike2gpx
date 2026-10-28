# Partage au téléphone : le contrat entre le PC et l'application Android

Le téléphone prend ses lots là où ils sont publiés, sur GitHub
([hike2gpx-bundles](https://github.com/nico579/hike2gpx-bundles)). Mais deux
sortes de données n'existent que sur le PC de l'utilisateur : les lots OSM
qu'il a préparés hors des pays routables, et les fonds de carte, dont le
SCAN 25 de l'IGN. Ce dernier n'est pas une donnée libre ; le PC le fabrique
avec la clé IGN de l'utilisateur, pour son seul usage, et ne peut donc pas le
publier. Le PC les sert alors lui-même à son téléphone, sur le réseau local.

Le partage reprend le dépôt tel qu'il existe déjà (`hike2gpx/depot.py`) : même
catalogue, mêmes empreintes, mêmes adresses relatives. Le téléphone n'a qu'un
lecteur de dépôt, qu'il lise GitHub ou le PC ; seuls changent l'adresse et le
jeton. Ce document fixe ce que l'application Android peut attendre du PC ; il
ne change qu'avec elle.

## 1. Le QR code

Le PC affiche, dans ses Réglages, un QR code qui contient ce texte :

```
hike2gpx://depot?url=<adresse du catalogue, encodée URL>&jeton=<jeton>
```

Par exemple, avant encodage de l'adresse :

```
url   = http://192.168.1.20:8799/depot/catalog.json
jeton = Yp3…(43 caractères base64 URL)…
```

- l'adresse est `http://<IP locale du PC>:<port>/depot/catalog.json` ; le port
  vaut 8799, ou le suivant de libre (jusqu'à 8808) ;
- le jeton est tiré par `secrets.token_urlsafe(32)` : 32 octets aléatoires,
  43 caractères `A-Z a-z 0-9 - _`. Il change à **chaque ouverture** du
  partage : un QR code ancien ne vaut plus rien ;
- les deux paramètres sont encodés comme une requête de formulaire
  (`urllib.parse.urlencode`) ; le lecteur les décode avant usage.

## 2. Les requêtes

Toute requête du téléphone, catalogue et fichiers, porte l'en-tête

```
Authorization: Bearer <jeton>
```

Sans lui, ou avec un jeton faux ou périmé, la réponse est **401**, avec
`WWW-Authenticate: Bearer realm="hike2gpx"`. Les autres réponses :

| Requête                          | Réponse                                                        |
|----------------------------------|----------------------------------------------------------------|
| `GET /depot/catalog.json`        | 200, le catalogue (JSON UTF-8), `Cache-Control: no-store`      |
| `GET /depot/<url d'un fichier>`  | 200, le fichier entier, `Accept-Ranges: bytes`                 |
| idem avec `Range: bytes=N-`      | 206, la suite du fichier, `Content-Range: bytes N-F/T`         |
| `Range` hors du fichier          | 416, `Content-Range: bytes */T`                                |
| `HEAD` sur les mêmes adresses    | les mêmes en-têtes, sans corps                                 |
| toute autre adresse              | 404                                                            |
| toute autre méthode              | 405                                                            |

`<url d'un fichier>` est l'adresse que donne le catalogue, relative à celle du
catalogue : `E5_N40/E5_N40.rd5`, `fonds/E5_N40-scan25.mbtiles`. Une seule
plage par requête (`bytes=N-`, `bytes=N-M` ou `bytes=-N`) ; une autre forme
est ignorée et le fichier part en entier, comme HTTP le permet.

## 3. Le catalogue

Le format du dépôt, inchangé : `"format": 1` et la liste `"lots"`, chaque
fichier avec sa taille, son SHA-256 et son adresse. Le PC y ajoute une liste
facultative `"fonds"` :

```json
{"format": 1, "genere": "2026-10-28T14:02:11Z",
 "lots": [{"case": "E5_N40", "type": "osm", "fournisseurs": [], "zone": [43.0, 5.0, 44.0, 6.0],
           "sources": {"osm": "2026-10-25T21:21:21Z"}, "octets": 135000000,
           "fichiers": [{"nom": "E5_N40.rd5", "octets": 98000000, "sha256": "…", "url": "E5_N40/E5_N40.rd5"},
                        {"nom": "manifest.json", "octets": 812, "sha256": "…", "url": "E5_N40/manifest.json"}]}],
 "fonds": [{"nom": "E5_N40-scan25", "zone": [40, 5, 45, 10], "zoom": [6, 13], "source": "scan25",
            "octets": 412000000, "sha256": "…", "url": "fonds/E5_N40-scan25.mbtiles"}]}
```

Un fond de carte :

- `nom` : le nom du fichier sans extension, `<case>-<source>` pour une case
  entière, `<case>-<source>-vue-<6 hexadécimaux>` pour une vue ;
- `zone` : `[sud, ouest, nord, est]` en degrés, comme les lots ;
- `zoom` : `[min, max]`, les niveaux présents ; au-delà de `max`, on agrandit ;
- `source` : `scan25` (SCAN 25 de l'IGN, avec clé) ou `plan` (Plan IGN,
  Licence Ouverte) ;
- `octets`, `sha256`, `url` : comme un fichier de lot.

Le fichier est un [MBTiles 1.3](https://github.com/mapbox/mbtiles-spec/blob/master/1.3/spec.md) :
une base SQLite, table `tiles` en rangées TMS (comptées depuis le sud), tuiles
JPEG (`scan25`) ou PNG (`plan`) de 256 pixels en Web Mercator, et la table
`metadata` avec `name`, `format`, `type` (`baselayer`), `bounds`, `minzoom`,
`maxzoom`, `attribution`, plus `source`.

Un lecteur qui ne connaît pas `"fonds"` l'ignore : celui du PC
(`depot.lire_catalogue`) ne regarde que `format` et `lots`, et les tests le
vérifient. Une publication GitHub n'a jamais de `"fonds"`.

## 4. Sécurité

Le modèle est celui d'un outil personnel sur un réseau de confiance, durci là
où cela ne coûte rien :

- **fermé par défaut** : le partage ne s'ouvre que sur le bouton « Partager au
  téléphone » et se ferme sur « Arrêter le partage » ou à l'arrêt de hike2gpx ;
- **réseau local seulement** : le serveur écoute sur l'adresse privée du PC
  (jamais `0.0.0.0`), refuse d'ouvrir si cette adresse n'est pas privée, et
  répond 403 à un client dont l'adresse n'est pas privée ;
- **jeton** : comparé en temps constant (`secrets.compare_digest`), renouvelé
  à chaque ouverture ;
- **rien d'autre que le catalogue** : à l'ouverture, le PC dresse une table
  adresse -> fichier des lots et fonds installés ; une requête n'est servie que
  si son adresse figure dans cette table. Aucune adresse reçue ne devient un
  chemin, et `..` ne mène nulle part.

Le transport est en HTTP clair, comme tout service d'un réseau domestique sans
certificat : le jeton protège l'accès, pas la confidentialité sur un Wi-Fi
partagé. Le contenu est vérifié par le téléphone, fichier par fichier, contre
le SHA-256 du catalogue.

## 5. Côté téléphone, en résumé

1. Lire le QR code, extraire `url` et `jeton`.
2. `GET url` avec `Authorization: Bearer <jeton>` ; vérifier `format == 1`.
3. Pour chaque lot ou fond voulu, télécharger chaque fichier à
   `urljoin(url, fichier.url)`, avec le même en-tête, en reprenant par `Range`
   après une coupure ; contrôler taille et SHA-256 avant d'installer.
4. Un 401 veut dire que le partage a été fermé ou rouvert : rescanner.
