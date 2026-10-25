# PR 1 — Mode serveur et client actuel

## Objectif

Conserver le fonctionnement local de l'application actuelle. Ajouter dans les réglages une adresse HTTPS de serveur de données. Si le serveur répond, utiliser ses calques et ses paquets de zone ; sinon, continuer avec les données et le moteur locaux. Le calcul d'itinéraire reste sur l'appareil dès que les données nécessaires y sont présentes.

## Contrat du paquet de zone

- `GET /api/etat` annonce `mode_serveur: true`.
- `GET /api/paquet-zone?s=&w=&n=&e=&source=&officiel=&strict=` lit un paquet déjà calculé couvrant toute la zone. Une zone absente répond `pret: false`, sans lancer de génération.
- Le manifeste contient la couverture, la source, la variante stricte, les fichiers `.rd5`, `lookups.dat`, `hike2gpx.brf`, leurs tailles et SHA-256, ainsi que les coupes BRouter `polylines` déjà finales. Pour une source nationale, `chemins-officiels.json` fournit aussi la géométrie du calque hors ligne. Les franchissements restent listés pour l'affichage et le contrôle du tracé.
- `GET /api/paquets/<id>/<fichier>` livre les fichiers avec reprise HTTP `Range`.
- `POST /api/itineraire` peut servir de secours lorsque l'appareil ne peut pas calculer, sans être la voie principale.

## Étapes de code

1. Isoler les routes exposées en mode serveur ; exclure les réglages, les mises à jour, les journaux et les commandes de cache.
2. Préparer les paquets côté serveur avec le même moteur de fusion national et OSM que l'application locale.
3. Ajouter le client HTTPS, la vérification des empreintes, le cache de paquets et l'état cloud/local dans les réglages.
4. Brancher le calcul local sur le paquet téléchargé, y compris le contrôle final des franchissements ; garder le calcul local existant en repli.
5. Tester le contrat HTTP, les refus de routes d'administration, la couverture, les coupes, l'intégrité et le repli hors connexion.

## Critères de validation

La carte et le calcul fonctionnent sans adresse configurée. Avec un serveur disponible, les paquets préparés arrivent sans mot de passe et le calcul ne sollicite pas le BRouter du serveur. Après téléchargement d'une zone, le calcul de cette zone reste possible sans réseau. Le serveur ne reçoit aucune commande de gestion depuis les clients.
