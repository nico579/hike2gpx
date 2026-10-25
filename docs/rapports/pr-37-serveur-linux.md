# Rapport PR 37 — Serveur Linux et mailles de données

## Résultat

Cette PR prépare le serveur Ubuntu qui fabrique à l'avance les réseaux de routage par pays et publie les données en lecture seule aux clients. Le calcul BRouter côté client reste le chemin normal ; le serveur conserve un itinéraire de secours.

## Travail réalisé

- Installation Ubuntu avec service systemd, proxy HTTPS Caddy, configuration des zones et commandes de fabrication déclenchables par SSH.
- Contrat de providers partagé entre les pays pour les fonds, les chemins et les données d'itinéraire.
- Découpage de RD5 en fragments distribuables de 0,25°, manifeste avec empreintes, publication atomique et assemblage vérifié par le client.
- Publication gzip des chemins OSM, des chemins nationaux, des barrières et des franchissements dans des mailles de 0,25°. Les calques sont filtrés sur les chemins ; le réseau routier nécessaire au routage reste dans les données RD5.
- API en lecture seule pour les calques, l'inventaire des mailles et les paquets de routage. Les fichiers de paquet acceptent la reprise HTTP `Range`.
- Client bureau en mode serveur avec cache gzip des calques dans `cloud-paquets/calques`, réutilisation hors ligne et provenance `cloud`/`local` affichée sur la carte. Le quadrillage des cellules disponibles s'active dans les réglages.
- Journaux horodatés au démarrage et lors des échanges : source des données, téléchargement direct ou cloud, durée, taille reçue et état du cache.
- Script d'inspection du contenu des calques et règles d'épuration propres au provider IGN, sans changer les données du routage.
- Le voyant « Tracé disponible » interroge le serveur pour savoir si le paquet de routage préparé couvre la zone. En dehors de cette couverture, les calques, le voyant et le calcul basculent ensemble vers les données locales : Overpass, extraits locaux et BRouter local reprennent alors leur rôle normal.

## Mesures réalisées

Sur les deux mailles voisines de Garéoult, après filtrage :

| Maille | OSM compressé | IGN compressé | Contenu OSM | Contenu IGN |
| --- | ---: | ---: | --- | --- |
| 173_24 | 823 449 octets | 1 603 709 octets | 6 788 chemins/pistes, 278 barrières, 253 franchissements | 16 971 chemins, sentiers, escaliers et routes empierrées |
| 173_25 | 867 995 octets | 1 534 541 octets | 7 335 chemins/pistes, 613 barrières, 241 franchissements | 18 910 chemins retenus |

Comparé aux calques qui incluaient les routes, les tailles ont baissé de 24 à 48 %. Le volume moyen observé, fragments RD5 compris, donne une première estimation d'environ 76 Mo pour les 25 mailles du Var et 4,9 Go pour les 1 608 mailles de France métropolitaine. Cette extrapolation ne remplace pas une mesure nationale.

Le calcul témoin OSM + BD TOPO a pris 50 et 56 secondes, avec environ 1 Gio de RAM au pic. Deux fragments totalisant 1 245 096 octets ont été assemblés en une RD5 identique à la référence ; BRouter a calculé localement un itinéraire strict de 109 m traversant la frontière des mailles.

## Vérification et limites

La suite Python complète a réussi : **276 tests**. La VM de test a été mise à jour et son service redémarré avec les derniers calques épurés. Les essais portent sur deux mailles du Var ; la couverture complète des pays, les coins de quatre mailles, les limites entre fichiers RD5 et les autres adaptateurs nationaux restent à valider.
