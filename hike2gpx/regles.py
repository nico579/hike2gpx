"""Règles de passage d'une barrière OpenStreetMap : bloquante, à vérifier ou
franchissable, pour un mode de déplacement.

Copie conforme de access(), status() et de leurs constantes, prise dans
gpx2elev (desktop/gpx2elev/obstacles.py, dépôt nico579/gpx2elev, version
0.6.3, PR 10). Les deux applications doivent juger une barrière de la même façon :
une correction se fait d'abord dans gpx2elev, puis se recopie ici telle
quelle. Ce que hike2gpx ajoute pour le calcul d'itinéraire (sentiers balisés,
niveaux, poids) est dans franchissements.py, jamais dans ce fichier.
"""

SOLID = {"fence", "wall", "city_wall", "hedge", "retaining_wall", "jersey_barrier"}
PASSAGES = {"gate", "lift_gate", "swing_gate", "kissing_gate", "stile", "entrance", "gap", "cycle_barrier"}
LABELS = {"fence": "Clôture", "wall": "Mur", "hedge": "Haie", "gate": "Portail",
          "lift_gate": "Barrière levante", "swing_gate": "Barrière pivotante", "stile": "Échalier",
          "kissing_gate": "Portillon", "bollard": "Borne", "cycle_barrier": "Chicane",
          "block": "Bloc", "chain": "Chaîne", "entrance": "Passage", "gap": "Ouverture"}


# Access keys from the most specific to the most general, for each mode.
ACCESS_KEYS = {"foot": ("foot", "access"), "bicycle": ("bicycle", "vehicle", "access"),
               "motor_vehicle": ("motor_vehicle", "vehicle", "access")}


def access(tags, mode, direction=None):
    for key in ACCESS_KEYS[mode]:
        if direction and f"{key}:{direction}" in tags:
            return tags[f"{key}:{direction}"]
        if key in tags:
            return tags[key]
    return None


def status(tags, mode, direction=None, parent=None):
    """Return blocked / uncertain / passable and a reason, never infer a gate is shut."""
    kind = tags.get("barrier", "entrance" if "entrance" in tags else "yes")
    if tags.get("entrance") == "no":
        return "blocked", "Entrée condamnée"
    if kind in ("no", "kerb", "flush", "lowered"):
        return "passable", "Passage autorisé"
    keys = ACCESS_KEYS[mode]
    combined = {**(parent or {}), **tags}
    # The obstacle's own access rules take precedence; the way supplies missing ones.
    source = tags if access(tags, mode, direction) is not None else (parent or {})
    value = access(source, mode, direction)
    rank = next((r for r, key in enumerate(keys) if direction and f"{key}:{direction}" in source or key in source),
                len(keys))
    conditions = [keys.index(k.split(":")[0]) for k in combined if k.split(":")[0] in keys and "conditional" in k]
    conditional_direction = {f"oneway:{mode}:conditional"} | ({"oneway:conditional", "oneway:vehicle:conditional"} if mode != "foot" else set())
    if value in ("no", "private", "use_sidepath"):
        # An explicit prohibition only yields to a condition on a key at least as specific as the one
        # that sets it: opening hours or a general access:conditional never lift foot=no.
        doubtful = any(r <= rank for r in conditions)
    else:
        doubtful = bool(conditions) or any(k in combined for k in conditional_direction) or bool(combined.get("opening_hours"))
    if doubtful:
        return "uncertain", "Accès soumis à des conditions ou horaires"
    directional = any(k.endswith((":forward", ":backward")) and k.split(":")[0] in keys for k in combined)
    oneway = (parent or {}).get(f"oneway:{mode}", (parent or {}).get("oneway") if mode != "foot" else None)
    if direction is None and (directional or oneway in ("yes", "1", "true", "-1")):
        return "uncertain", "Sens de la voie OSM indéterminé"
    if oneway in ("yes", "1", "true") and direction == "backward" or oneway == "-1" and direction == "forward":
        return "blocked", "Passage interdit dans ce sens"
    if value in ("no", "private", "use_sidepath"):
        return "blocked", "Accès interdit ou privé"
    if tags.get("entrance") in ("exit", "entrance", "emergency"):
        return "uncertain", "Entrée à usage ou sens limité"
    if tags.get("locked") == "yes":
        if mode != "motor_vehicle" and value in ("yes", "designated", "permissive"):
            return "uncertain", "Portail verrouillé, passage autorisé à confirmer"
        return "blocked", "Barrière verrouillée"
    if value in ("yes", "designated", "permissive", "official"):
        return "passable", "Passage autorisé"
    if value is not None:
        return "uncertain", "Accès limité ou à confirmer"
    if kind in ("entrance", "gap"):
        if "entrance" in tags and "barrier" not in tags:
            return "uncertain", "Ouverture cartographiée, accès à confirmer"
        return "passable", "Ouverture cartographiée"
    if kind in SOLID:
        return "blocked", "Obstacle linéaire traversé sans ouverture cartographiée"
    if mode == "motor_vehicle" and kind in {"bollard", "block", "stile", "kissing_gate", "cycle_barrier", "bus_trap", "sump_buster"}:
        return "blocked", "Obstacle physique pour ce mode de déplacement"
    if mode == "foot" and kind in {"bollard", "cycle_barrier", "stile", "kissing_gate", "cattle_grid"}:
        return "passable", "Passage piéton possible"
    return "uncertain", "Franchissement à vérifier sur place"
