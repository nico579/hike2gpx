#!/usr/bin/env python3
"""Compte les mailles de 0,25° touchant un contour national ou départemental."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from shapely.geometry import Polygon, box
from shapely.ops import unary_union


def compter(index: Path, identifiant: str) -> tuple[int, int]:
    regions = json.loads(index.read_text(encoding="utf-8"))["regions"]
    region = next(r for r in regions if r["id"] == identifiant)
    contour = unary_union([Polygon(anneaux[0], anneaux[1:]) for anneaux in region["polygones"]])
    sud, ouest, nord, est = region["bornes"]
    candidates, touchees = 0, 0
    for i in range(math.floor(sud * 4), math.ceil(nord * 4)):
        for j in range(math.floor(ouest * 4), math.ceil(est * 4)):
            candidates += 1
            if contour.intersects(box(j / 4, i / 4, (j + 1) / 4, (i + 1) / 4)):
                touchees += 1
    return touchees, candidates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path)
    parser.add_argument("identifiant")
    args = parser.parse_args()
    touchees, candidates = compter(args.index, args.identifiant)
    print(f"{args.identifiant} : {touchees} mailles touchées sur {candidates} dans le rectangle")


if __name__ == "__main__":
    main()
