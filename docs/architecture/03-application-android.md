# PR 3 — Application Android avec calcul local

## Objectif

Créer une application Android qui lit les données préparées par le serveur Linux, conserve des zones sur le téléphone et calcule les itinéraires avec BRouter sur l'appareil. Une zone déjà téléchargée doit rester utilisable hors ligne. Le serveur ne calcule qu'en secours si le moteur embarqué est indisponible ou si la mémoire de l'appareil est insuffisante.

## Contrat avec le serveur

L'application demande un manifeste via `GET /api/paquet-zone`, puis télécharge les RD5 enrichis, `lookups.dat` et `hike2gpx.brf`. Elle vérifie taille et SHA-256 avant de rendre la zone active. Le manifeste contient les `polylines` BRouter définitives pour le mode strict choisi et les franchissements nécessaires à l'affichage et au contrôle final. Il n'y a ni compte ni mot de passe. L'utilisateur choisit l'adresse HTTPS et les zones à conserver.

## Calcul embarqué

- Intégrer les bibliothèques Java de BRouter dans le processus Android, avec un adaptateur Java autour de `RoutingEngine` et des fichiers de la zone dans le stockage privé de l'application. L'accès à l'installation Android distincte de BRouter ne suffit pas, car elle ne connaît pas les RD5 enrichis de hike2gpx.
- Lancer le calcul sur un fil de fond annulable. Transmettre les points, le profil et les coupes finales du manifeste à BRouter ; convertir le résultat en tracé et statistiques.
- Vérifier après calcul que le tracé reste dans la couverture du paquet et ne traverse aucun franchissement interdit. Afficher les franchissements et les portions officielles sur la carte.
- Si les fichiers sont absents, incomplets ou périmés, proposer le téléchargement. Si le moteur local échoue pour une limite de ressources, tenter le calcul de secours du serveur lorsque le réseau répond.

## Étapes de code

1. Créer le projet Android, les écrans carte, recherche, parcours, réglages et choix des zones.
2. Implémenter le client HTTPS, les téléchargements reprenables, la vérification SHA-256 et le catalogue de zones conservées.
3. Intégrer BRouter dans l'application et brancher le profil, les RD5 et les coupes finales ; ajouter les contrôles de sortie et les erreurs claires.
4. Ajouter l'export GPX, le mode hors ligne, le changement FR/EN et le calcul de secours distant.
5. Valider sur émulateur et appareil avec une zone officielle, une coupure réseau, un paquet corrompu et un franchissement bloquant.

## Critères de validation

Après téléchargement d'une zone, le mode avion permet d'afficher cette zone et de calculer un itinéraire avec les mêmes interdictions de franchissement. Le serveur distribue les données et ne reçoit pas de demande de calcul en fonctionnement normal. L'application signale explicitement les cas qui demandent encore un téléchargement ou un secours distant.
