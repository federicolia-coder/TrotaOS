import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = sorted(ROOT.glob("scripts/**/*.sh")) + [ROOT / "branding/render.sh"]


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: str(p.relative_to(ROOT)))
def test_shell_syntax(script):
    shell = "sh" if script.read_text().startswith("#!/bin/sh") else "bash"
    assert subprocess.run([shell, "-n", str(script)]).returncode == 0


@pytest.mark.skipif(not shutil.which("shellcheck"), reason="shellcheck not installed")
@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: str(p.relative_to(ROOT)))
def test_shellcheck(script):
    p = subprocess.run(["shellcheck", "-x", "-S", "warning", str(script)], capture_output=True, text=True, cwd=ROOT)
    assert p.returncode == 0, p.stdout


def config():
    out = subprocess.run(["bash", "-c", f". {ROOT}/scripts/build/config.env; set | grep ^TROTA_"],
                         capture_output=True, text=True, check=True).stdout
    return dict(line.split("=", 1) for line in out.splitlines())


def test_config_values():
    c = config()
    volid = c["TROTA_ISO_VOLID"].strip("'")
    assert len(volid) <= 32 and volid.replace("_", "").isalnum() and volid.isupper()
    assert c["TROTA_BASE_SUITE"] == "noble"
    assert c["TROTA_ARCH"] == "amd64"
    assert c["TROTA_SQUASHFS_COMP"] in ("xz", "zstd", "gzip", "lzo", "lz4")


def test_config_can_be_overridden():
    out = subprocess.run(["bash", "-c", f"export TROTA_VERSION=9.9; . {ROOT}/scripts/build/config.env; echo $TROTA_VERSION"],
                         capture_output=True, text=True, check=True).stdout
    assert out.strip() == "9.9"


def test_safe_rm_refuses_paths_outside_build(tmp_path):
    script = f"""
        . {ROOT}/scripts/build/lib.sh
        safe_rm {tmp_path}
    """
    p = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert p.returncode != 0 and "refusing" in p.stderr
    assert tmp_path.exists()


def test_safe_rm_refuses_build_root_itself():
    p = subprocess.run(["bash", "-c", f". {ROOT}/scripts/build/lib.sh; safe_rm $BUILD"], capture_output=True, text=True)
    assert p.returncode != 0 and "refusing" in p.stderr


def test_read_list_strips_comments(tmp_path):
    f = tmp_path / "x.list"
    f.write_text("# comment\nfoo   # inline\n\n  \nbar\n")
    p = subprocess.run(["bash", "-c", f". {ROOT}/scripts/build/lib.sh; read_list {f}"], capture_output=True, text=True)
    assert p.stdout.split() == ["foo", "bar"]


def test_build_iso_requires_root():
    import os

    if os.geteuid() == 0:
        pytest.skip("running as root")
    p = subprocess.run([str(ROOT / "scripts/build/build-iso.sh"), "iso"], capture_output=True, text=True)
    assert p.returncode != 0 and "root" in p.stderr


def test_chroot_umount_with_nothing_mounted():
    """Regression: with nothing mounted, grep returned 1 and pipefail made the
    whole build exit silently at the start of the 'iso' stage."""
    script = f"""
        . {ROOT}/scripts/build/lib.sh
        d="$BUILD/test-empty-chroot-$$"
        mkdir -p "$d"
        chroot_umount "$d"
        rmdir "$d"
        echo survived
    """
    p = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert p.returncode == 0 and "survived" in p.stdout, p.stderr


def test_errors_are_reported_not_silent():
    p = subprocess.run(["bash", "-c", f". {ROOT}/scripts/build/lib.sh; f() {{ false; }}; f"],
                       capture_output=True, text=True)
    assert p.returncode != 0 and "command failed" in p.stderr
