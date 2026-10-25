# Application Android

Cette PR ajoute un client natif Android. BRouter 1.7.10 est épinglé comme sous-module Git et compilé directement dans l'APK : les RD5 enrichis restent dans le stockage privé de l'application. Le calcul local reçoit les coupes finales du manifeste, puis vérifie le tracé contre les franchissements interdits.

```bash
git submodule update --init android/brouter
```

Ouvrir `android/` dans Android Studio et construire `:app:assembleDebug`. Sous Windows, `powershell -File android/build-local.ps1` utilise le JDK et le SDK d'Android Studio. Le wrapper Gradle se trouve à la racine du projet Android. L'APK de développement est généré sous `android/app/build/outputs/apk/debug/`.

Dans l'application : saisir l'adresse HTTPS du serveur, sélectionner le provider, cadrer la carte puis toucher « Utiliser la zone visible », ou saisir l'emprise `[sud, ouest, nord, est]`, puis télécharger la zone. Les fichiers et le manifeste sont vérifiés par taille et SHA-256. « Zones téléchargées » permet de rouvrir une zone après redémarrage, hors ligne. Deux touches sur la carte définissent le départ et l'arrivée. Après téléchargement, le calcul et l'export GPX fonctionnent sans connexion. Les tuiles de fond OSM déjà affichées peuvent rester en cache, sans téléchargement massif anticipé.

Le serveur ne reçoit aucune requête de calcul pendant le parcours normal. Le bouton de secours distant est explicite et demande le calcul au serveur si le téléphone ne peut pas le terminer. Les chemins officiels téléchargés s'affichent en violet, et les franchissements connus du paquet en rouge (bloquants) ou orange (à vérifier), indépendamment du tracé. Les essais sur appareil restent une étape ouverte de cette PR.

Essai du moteur local avec une tuile déjà installée sur le PC (aucun accès réseau) :

```text
python android/smoke/run.py CHEMIN_VERS_DONNEES/brouter CHEMIN_VERS_JDK
```

Le test prépare un dossier temporaire, appelle le même `LocalRouter` que l'APK et exige un tracé GeoJSON réel.

Le format 2 télécharge les fragments RD5 de 0,25° du paquet choisi, vérifie
leurs SHA-256 et reconstruit atomiquement la RD5 locale. Les anciens paquets
complets du format 1 restent lisibles. Le calcul vérifie que le tracé reste
dans la couverture annoncée par le paquet, avec une marge de 0,002°. Sur la
VM, deux fragments ont été téléchargés et assemblés octet pour octet avant
un itinéraire local de 109 m. L'essai sur appareil Android, notamment en cas
de coupure pendant le téléchargement, reste à faire. La conception et les
mesures figurent dans [Mailles calculées et téléchargées](../docs/architecture/05-mailles-telechargeables.md).
