import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "packages" / "manifest"
NAME = re.compile(r"^[a-z0-9][a-z0-9+.\-]+$")


def read_list(path):
    out = []
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line.split()[0])
    return out


INSTALL_LISTS = ["base.list", "desktop.list", "applications.list", "tools.list", "live.list"]


@pytest.mark.parametrize("name", INSTALL_LISTS + ["excluded.list"])
def test_list_exists_and_valid_names(name):
    pkgs = read_list(MANIFEST / name)
    assert pkgs, name
    for p in pkgs:
        assert NAME.match(p), f"{name}: invalid package name {p!r}"


def test_no_duplicates_across_install_lists():
    seen = {}
    for name in INSTALL_LISTS:
        for p in read_list(MANIFEST / name):
            assert p not in seen, f"{p} in both {seen.get(p)} and {name}"
            seen[p] = name


def test_excluded_packages_are_not_installed():
    excluded = set(read_list(MANIFEST / "excluded.list"))
    for name in INSTALL_LISTS:
        clash = excluded & set(read_list(MANIFEST / name))
        assert not clash, f"{name} installs excluded packages: {clash}"


def test_excluded_entries_have_a_reason():
    for line in (MANIFEST / "excluded.list").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            assert "#" in line, f"no reason given: {line}"


def test_essential_components_present():
    allp = {p for n in INSTALL_LISTS for p in read_list(MANIFEST / n)}
    required = {"apparmor", "unattended-upgrades", "network-manager", "gdm3", "gnome-shell",
                "gnome-software", "gnome-software-plugin-flatpak", "flatpak",
                "shim-signed", "grub-efi-amd64-signed", "grub-pc", "casper", "ubiquity", "update-manager"}
    assert required <= allp, required - allp


def test_no_snaps():
    excluded = set(read_list(MANIFEST / "excluded.list"))
    assert {"snapd", "gnome-software-plugin-snap"} <= excluded
    build = (ROOT / "scripts/build/build-iso.sh").read_text()
    assert "snap prepare-image" not in build and "TROTA_SEED_SNAPS" not in build
    # Ubuntu's firefox deb is a snap installer: it must never be in a list
    for name in INSTALL_LISTS:
        assert "firefox" not in read_list(MANIFEST / name), name
    assert "install firefox firefox-l10n-it" in build


def test_telemetry_is_excluded():
    excluded = set(read_list(MANIFEST / "excluded.list"))
    assert {"ubuntu-report", "whoopsie", "popularity-contest", "apport", "openssh-server"} <= excluded


def test_live_only_packages_are_removed_after_install():
    build = (ROOT / "scripts/build/build-iso.sh").read_text()
    assert "filesystem.manifest-remove" in build
    for p in read_list(MANIFEST / "live.list"):
        base = p.split("-")[0]
        assert base in ("casper", "ubiquity", "gparted"), p
    # ubiquity crashes without a slideshow: ours must be built and checked by the build
    assert "Package: ubiquity-slideshow-trota" in (ROOT / "packaging/debian/control").read_text()
    assert "/usr/share/ubiquity-slideshow/slides/index.html" in build


def test_firmware_filter_is_installed_before_the_kernel():
    conf = ROOT / "packaging/files/settings/trota-firmware-exclude"
    rules = (ROOT / "packaging/debian/rules").read_text()
    build = (ROOT / "scripts/build/build-iso.sh").read_text()
    assert "packaging/files/settings/trota-firmware-exclude $(SET)/etc/dpkg/dpkg.cfg.d/" in rules
    # the build copies it into the chroot before any package is installed
    assert build.index("trota-firmware-exclude") < build.index('install $(read_list "$m/base.list"')
    patterns = [ln.split("=", 1)[1] for ln in conf.read_text().splitlines() if ln.startswith("path-exclude=")]
    assert patterns and all(p.startswith(("/lib/firmware/", "/usr/lib/firmware/")) and p.endswith("/*") for p in patterns)
