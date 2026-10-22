"""Start every GUI application under a virtual X server and render it."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
pytest.importorskip("gi")
if not shutil.which("xvfb-run"):
    pytest.skip("xvfb-run not installed", allow_module_level=True)


@pytest.mark.parametrize("app,action,seconds", [
    ("welcome", None, 3), ("welcome", "page:3", 3), ("welcome", "page:4", 3),
    ("system-info", None, 4), ("diagnostics", "run-checks", 15), ("package-helper", "search:bash", 6), ("vr", None, 8),
])
def test_app_renders(tmp_path, app, action, seconds):
    out = tmp_path / f"{app}.png"
    env = dict(os.environ, GDK_BACKEND="x11", NO_AT_BRIDGE="1", GTK_A11Y="none",
               PYTHONPATH=os.pathsep.join(str(p) for p in sorted((ROOT / "applications").iterdir())),
               TROTA_DATA_DIR=str(ROOT / "applications/trota-common/data"))
    cmd = ["xvfb-run", "-a", "-s", "-screen 0 1280x900x24", sys.executable,
           str(ROOT / "tests/ui/render_window.py"), app, str(out), "--seconds", str(seconds)]
    if action:
        cmd += ["--action", action]
    p = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
    assert p.returncode == 0, p.stderr[-2000:]
    assert "Traceback" not in p.stderr, p.stderr[-2000:]
    assert "CRITICAL" not in p.stderr, p.stderr[-2000:]
    assert "markup" not in p.stderr, p.stderr[-2000:]
    assert out.exists() and out.stat().st_size > 5000
