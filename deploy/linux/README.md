# Serveur Linux

Pré-requis : Ubuntu 24.04 x86_64, nom DNS public pointant vers le serveur, ports 80 et 443 ouverts, accès SSH pour l'administration. L'API de lecture ne demande aucun mot de passe. La gestion reste exclusivement sur le serveur via SSH et systemd.

```bash
git clone https://github.com/nico579/hike2gpx.git
cd hike2gpx
git switch feat/linux-server-deploy
sudo bash deploy/linux/install.sh rando.example.org
curl https://rando.example.org/api/etat
```

L'installation crée l'utilisateur `hike2gpx`, l'environnement Python sous `/opt/hike2gpx`, les données sous `/var/lib/hike2gpx`, le service HTTP et un timer journalier. Caddy obtient le certificat HTTPS et ne publie que `GET /api/*` ainsi que `POST /api/itineraire` pour le secours. Les routes d'administration, fichiers et pages locales ne sont pas exposés.

Adapter `/etc/hike2gpx/zones.json` : chaque zone a un `id`, un `pays` du registre des providers, une `source` officielle, quatre bornes `[sud, ouest, nord, est]`, `renouvellement_jours` et `modes` (`strict`, `souple`). Garder les zones assez petites pour les limites de tuiles et de mémoire ; découper un pays en plusieurs zones. Le timer vérifie les échéances chaque jour. Sa cadence par zone vaut au minimum le délai configuré et dix fois la durée du dernier calcul.

```bash
# Depuis le PC, déclencher un seul calcul distant par SSH.
ssh nico@rando.example.org 'sudo -u hike2gpx env HIKE2GPX_HOME=/var/lib/hike2gpx PATH=/opt/hike2gpx/venv/bin:/usr/bin:/bin /opt/hike2gpx/venv/bin/python /opt/hike2gpx/refresh.py --zone de-rosa --all'

# Ou, sur le serveur, déclencher toutes les zones arrivées à échéance.
sudo systemctl start hike2gpx-refresh.service
sudo journalctl -u hike2gpx-refresh.service -n 100
sudo cat /var/lib/hike2gpx/refresh.json
```

Le planificateur prend un verrou exclusif, prépare les zones l'une après l'autre et n'avance la prochaine échéance qu'après succès. Un échec garde le dernier paquet publié et sera retenté au prochain passage. Les durées sont consignées dans `refresh.json` et dans le journal systemd. Le stockage des anciens paquets doit être surveillé tant que la politique de rétention n'est pas en place.

## Essai dans la VM VirtualBox locale

La VM disponible est Ubuntu 26.04.1, avec Python 3.14 par défaut, alors que l'installateur ci-dessus cible Ubuntu 24.04 et Python 3.12. Le serveur applicatif y a été installé avec un Python 3.12 géré dans le répertoire utilisateur, sans modifier le système. Pour répéter l'essai : démarrer `serve --mode-serveur --nom-hote rando.example.org` sur le port 8795, puis lancer `python3 deploy/linux/vm_smoke.py` dans la VM. Le script vérifie l'état, l'absence de paquet non préparé et le refus des routes de gestion. L'option `--prepared` vérifie un paquet OSM déjà calculé et le téléchargement partiel de sa RD5 ; `--route` ajoute le calcul distant de secours.

Sur une zone française de 0,05° préparée dans un dossier vierge, la VM a produit une RD5 de 69 Mo et 34 franchissements. Le dossier complet occupe 80 Mo et n'a pas lancé d'import régional Geofabrik. Ce résultat valide le mécanisme par zone ; il ne mesure pas encore les durées ni la place nécessaires pour toutes les zones nationales.

Le même paquet a été relu par l'API : manifeste, réponse HTTP `206` sur une plage de la RD5 et calcul de secours de 419 m avec BRouter local au serveur. Ce calcul n'a utilisé que le paquet déjà préparé.

Avec accès sudo sur cette VM Ubuntu 26.04, Caddy 2.6.2 a été installé et la configuration de filtrage a été validée. Une instance HTTP locale de Caddy a relayé les mêmes contrôles (`vm_smoke.py --prepared --route`) vers un service `hike2gpx-vmtest` lancé par systemd : paquet réel, réponse HTTP `206`, 34 franchissements et calcul de secours de 419 m. Le service de test utilise les répertoires et l'utilisateur de la VM ; il n'exerce donc pas l'isolation `ProtectHome` du modèle de production. L'installateur refuse correctement Ubuntu 26.04. La VM n'a ni nom DNS public ni certificat HTTPS ; l'installation complète et TLS restent à valider sur Ubuntu 24.04.
