***English** | [Français](README.fr.md)*

# hike2gpx

hike2gpx plans a hiking route, anywhere in the world, without crossing the
fences, barriers and prohibitions that OpenStreetMap describes. It works out
the elevation gain and the walking time, then exports the route as GPX. In
France, it can also use the paths that only IGN (the French national mapping
agency) knows about.

Common planners such as Visorando, Locus Map or brouter-web do not see a fence
drawn as a line across a footpath. This is not an oversight on their part:
their routing engines only read the tags on the nodes of the path, and a fence
is a separate line. hike2gpx examines the network of the area beforehand,
finds every crossing between a path and a barrier, judges it, then forbids or
discourages the passage. In Garéoult (Var, France), BRouter's standard hiking
profile goes through a concrete fence on a 69 m stretch; hike2gpx goes around
it with a 435 m detour.

For desktop computers: Windows, macOS and Linux. Phones will come later,
through the BRouter app for Android.

Installed from a release, hike2gpx updates itself, like the other nico579
applications: when a newer version is published, a banner on the page and the
menu of its tray icon offer to install it; it downloads it, checks it, then
restarts on it. The "Check for updates" button in the Settings panel asks
right away, without waiting for the periodic check. Run from source,
hike2gpx simply opens the page of the new version.

## What hike2gpx does

Everything happens in a local page, opened in the browser, and in the menu of
a tray icon.

**The map.** It follows the country at its center, including when you move it
by hand, and offers that country's base maps; each country remembers the last
base map you chose.

- **Everywhere**: OpenStreetMap, OSM hiking (OpenTopoMap), and a satellite
  view (Esri). A layer you can tick, from zoom 14,
  shows OpenStreetMap's paths (footpaths dashed), with the fences and walls it
  maps.
- **In France**: IGN's base maps, SCAN 25 (with an IGN key, see below), IGN
  Plan, aerial photos, and the LiDAR HD relief wherever IGN has published it.
  A second layer shows the paths of IGN's BD TOPO; next to OpenStreetMap's, it
  shows at a glance the paths one source is missing.
- **In eight other countries**: the national map of Spain, Switzerland,
  Germany (BKG TopPlusOpen), Austria, the Netherlands, Luxembourg, Norway
  and the United States. Spain,
  Switzerland and the United States add their official trails, for display
  only. Germany adds an ATKIS path layer in all sixteen states. The ⓘ
  button, next to the base map selector, lists these countries.

A town search recenters the map: French municipalities through the French
government's Géo API, the rest of the world through Nominatim, OpenStreetMap's
search engine. A button switches the map to full screen. An indicator tells
whether a route can be planned right away, thanks to an OSM extract already
installed or to Overpass.
Right-click the map to show and copy the clicked point's GPS coordinates.

**The route.** A click sets the start, then the waypoints and the finish; a
point moves by dragging it and is removed from its popup. "Return" closes the
loop on the start, "Remove" takes off the last point, "Clear" starts over. The
routing is BRouter's, run locally, with OpenStreetMap's barriers laid across
the paths (see below). Three options tune it:

- **Strict mode**: also avoid the passages "to check", not only the blocking
  ones;
- **Official paths** (France and Germany): let BRouter use BD TOPO
  or ATKIS paths missing from OpenStreetMap. They show as orange dashes and
  join the points to check, since nothing guarantees they still exist or that
  you may walk them. In Spain, Switzerland and the United States, the checkbox
  names the country's official trails and states they are for display only;
- **Comparison**: show, dotted, the standard route that ignores the barriers,
  with its length and the blocking crossings it would go through.

**The result.** A summary gives the distance, the estimated time (Tobler's
model, applied to the slope of the profile), the elevation gain and loss, and
the highest and lowest points. The elevation profile unfolds at the bottom of
the map, with the name of the terrain model used; hovering over it shows the
matching point on the route. The crossings to check are listed, each with a
link that centers the map on it and another to the object in OpenStreetMap.
"Export GPX" saves the route, with those points as waypoints.

