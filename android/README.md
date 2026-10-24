# Application Android

Cette PR ajoute un client natif Android. BRouter 1.7.10 est épinglé comme sous-module Git et compilé directement dans l'APK : les RD5 enrichis restent dans le stockage privé de l'application. Le calcul local reçoit les coupes finales du manifeste, puis vérifie le tracé contre les franchissements interdits.

```bash
git submodule update --init android/brouter
```

Ouvrir `android/` dans Android Studio et construire `:app:assembleDebug`. Sous Windows, `powershell -File android/build-local.ps1` utilise le JDK et le SDK d'Android Studio. L'APK de développement est généré sous `android/app/build/outputs/apk/debug/`.

Dans l'application : saisir l'adresse HTTPS du serveur, sélectionner le provider, saisir l'emprise `[sud, ouest, nord, est]`, puis télécharger la zone. Les fichiers et le manifeste sont vérifiés par taille et SHA-256. Choisir ensuite deux points dans la couverture et lancer le calcul. Après téléchargement, le calcul et l'export GPX fonctionnent sans connexion. L'affichage hors ligne montre le tracé sur un aperçu simplifié ; le fond cartographique et la sélection tactile des points restent à intégrer.

Le serveur ne reçoit aucune requête de calcul pendant le parcours normal. Le bouton de secours distant est explicite et demande le calcul au serveur si le téléphone ne peut pas le terminer. L'interface cartographique complète et les essais sur appareil restent des étapes ouvertes de cette PR.
