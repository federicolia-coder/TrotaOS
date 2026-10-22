"""The Trota OS os-release file and the compatibility it must keep.

The system identifies itself as Trota OS (ID=trota) and declares the base in
ID_LIKE; the codenames stay those of the base so that APT sources, PPAs and
third-party repositories keep working (ADR-005). The file must be parseable by
aptsources (python3-apt), whose parser does not accept comments or blank lines
although os-release(5) does: a comment line broke "Software & Updates" in an
early test build.
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
    assert d["ID"] == "trota" and d["VERSION_ID"] == d["TROTA_VERSION"]
    assert d["ID_LIKE"].split()[:2] == ["ubuntu", "debian"]
    # lsb_release -c, unattended-upgrades, PPAs and python-apt templates use it
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
    assert rel.result["Distributor ID"] == "trota"
    assert rel.result["Codename"] == "noble"
    assert rel.result["ID_LIKE"][0] == "ubuntu"


def test_shell_sourcing_matches(tmp_path):
    """lsb_release and many scripts source the file with /bin/sh."""
    import subprocess

    out = subprocess.run(["sh", "-c", f'. "{OS_RELEASE}"; printf "%s|%s|%s" "$ID" "$NAME" "$TROTA_VERSION"'],
                         capture_output=True, text=True, check=True).stdout
    assert out == "trota|Trota OS|1.0"


def test_unattended_upgrades_keep_the_security_archive():
    """With ID=trota, ${distro_id} of 50unattended-upgrades no longer matches."""
    conf = (ROOT / "packaging/files/release/51trota-unattended-upgrades").read_text()
    assert '"Ubuntu:${distro_codename}-security";' in conf
    assert '"site=packages.mozilla.org";' in conf
    rules = (ROOT / "packaging/debian/rules").read_text()
    assert "51trota-unattended-upgrades" in rules


def test_python_apt_templates_for_trota():
    links = (ROOT / "packaging/debian/trota-release.links").read_text().split()
    pairs = dict(zip(links[1::2], links[0::2]))
    base = "usr/share/python-apt/templates/"
    assert pairs[base + "Trota.info"] == base + "Ubuntu.info"
    assert pairs[base + "Trota.mirrors"] == base + "Ubuntu.mirrors"


def test_build_checks_the_identity():
    build = (ROOT / "scripts/build/build-iso.sh").read_text()
    assert "lsb_release -is)\" = Trota" in build and "check_identity" in build
    assert "DISTRIB_ID=Trota" in build
    # ubiquity splits the medium name on spaces: "Trota-OS 1.0 ..."
    assert '"${FLAVOR_NAME// /-}"' in build and 'FLAVOR_NAME="$TROTA_NAME"' in build
