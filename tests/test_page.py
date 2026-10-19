"""La page (app.js) sous Node, par page.test.cjs : sauté si Node est absent."""
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="Node absent")
def test_page_sous_node():
    r = subprocess.run([NODE, "--test", str(Path(__file__).with_name("page.test.cjs"))], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, (r.stdout + r.stderr)[-4000:]
