"""The Trota OS os-release file must stay compatible with Ubuntu tooling.

ID/VERSION_ID/VERSION_CODENAME keep the Ubuntu values (ADR-005), and the file
must be parseable by aptsources (python3-apt), whose parser does not accept
comments or blank lines although os-release(5) does: a comment line broke
"Software & Updates" in an early test build.
"""

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
OS_RELEASE = ROOT / "packaging/files/release/os-release"

from trota_common import osinfo  # noqa: E402


def test_no_comments_or_blank_lines():
    for n, line in enumerate(OS_RELEASE.read_text().splitlines(), 1):
        assert line.strip(), f"blank line {n}"
        assert "=" in line and not line.lstrip().startswith("#"), f"line {n}: {line!r}"


def test_compatibility_identifiers():
    d = osinfo.parse_os_release(OS_RELEASE.read_text())
    assert d["ID"] == "ubuntu" and d["VERSION_ID"] == "24.04"
    assert d["VERSION_CODENAME"] == "noble" == d["UBUNTU_CODENAME"]
    assert d["NAME"] == "Trota OS" and d["PRETTY_NAME"].startswith("Trota OS")
    assert d["TROTA_VERSION"] and d["LOGO"] == "trota-os-logo"


def test_parsed_by_real_aptsources(monkeypatch):
    if "/usr/lib/python3/dist-packages" not in sys.path:
        monkeypatch.syspath_prepend("/usr/lib/python3/dist-packages")
    try:
        distro = importlib.import_module("aptsources.distro")
    except Exception:
        pytest.skip("python3-apt (aptsources) not available")
    monkeypatch.setattr(distro._OSRelease, "OS_RELEASE_FILE", str(OS_RELEASE))
    rel = distro._OSRelease()
    assert rel.valid
    assert rel.result["Distributor ID"] == "ubuntu"
    assert rel.result["Codename"] == "noble"


def test_shell_sourcing_matches(tmp_path):
    """lsb_release and many scripts source the file with /bin/sh."""
    import subprocess

    out = subprocess.run(["sh", "-c", f'. "{OS_RELEASE}"; printf "%s|%s|%s" "$ID" "$NAME" "$TROTA_VERSION"'],
                         capture_output=True, text=True, check=True).stdout
    assert out == "ubuntu|Trota OS|1.0"
