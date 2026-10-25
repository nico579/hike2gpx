# Rapport PR 36 — Mode serveur pour le bureau

## Résultat

L'application de bureau peut utiliser un serveur personnel en lecture seule pour accéder aux données préparées. Une adresse de serveur se configure dans les réglages ; le client vérifie que l'adresse répond bien comme serveur hike2gpx. Sans adresse valide ou si le serveur devient inaccessible, l'application garde son mode local.

## Fonctionnalités réalisées

- API serveur distincte des fonctions d'administration locales. Elle publie l'état, les paquets déjà préparés, leurs fichiers et le calcul de secours.
- Téléchargement des paquets de zone avec couverture, profil BRouter, fichiers RD5 et empreintes SHA-256. Les clients vérifient les fichiers avant de les conserver.
- Reprise HTTP `Range` des fichiers de paquet.
- Calcul d'itinéraire local privilégié lorsque les données sont disponibles dans le paquet. Le serveur ne calcule qu'en secours explicite.
- Cache local des paquets cloud pour permettre de recalculer une zone déjà téléchargée hors connexion.
- Refus des chemins d'administration et d'écriture depuis le client ; l'application cliente ne reçoit aucun mot de passe.
- Adresse du serveur et état de connexion accessibles dans les réglages, avec retour au mode local en cas d'indisponibilité.

## Vérifications

Les tests du contrat couvrent l'état du serveur, les paquets préparés, les limites de couverture, la reprise HTTP, l'intégrité des fichiers, la sécurité des routes et le mode hors connexion. Le test de bout en bout sur VM a également utilisé les fragments préparés par le serveur et le calcul local BRouter.

## Limites connues

La sélection et le renouvellement d'un catalogue national de zones restent à finaliser. Le calcul de secours du serveur reste nécessaire pour les cas où le client ne peut pas calculer localement.
