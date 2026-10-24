"""Vérifie l'API d'une instance Linux locale avant de la publier par Caddy.

python vm_smoke.py [nom-dns] [port]
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

host = sys.argv[1] if len(sys.argv) > 1 else "rando.example.org"
port = int(sys.argv[2]) if len(sys.argv) > 2 else 8795
base = f"http://127.0.0.1:{port}/api/"


def demander(route, *, data=None):
    request = urllib.request.Request(base + route, data=data,
                                     headers={"Host": host, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, None


status, health = demander("etat")
assert status == 200 and health["app"] == "hike2gpx" and health["mode_serveur"] is True
assert "dossier" not in health
assert demander("reglages")[0] == 404
assert demander("donnees", data=b"{}")[0] == 404
query = urllib.parse.urlencode({"s": 43.30, "w": 6.00, "n": 43.35, "e": 6.05,
                                "source": "ign", "strict": 1, "officiel": 1})
status, package = demander("paquet-zone?" + query)
assert status == 200 and package["raison"] == "zone_non_preparee"
print("API Linux locale OK : santé, paquet absent, administration inaccessible")
