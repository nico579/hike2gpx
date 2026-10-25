#!/usr/bin/env bash
# Ubuntu 24.04 AMD64 : installation du service de données depuis un checkout.
set -euo pipefail

if [[ $EUID -ne 0 || $# -ne 1 ]]; then
  echo "Usage: sudo bash deploy/linux/install.sh rando.example.org" >&2
  exit 2
fi

domain=$1
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
if [[ ! $domain =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}$ ]] \
    || [[ $domain == *..* ]] || [[ $domain == *--* ]]; then
  echo "Nom DNS invalide (sans https:// ni port)." >&2
  exit 2
fi
if [[ $(. /etc/os-release; echo "$ID:$VERSION_ID") != ubuntu:24.04 ]]; then
  echo "Installateur vérifié uniquement pour Ubuntu 24.04 LTS." >&2
  exit 2
fi
if [[ $(uname -m) != x86_64 ]]; then
  echo "Installateur vérifié uniquement sur x86_64." >&2
  exit 2
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl gnupg git python3.12 python3.12-venv \
  openjdk-21-jre-headless debian-keyring debian-archive-keyring apt-transport-https

if ! command -v caddy >/dev/null; then
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
    -o /etc/apt/sources.list.d/caddy-stable.list
  chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
    /etc/apt/sources.list.d/caddy-stable.list
  apt-get update
  apt-get install -y caddy
fi

if ! id -u hike2gpx >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/hike2gpx --shell /usr/sbin/nologin hike2gpx
fi
install -d -o hike2gpx -g hike2gpx -m 0750 /var/lib/hike2gpx
install -d -m 0755 /opt/hike2gpx
if [[ ! -x /opt/hike2gpx/venv/bin/python ]]; then
  python3.12 -m venv /opt/hike2gpx/venv
fi
/opt/hike2gpx/venv/bin/python -m pip install --upgrade pip
/opt/hike2gpx/venv/bin/python -m pip install --upgrade "$repo_dir"
install -m 0755 "$repo_dir/deploy/linux/refresh.py" /opt/hike2gpx/refresh.py
install -m 0755 "$repo_dir/deploy/linux/france_osm.py" /opt/hike2gpx/france_osm.py
install -d -m 0755 /etc/hike2gpx
if [[ ! -f /etc/hike2gpx/zones.json ]]; then
  install -m 0644 "$repo_dir/deploy/linux/zones.example.json" /etc/hike2gpx/zones.json
fi
install -m 0644 "$repo_dir/deploy/linux/hike2gpx-refresh.service" /etc/systemd/system/hike2gpx-refresh.service
install -m 0644 "$repo_dir/deploy/linux/hike2gpx-refresh.timer" /etc/systemd/system/hike2gpx-refresh.timer

export H2G_DOMAIN=$domain
export H2G_DEPLOY_DIR=$repo_dir/deploy/linux
python3.12 - <<'PY'
import os
from pathlib import Path

templates = Path(os.environ["H2G_DEPLOY_DIR"])
values = {"@DOMAIN@": os.environ["H2G_DOMAIN"]}
for source, target in (("hike2gpx.service.in", "/etc/systemd/system/hike2gpx.service"),
                       ("Caddyfile.in", "/etc/caddy/Caddyfile")):
    body = (templates / source).read_text(encoding="utf-8")
    for old, new in values.items():
        body = body.replace(old, new)
    path = Path(target)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o644)
PY

caddy validate --config /etc/caddy/Caddyfile
systemctl daemon-reload
systemctl enable hike2gpx
systemctl restart hike2gpx
systemctl enable --now hike2gpx-refresh.timer
systemctl enable --now caddy
systemctl reload caddy
systemctl is-active --quiet hike2gpx
systemctl is-active --quiet caddy
echo "Installé : https://$domain/api/etat"
echo "Vérifier DNS et l'ouverture des ports 80/443 si le certificat n'est pas encore délivré."
