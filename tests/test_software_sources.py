"""Configuration shipped by trota-software-sources (no snaps, Firefox from
Mozilla, Flathub, no Ubuntu Pro advertising)."""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "packaging/files/sources"
RULES = (ROOT / "packaging/debian/rules").read_text()
# Published by Mozilla: https://support.mozilla.org/kb/install-firefox-linux
MOZILLA_FPR = "35BAA0B33E9EB396F59CA838C0BA5CE6DC6315A3"


def stanzas(text):
    out = []
    for block in re.split(r"\n\s*\n", text):
        lines = [ln for ln in block.splitlines() if ln.strip() and not ln.startswith("#")]
        if lines:
            out.append(dict(ln.split(": ", 1) for ln in lines))
    return out


def test_every_file_is_installed_by_the_package():
    for f in SRC.iterdir():
        assert f"packaging/files/sources/{f.name}" in RULES, f.name


def test_mozilla_source_uses_the_bundled_key():
    (s,) = stanzas((SRC / "mozilla.sources").read_text())
    assert s["URIs"] == "https://packages.mozilla.org/apt" and s["Suites"] == "mozilla"
    assert s["Signed-By"] == "/usr/share/keyrings/packages.mozilla.org.asc"
    assert "$(SRC)/usr/share/keyrings/packages.mozilla.org.asc" in RULES


def test_mozilla_key_fingerprint():
    try:
        out = subprocess.run(["gpg", "--show-keys", "--with-colons", str(SRC / "packages.mozilla.org.asc")],
                             capture_output=True, text=True, check=True).stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("gpg not available")
    fprs = [ln.split(":")[9] for ln in out.splitlines() if ln.startswith("fpr:")]
    assert fprs[0] == MOZILLA_FPR


def test_firefox_pins():
    pins = stanzas((SRC / "trota-mozilla.pref").read_text())
    by_pin = {p["Pin"]: int(p["Pin-Priority"]) for p in pins}
    assert all(p["Package"] == "firefox*" for p in pins)
    assert by_pin["origin packages.mozilla.org"] >= 1000
    assert by_pin["release o=Ubuntu"] < 0


def test_snapd_is_blocked():
    (p,) = stanzas((SRC / "trota-no-snap.pref").read_text())
    assert p["Package"] == "snapd" and int(p["Pin-Priority"]) < 0


def test_pro_advertising_hook_cleared():
    text = (SRC / "99trota-no-pro-ads").read_text()
    assert "#clear binary::apt::AptCli::Hooks::Upgrade;" in text
    # Pre-Invoke is shared with other packages: it must not be cleared
    assert "#clear APT::Update::Pre-Invoke" not in text
    for unit in ("esm-cache.service", "apt-news.service"):
        assert f"ln -sf /dev/null $(SRC)/etc/systemd/system/{unit}" in RULES


def test_flathub_remote():
    text = (SRC / "flathub.flatpakrepo").read_text()
    assert "[Flatpak Repo]" in text and "Url=https://dl.flathub.org/repo/" in text
    assert re.search(r"^GPGKey=[A-Za-z0-9+/=]{100,}$", text, re.M)
    postinst = (ROOT / "packaging/debian/trota-software-sources.postinst").read_text()
    assert "flatpak remote-add --system --if-not-exists flathub" in postinst


def test_metapackage_depends_on_it():
    control = (ROOT / "packaging/debian/control").read_text()
    meta = control.split("Package: trota-desktop\n", 1)[1].split("\n\n", 1)[0]
    assert "trota-software-sources" in meta