"Load a GPX" shows an existing track (GPX tracks and routes) in yellow on the
map and centers the view on it. Its name, without the extension, appears in
the layers: the checkbox hides or shows the track without removing it, and the
legend shows its yellow line while it is loaded. It serves as a guide while
you prepare the route: it changes neither the waypoints nor the export. Once
loaded, the button becomes "Remove GPX" and takes the track off the map
without touching the file on the computer. The loaded track stays on screen
until the page is closed or reloaded.

**The settings.** The IGN key for the SCAN 25, how long downloaded data is
kept before being renewed (30 days by default), the transparency of the panels
and whether to hide them, and a button that empties all local caches. One
button opens the `logs` folder, which holds the logs of the application and of
BRouter; another shows the installed version and checks whether a newer one
exists. The page speaks French or English, and when reopened it restores the
view, the base map, the layers and the options of the previous session.
Downloads, imports and computations in progress appear in a banner at the
bottom of the map.

## How it works

The routing relies on five pieces.

1. **The crossings.** For the area of the route, hike2gpx reads from
   OpenStreetMap (from an installed extract, or through Overpass, in 0.05°
   tiles kept for seven days) the paths you can walk, the barriers drawn as
   lines, the barrier nodes and the waymarked hiking routes. Each crossing is
   judged **blocking**, **to check** or **passable**, with the rules of
   [gpx2elev](https://github.com/nico579/gpx2elev), copied as they are into
   `regles.py`: a fence crossed with no mapped opening blocks, a gate with no
   access information is to check, `foot=yes` wins over `access=private`,
   opening hours or conditions leave a doubt.
2. **The engine.** [BRouter](https://github.com/abrensch/brouter), the one
   Locus uses, computes the route locally. Each crossing reaches it as a small
   one-meter line laid across the path: without a weight, it removes the
   stretch from the routing; with a weight, it makes it costly, so that a
   detour of less than about 300 m avoids it. The profile is BRouter's hiking
   profile, corrected so that a pedestrian ban (`foot=no` or `foot=private`)
   is respected even where a bicycle could pass or a sidewalk is tagged. When
   two cuts fall on the same stretch, the forbidden one always wins over the
   weighted one; and if the route returned by BRouter still went through a
   forbidden cut, hike2gpx would reject it instead of showing it.
3. **The page.** A local page, served by the shared library
   [nico579-commons](https://pypi.org/project/nico579-commons/), which the
   other nico579 applications share for the tray icon, the language and the
   updates. Each computation leaves its trace in the session log
   (`logs/hike2gpx-<date>.log`, in the data folder; the last ten sessions are
   kept), with the time of each step, its errors and its slow spots.
4. **The elevation.** Once the route is displayed, the
   [gpx2elev](https://pypi.org/project/gpx2elev/) engine recomputes its
   elevation gain: track sampled every 5 m, 20 m Gaussian smoothing, 2 m
   hysteresis. It takes the best terrain model covering the whole route: IGN
   LiDAR HD in France, otherwise Mapterhorn, FABDEM, Copernicus GLO-30 or SRTM.
   BRouter's figure, taken from a coarser worldwide model, is only an estimate
   in the meantime; if no model covers the route, the elevation is reported as
   unavailable rather than replaced by that figure.
5. **Official paths in France and Germany.** A path that the BD TOPO knows and
   OpenStreetMap does not is invisible to BRouter, which only sees its own
   tiles. So hike2gpx builds its own BRouter tile from the data it has already
   read: the OpenStreetMap ways, plus the BD TOPO sections that duplicate none
   of them, connected to the network. The tile grows with the areas you visit,
   up to 25 tiles of 0.05° before starting again from the requested area, and
   is rebuilt only for a new area or reread data, in about six seconds for nine
   tiles. The crossings are then looked for on the merged network: an OSM path
   and an IGN path stopping on either side of a fence, once connected, cross
   it. These paths cost a little more than the others, show as orange dashes
   on the route and join the points to check, since nothing says they still
   exist or that you may walk them; a restricted pedestrian access in the
   BD TOPO closes them. A checkbox lets you do without them, and if building
   the tile fails, the route is computed on OpenStreetMap alone, with a
   warning. In Germany, the ATKIS layer and routing load the same small areas
   on demand. Bavaria and Thuringia use their native WFS; the other fourteen
   states use [basemap.de's](https://basemap.de/produkte-und-dienste/web-vektor/)
   official vector tiles derived from ATKIS Basis-DLM. Those presentation
   geometries may have less precise connections. ATKIS additions carry a
   penalty and are marked for checking. In the tile containing Rosa, 76.6 km of the examined
   ATKIS ways pass the missing-from-OSM test, compared with 96.8 km of OSM
   ways; this potential gain does not prove pedestrian access. BD TOPO adds
   18 to 100 % in the French areas measured. The official sources examined in
   the United States, Switzerland and the Netherlands add only 0 to 12 %, so
   routing there stays on OSM alone. The
   measurement and the analysis are in
   [RAPPORT_SOURCES_CHEMINS_BROUTER.md](RAPPORT_SOURCES_CHEMINS_BROUTER.md)
   (in French).

What hike2gpx adds to the gpx2elev rules, because it examines a whole network
rather than a single track:

- a barrier that stops on a path, or touches it and leaves on the same side,
  does not cross it; nor does a path on a bridge or in a tunnel;
- a barrier that ends less than 2 m from the path can be walked around;
- a gate set in the fence very close to the path, without being carried by it,
  is judged as if it were: locked or private, it does not make the fence
  passable;
- two different levels (`layer`) make the crossing "to check";
- a waymarked trail has to go through somewhere: a barrier that would block it
  becomes "to check" there.

If OpenStreetMap does not answer, the computation stops: an unknown barrier
never proves that a passage is free. And if no route exists, the page says so,
without joining the points in a straight line.

### Offline OSM data

Overpass, the service that answers questions about OpenStreetMap, saturates at
times and sometimes goes down. To stop depending on it, hike2gpx downloads by
itself an OpenStreetMap extract around the place where you are working.

Anywhere in the world, it is the smallest
[Geofabrik](https://download.geofabrik.de/) extract that contains the whole
area, among some 550: Liechtenstein for Vaduz (3 MB), a US state such as Utah
rather than the whole United States. In France, hike2gpx works in two steps.
First the département, taken from the
[OSM France extracts](https://download.openstreetmap.fr/extracts/europe/france/):
for Garéoult, the Var weighs 83 MB and is ready in about forty seconds,
import included; you can work right away. Meanwhile, the Geofabrik region gets
ready: Provence-Alpes-Côte d'Azur weighs 391 MB and takes more than three
minutes. As soon as it is there, it takes over, because OSM France cuts the
paths sharply at the edge of the département, where Geofabrik keeps them
whole.

The download starts once the region is really in use, by a computation or the
OSM paths layer, but not when the map merely flies over it; it stops if the
map leaves the region. It runs in the background, checked against its MD5,
while Overpass keeps serving; the panel follows its progress, and a
computation that was waiting for it resumes by itself as soon as the extract
is there. An extract over 2 GB, or one the disk could not hold, is not
downloaded: Overpass then remains the source. The extract is read once and
stored in a SQLite database per tile, in the data folder (`geofabrik/`), then
the downloaded file is deleted.

Once installed, the extract is the source of the tiles it contains: instant
reading, no quota, no outage, offline included. A tile comes out of it in the
exact form of an Overpass answer, so the crossings are judged the same way.
Overpass only serves elsewhere: outside the installed extracts, or on a tile
straddling their edge; and a tile that was waiting for Overpass when an
extract gets installed switches to it at once. OSM France and Geofabrik
rebuild their extracts every day; once older than the delay chosen in the
settings (30 days by default, from 1 to 365), the extract renews itself in the
background, the old one serving until the switch. The BRouter tiles follow the
same delay.

## Limits

hike2gpx can only avoid what is mapped. Around Garéoult, over 250 km²,
OpenStreetMap records only 18 fences, and IGN's BD TOPO none (see
[ESSAI.md](ESSAI.md), in French). A fence found in the field and added to
OpenStreetMap is respected by hike2gpx as soon as its cache of the area is
renewed; the engines of the other planners keep ignoring it.

Outside France and Germany, routing only knows OpenStreetMap's
paths: a trail missing from OSM does not exist for it, even if the national
map draws it. The integrated ATKIS ways do not state explicit pedestrian
rights, so any routed section must be checked on site.

A computation examines at most 100 tiles of 0.05°, about 55 × 40 km: the first
reading of a larger area would take tens of minutes. A long route is split
into stages.

## Installation

The simplest way: download the program for your system from the
[releases](https://github.com/nico579/hike2gpx/releases) (Windows, Linux,
macOS), unzip it, for instance on Windows into
`%LOCALAPPDATA%\Programs\hike2gpx`, and run `hike2gpx`. It ships its own Java
and updates itself; "Create a Desktop shortcut", in the menu of its tray icon,
adds the shortcut.

From source, you need Python 3.12, [uv](https://docs.astral.sh/uv/) and
Java 11 or later for BRouter.

```
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -e ".[test]"
.venv\Scripts\hike2gpx installer E5_N40
.venv\Scripts\hike2gpx serve
```

`installer` downloads BRouter 1.7.10 (archive checked against its SHA256
digest) and a data tile, here E5_N40, which covers Provence, from 5° to 10° E
and from 40° to 45° N. From the page, there is nothing to do: the engine
installs itself on first launch, and each data tile downloads in the
background as soon as a computation needs it, anywhere in the world, the
computation resuming when it arrives. The data goes into the standard state
folder (`%LOCALAPPDATA%\hike2gpx-data` on Windows), or the one named by the
`HIKE2GPX_HOME` variable.

The SCAN 25 is not open data: it needs an IGN key, entered in the page
settings. Without a key, the map uses the IGN Plan, under the Licence Ouverte
(the French open licence). The other base maps need no key.

## Tests

```
.venv\Scripts\python.exe -m pytest
```

The unit tests run without network or BRouter. `test_regles.py` compares
`regles.py` with its source in gpx2elev when that repository is on the
machine. `test_integration.py` replays a real case from Garéoult with the
actual BRouter: it is skipped as long as BRouter and its E5_N40 tile are
missing from the data folder, and runs in a few seconds with
`$env:HIKE2GPX_HOME = 'D:\hike2gpx'`. `test_integration_maison.py` builds a
home-made tile with the actual tile builder, on a small invented network where
two OSM paths only meet through IGN paths; it also needs BRouter's build
profiles, which the first build from the page downloads into the data folder.
`test_integration_securite.py` checks in the same way, on six invented cases,
that the profile and the order of the cuts respect the prohibitions.
`test_page.py` runs the page under Node, when Node is installed; it also
checks that every country in `providers/` has its labels in French and
English. The tools in `tools/` replay the trial described in
[ESSAI.md](ESSAI.md) (in French) and the measurement of the path sources.

## Building the program

```
python build.py --archive
```

`build.py` creates an isolated environment, fills it from the
`requirements-build.txt` lock file (exact versions and digests, PyInstaller
included), downloads the Temurin 21 JRE for this system while checking the
digest Adoptium publishes, builds the program with `hike2gpx.spec`, then runs
its self-test (`--self-test-version`): embedded Java, pyosmium, rasterio, page.
With `--archive`, it packs the published archive and its `.sha256`, under the
name the shared library's automatic update expects. The frozen program only
uses its own Java; from source, hike2gpx uses the system's. On GitHub,
`release.yml` does the same on the four systems for every tag, and on every
pull request that touches the program. On macOS, it needs macOS 15 or later,
as do the rasterio wheels.

The lock files are regenerated with uv:

```
uv pip compile pyproject.toml --universal --python-version 3.12 --generate-hashes -o requirements.txt
uv pip compile requirements-build.in --universal --python-version 3.12 --generate-hashes -o requirements-build.txt
```

## License

GPL-3.0-or-later. BRouter (MIT) is downloaded at installation; Leaflet 1.9.4
(BSD-2-Clause) is shipped in `hike2gpx/assets/web/leaflet`. The published
program embeds Eclipse Adoptium's Temurin 21 JRE (GPL-2.0 with the Classpath
exception, texts in `_internal/jre/legal`). Data © OpenStreetMap contributors
(ODbL), including the test extract `tests/donnees/gareoult_cloture.json`;
BD TOPO © IGN (Licence Ouverte); maps © IGN, and for the national base maps,
© each agency, as credited on the map.
