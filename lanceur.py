"""Point d'entrée du programme figé : PyInstaller lance un script, pas le
__main__ d'un paquet, dont les imports relatifs échoueraient. Se lance aussi
avec Python, comme celui de gpx2elev."""
from hike2gpx.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
