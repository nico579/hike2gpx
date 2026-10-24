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
ssh nico@rando.example.org 'sudo -u hike2gpx env HIKE2GPX_HOME=/var/lib/hike2gpx PATH=/opt/hike2gpx/venv/bin:/usr/bin:/bin /opt/hike2gpx/venv/bin/python /opt/hike2gpx/refresh.py --zone de-dresde --all'

# Ou, sur le serveur, déclencher toutes les zones arrivées à échéance.
sudo systemctl start hike2gpx-refresh.service
sudo journalctl -u hike2gpx-refresh.service -n 100
sudo cat /var/lib/hike2gpx/refresh.json
```

Le planificateur prend un verrou exclusif, prépare les zones l'une après l'autre et n'avance la prochaine échéance qu'après succès. Un échec garde le dernier paquet publié et sera retenté au prochain passage. Les durées sont consignées dans `refresh.json` et dans le journal systemd. Le stockage des anciens paquets doit être surveillé tant que la politique de rétention n'est pas en place.
