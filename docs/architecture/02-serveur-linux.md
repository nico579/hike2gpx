# PR 2 — Serveur Linux de données

## Objectif

Installer sur un Linux vierge le service qui prépare les données par pays et par zone, puis les distribue aux applications. Le serveur produit les RD5 enrichis et les coupes de franchissements finales. Les calculs coûteux sont lancés par SSH depuis un PC, puis par une tâche programmée selon leur durée mesurée. L'API publique ne donne aucun contrôle d'administration.

## Architecture

- Ubuntu 24.04, utilisateur de service dédié, répertoire de données persistant, Python, Java pour la préparation BRouter, Caddy pour HTTPS et systemd pour le service.
- Caddy expose les routes de lecture `GET /api/etat`, `GET /api/paquet-zone`, `GET /api/paquets/*` et les calques nécessaires. Le calcul de secours `POST /api/itineraire` est borné séparément ; aucun mot de passe n'est requis pour lire les données.
- Les sources officielles et leurs zones de validité proviennent du registre `providers`. Une configuration de zones associe pays, fournisseur, emprise, variantes stricte et non stricte, et cadence.
- `hike2gpx preparer-zone ...` est la même commande pour un appel SSH ponctuel et pour systemd. Elle écrit un nouveau paquet complet avant de le rendre visible ; les clients peuvent continuer à lire l'ancien durant le calcul.
- Le planificateur évite les calculs concurrents et journalise durée, succès, taille, date et prochaine échéance. Sa fréquence initiale est configurable, puis s'ajuste à la durée des calculs observée.

## Étapes de code

1. Ajouter un programme d'installation idempotent et des unités systemd pour le service et la préparation.
2. Ajouter la configuration des zones et une commande de préparation séquentielle utilisable via SSH.
3. Ajouter le journal d'exécution, les durées et la planification automatique ; éviter de republier un paquet incomplet.
4. Vérifier le proxy HTTPS, le téléchargement partiel `Range` et l'exclusion des routes de gestion.
5. Documenter les commandes d'installation, de calcul distant, de consultation des journaux et de modification de cadence.

## Critères de validation

Une machine neuve peut être installée à partir du dépôt, puis produire et servir une zone sans interface graphique. Un téléphone récupère uniquement des données préparées. La coupure ou l'échec d'un calcul conserve le dernier paquet valide. Le calcul BRouter serveur n'est utilisé qu'en secours.
