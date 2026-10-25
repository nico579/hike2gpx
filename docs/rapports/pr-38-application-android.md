# Rapport PR 38 — Application Android

## Résultat

Le dépôt contient un client Android natif capable de télécharger une zone préparée, de calculer avec BRouter embarqué et de conserver les données pour un usage hors connexion.

## Travail réalisé

- Projet Gradle autonome, icône hike2gpx, interface localisée en français et en anglais, carte interactive et saisie de coordonnées.
- BRouter 1.7.10 intégré comme sous-module Git et calcul exécuté localement sur le téléphone.
- Téléchargement des paquets serveur anonymes en lecture seule, avec contrôle des tailles et SHA-256.
- Prise en charge des paquets complets format 1 et des fragments RD5 de 0,25° format 2. L'assembleur reconstruit la RD5 dans le stockage privé de l'application et vérifie la couverture avant le calcul.
- Stockage des zones téléchargées et réouverture hors connexion après redémarrage.
- Affichage séparé des chemins officiels et des franchissements connus. Le calcul applique les coupes finales du manifeste et contrôle le résultat contre les franchissements et les limites de couverture.
- Bouton de secours explicite pour demander un calcul serveur si le téléphone ne termine pas le calcul local.
- Export de l'itinéraire au format GPX.

## Vérifications réalisées

- La compilation `:app:assembleDebug` a réussi avec le sous-module BRouter 1.7.10.
- Le client de référence a téléchargé les deux fragments de la VM (1 245 096 octets), reconstruit une RD5 de 1 248 993 octets identique à la référence et calculé localement un itinéraire strict de 109 m qui traverse une limite de maille.
- Le parcours de téléchargement contrôle les empreintes avant publication atomique ; les anciens paquets complets restent lisibles.

## À valider

Un essai sur téléphone ou émulateur reste à faire : téléchargement interrompu puis repris, calcul hors ligne après redémarrage, consommation mémoire et affichage autour des barrières et franchissements.
