"""Smoke test the Android adapter with an existing local BRouter installation.

Usage: python android/smoke/run.py PATH_TO_BROUTER_DIRECTORY PATH_TO_JDK
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if len(sys.argv) != 3:
    raise SystemExit(__doc__)

data, jdk = Path(sys.argv[1]), Path(sys.argv[2])
root = Path(__file__).resolve().parents[1]
classes = root / "app/build/intermediates/javac/debug/compileDebugJavaWithJavac/classes"
source = Path(__file__).with_name("RouterSmoke.java")
profiles = data / "brouter-1.7.10/profiles2"
with tempfile.TemporaryDirectory(prefix="hike2gpx-android-smoke-") as temp:
    package = Path(temp) / "package"
    package.mkdir()
    segment = data / "segments4/E5_N40.rd5"
    try:
        os.link(segment, package / segment.name)
    except OSError:
        shutil.copy2(segment, package / segment.name)
    for name in ("lookups.dat", "hike2gpx.brf"):
        shutil.copy2(profiles / name, package / name)
    subprocess.run([str(jdk / "bin/javac"), "-cp", str(classes), "-d", temp, str(source)], check=True)
    subprocess.run([str(jdk / "bin/java"), "-cp", os.pathsep.join((temp, str(classes))),
                    "org.hike2gpx.android.RouterSmoke", str(package)], check=True)
