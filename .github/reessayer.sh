#!/usr/bin/env bash
# Relance une étape après une panne passagère : Geofabrik saturé (502, 503,
# délai dépassé), coupure réseau, service d'artefacts de GitHub muet. Le
# 2026-11-11, une seule panne de ce genre faisait perdre une case entière.
# hike2gpx reprend là où il s'était arrêté : les extraits Geofabrik et les
# archives des fournisseurs déjà installés sont gardés, un nouveau passage ne
# fait que ce qui manque.
#
# Usage : bash .github/reessayer.sh PASSAGES COMMANDE [ARGUMENTS...]
# PAUSE_S (300 par défaut) : l'attente entre deux passages.
set -u
passages=$1
shift
statut=1
for passage in $(seq 1 "$passages"); do
  "$@" && exit 0
  statut=$?
  if [ "$passage" -lt "$passages" ]; then
    echo "::warning::passage $passage sur $passages échoué (code $statut), reprise dans ${PAUSE_S:-300} s"
    sleep "${PAUSE_S:-300}"
  fi
done
exit "$statut"
