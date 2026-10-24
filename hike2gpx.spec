# Recette PyInstaller du programme hike2gpx, la même sur les trois systèmes.
# Ne se lance pas seule : build.py prépare l'environnement isolé et le Java
# embarqué (build/jre), puis appelle PyInstaller sur ce fichier.
#
# Mode dossier (onedir), comme les autres applications de nico579 : démarrage
# immédiat, sans extraction. Sous macOS, le dossier devient hike2gpx.app.
#
#   dist/hike2gpx/                     Windows et Linux
#     hike2gpx(.exe)                   lanceur.py
#     _internal/hike2gpx/assets/       icône, page (web/), Leaflet
#     _internal/jre/                   Java de BRouter (brouter.java())
#   dist/hike2gpx.app/                 macOS (Contents/MacOS/hike2gpx)

import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

SRC = Path(SPECPATH)
ASSETS = SRC / "hike2gpx" / "assets"
JRE = SRC / "build" / "jre"
VERSION = re.search(r'__version__ = "([^"]+)"', (SRC / "hike2gpx" / "__init__.py").read_text(encoding="utf-8"))[1]

# Sans Java, BRouter ne tourne pas : pas de programme à moitié construit.
if not (JRE / "bin" / ("java.exe" if sys.platform == "win32" else "java")).is_file():
    raise SystemExit(f"Java embarqué absent de {JRE} : lancer python build.py, qui le télécharge.")

# La page et l'icône sont lues à côté des modules (Path(__file__).parent), aux
# mêmes chemins relatifs qu'en sources. PyInstaller ne les voit pas seul : ce
# ne sont pas des imports.
datas = [(str(f), "hike2gpx/assets") for f in (ASSETS / "hike2gpx.ico", ASSETS / "hike2gpx.png")]
datas += [(str(f), "hike2gpx/assets/web") for f in sorted((ASSETS / "web").glob("*"))
          if f.suffix in (".html", ".js", ".css")]
datas += [(str(f), "hike2gpx/assets/web/leaflet") for f in sorted((ASSETS / "web" / "leaflet").glob("*"))]
# Fonds et calques par pays, concaténés par web.py en /map-providers.js : sans
# eux, même la France perd ses fonds IGN.
datas += [(str(f), "hike2gpx/assets/web/providers") for f in sorted((ASSETS / "web" / "providers").glob("*.js"))]
datas += [(str(SRC / "LICENSE"), ".")]
# Le JRE Temurin tel que build.py l'a posé (sous macOS, son seul Contents/Home :
# le bundle complet serait pris par codesign --deep pour un bundle imbriqué,
# leçon de lidar2map). Sous macOS, PyInstaller range ses fichiers Mach-O dans
# Contents/Frameworks et le reste dans Contents/Resources, reliés par des
# liens : vu de sys._MEIPASS, l'arborescence reste jre/bin, jre/lib...
datas += [(str(JRE), "jre")]
# Données lues à l'import : bandeau et réglages du commun, version et
# traductions de gpx2elev (assets/version.txt dès « import gpx2elev »), base
# proj.db et données GDAL de rasterio.
datas += collect_data_files("nico579_commons") + collect_data_files("gpx2elev") + collect_data_files("rasterio")

# Imports que l'analyse statique ne voit pas : modules compilés de pyosmium et
# de rasterio chargés depuis leur code C, icône du commun par StatusNotifierItem
# sous Linux, moteur de pystray propre au système (comme gpx2elev).
hiddenimports = (collect_submodules("osmium") + collect_submodules("rasterio")
                 + collect_submodules("nico579_commons") + collect_submodules("mapbox_vector_tile"))
hiddenimports += ["pystray." + {"win32": "_win32", "darwin": "_darwin"}.get(sys.platform, "_xorg")]


# Ressource VERSIONINFO de l'exécutable Windows (sans effet ailleurs) : un
# programme PyInstaller sans éditeur ni description ressemble, pour les
# antivirus à heuristique, aux échantillons malveillants (constaté sur
# blink2video). Même contenu que watch2notif, régénéré à chaque construction.
def version_info(version: str) -> str:
    nombres = tuple(int(p) for p in (version.split(".") + ["0", "0", "0"])[:3]) + (0,)
    chemin = SRC / ".version_info.txt"
    chemin.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nombres}, prodvers={nombres}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable(u'040904B0', [
      StringStruct(u'CompanyName', u'nico579'),
      StringStruct(u'FileDescription', u'hike2gpx - tracé de randonnée qui respecte les clôtures'),
      StringStruct(u'FileVersion', u'{version}'),
      StringStruct(u'InternalName', u'hike2gpx'),
      StringStruct(u'LegalCopyright', u'GPLv3 - nico579'),
      StringStruct(u'OriginalFilename', u'hike2gpx.exe'),
      StringStruct(u'ProductName', u'hike2gpx'),
      StringStruct(u'ProductVersion', u'{version}')])]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
""", encoding="utf-8")
    return str(chemin)


analysis = Analysis(
    [str(SRC / "lanceur.py")],
    pathex=[str(SRC)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "PyInstaller", "pytest"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="hike2gpx",
    debug=False,
    strip=False,
    upx=False,
    # Pas de console : la page s'ouvre dans le navigateur, l'icône de la zone
    # de notification et hike2gpx.log sont les seuls autres retours.
    console=False,
    # target_arch=None : l'architecture du Python de construction (arm64 ou
    # x86_64 sous macOS), jamais une valeur en dur.
    target_arch=None,
    icon=str(ASSETS / ("hike2gpx.ico" if sys.platform == "win32" else "hike2gpx.png")),
    version=version_info(VERSION),
)
coll = COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False, name="hike2gpx")

if sys.platform == "darwin":
    BUNDLE(
        coll,
        name="hike2gpx.app",
        icon=str(ASSETS / "hike2gpx.png"),
        bundle_identifier="com.nico.hike2gpx",
        version=VERSION,
        info_plist={"NSHighResolutionCapable": True, "CFBundleDisplayName": "hike2gpx"},
    )
