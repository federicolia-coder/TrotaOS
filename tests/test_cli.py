import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = dict(os.environ, PYTHONPATH=os.pathsep.join(str(p) for p in sorted((ROOT / "applications").iterdir())))


def run(*args):
    return subprocess.run([sys.executable, "-m", *args], capture_output=True, text=True, env=ENV, timeout=180)


def test_system_info_json():
    p = run("trota_system_info", "--json")
    assert p.returncode == 0, p.stderr
    data = json.loads(p.stdout)
    assert {"kernel", "cpu", "memory", "disks", "network", "os_pretty_name"} <= set(data)


def test_system_info_text():
    p = run("trota_system_info", "--text")
    assert p.returncode == 0 and "Kernel" in p.stdout


def test_system_info_does_not_import_gtk_in_text_mode():
    code = ("import sys; from trota_system_info import cli; cli.main(['--json']); "
            "assert 'gi.repository.Gtk' not in sys.modules, 'GTK imported'")
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=ENV, timeout=120)
    assert p.returncode == 0, p.stderr


def test_diagnostics_json_and_exit_code():
    p = run("trota_diagnostics", "--json", "--no-dns")
    data = json.loads(p.stdout)
    worst = {r["status"] for r in data}
    expected = 2 if "error" in worst else 1 if "warning" in worst else 0
    assert p.returncode == expected


def test_diagnostics_text_format():
    from trota_common.diagnostics import CheckResult
    from trota_diagnostics.cli import exit_code, format_text

    rs = [CheckResult("a", "Disk", "warning", "Low", ["/: 1 GiB"], "Clean up")]
    out = format_text(rs)
    assert "[WARN] Disk: Low" in out and "-> Clean up" in out
    assert exit_code(rs) == 1


def test_version_flags():
    for mod in ("trota_system_info", "trota_diagnostics"):
        p = run(mod, "--version")
        assert p.returncode == 0 and "1.0.0" in p.stdout
