"""Point d'entrée du programme figé : PyInstaller lance un script, pas le
__main__ d'un paquet, dont les imports relatifs échoueraient. Se lance aussi
avec Python, comme celui de gpx2elev."""
import multiprocessing

from hike2gpx.__main__ import main

if __name__ == "__main__":
    # Les calques d'un lot se lisent dans des processus fils lancés par spawn
    # (fabrication._calques) : figé, le programme se relance pour chacun, et
    # freeze_support() en fait un fils au lieu d'une nouvelle application.
    multiprocessing.freeze_support()
    raise SystemExit(main())
