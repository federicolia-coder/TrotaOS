"""Internal edition: trota_common.internal and the trota-internal package files."""

import configparser
import subprocess
from pathlib import Path

from trota_common import internal

ROOT = Path(__file__).resolve().parents[1]
FILES = ROOT / "packaging/files/internal"


def test_edition_marker(tmp_path):
    assert not internal.is_internal(tmp_path)
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc/trota-edition").write_text("vr\n")
    assert not internal.is_internal(tmp_path)
    (tmp_path / "etc/trota-edition").write_text("internal\n")
    assert internal.is_internal(tmp_path)


def test_config_defaults_and_overrides(tmp_path):
    conf = internal.load(tmp_path)
    assert conf.admin_url == internal.DEFAULT_ADMIN_URL
    assert conf.support_uri == f"mailto:{internal.DEFAULT_SUPPORT_EMAIL}"
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc/trota-internal.conf").write_text(
        "# comment\nADMIN_URL=https://admin.example/\nSUPPORT_EMAIL=help@example.org\n")
    conf = internal.load(tmp_path)
    assert conf.admin_url == "https://admin.example/" and conf.support_email == "help@example.org"


def test_shipped_config_matches_defaults(tmp_path):
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc/trota-internal.conf").write_text((FILES / "trota-internal.conf").read_text())
    conf = internal.load(tmp_path)
    assert conf.admin_url == internal.DEFAULT_ADMIN_URL
    assert conf.support_email == internal.DEFAULT_SUPPORT_EMAIL


def test_support_texts():
    assert internal.support_title() == "Contact technical support"
    assert internal.support_subtitle() == "NOT FEDERICO, PREFERABLY"


def test_admin_launcher_reads_the_config(tmp_path):
    script = (FILES / "testard-admin").read_text()
    assert internal.DEFAULT_ADMIN_URL in script and "xdg-open" in script
    # Run it with a fake xdg-open: it must open the configured URL.
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "xdg-open").write_text('#!/bin/sh\necho "$1"\n')
    (fake / "xdg-open").chmod(0o755)
    p = subprocess.run(["sh", str(FILES / "testard-admin")], capture_output=True, text=True,
                       env={"PATH": f"{fake}:/usr/bin:/bin"})
    assert p.returncode == 0 and p.stdout.strip().startswith("https://")


def test_desktop_entry():
    entry = configparser.ConfigParser(interpolation=None)
    entry.optionxform = str
    entry.read(FILES / "it.testardstudios.TestardAdmin.desktop")
    d = entry["Desktop Entry"]
    assert d["Type"] == "Application" and d["Exec"] == "testard-admin"
    assert d["Name[it]"] == "Pannello admin Testard"


def test_gschema_override_points_to_the_internal_wallpaper():
    text = (FILES / "95_trota-internal.gschema.override").read_text()
    assert "trota-internal.png" in text
    assert "it.testardstudios.TestardAdmin.desktop" in text
    assert (ROOT / "branding/wallpapers/trota-internal.svg").exists()


def test_only_the_internal_iso_installs_the_package():
    iso = (ROOT / "scripts/build/build-iso.sh").read_text()
    assert "! -name 'trota-internal_*'" in iso and 'echo internal > "$CHROOT/etc/trota-edition"' in iso
    rules = (ROOT / "packaging/debian/rules").read_text()
    # trota-artwork ships only the public wallpapers.
    assert "for w in forge steel ingot; do" in rules
    assert "Package: trota-internal" in (ROOT / "packaging/debian/control").read_text()
