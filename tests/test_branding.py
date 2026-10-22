import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BRANDING = ROOT / "branding"
PALETTE = {"#101214", "#191D21", "#737B84", "#E8ECEF", "#FF6A2A"}


def test_committed_svgs_are_up_to_date():
    p = subprocess.run([sys.executable, str(BRANDING / "generate.py"), "--check"], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr


@pytest.mark.parametrize("svg", sorted(BRANDING.rglob("*.svg")), ids=lambda p: str(p.relative_to(BRANDING)))
def test_svg_is_well_formed_and_self_contained(svg):
    tree = ET.parse(svg)
    text = svg.read_text()
    assert tree.getroot().tag.endswith("svg")
    assert "<text" not in text, "logos must not depend on installed fonts"
    assert "<image" not in text and "http://" not in text.replace("http://www.w3.org/2000/svg", "")


def test_palette_is_used():
    text = "".join(p.read_text() for p in BRANDING.rglob("*.svg"))
    for color in PALETTE:
        assert color in text, color


def test_plymouth_frames(tmp_path):
    p = subprocess.run([sys.executable, str(BRANDING / "generate.py"), "--plymouth-frames", str(tmp_path), "--frames", "12"])
    assert p.returncode == 0
    frames = sorted(tmp_path.glob("throbber-*.svg"))
    assert len(frames) == 12 and frames[0].name == "throbber-0001.svg"
    for name in ("entry.svg", "bullet.svg", "lock.svg", "capslock.svg", "keyboard.svg"):
        ET.parse(tmp_path / name)


def test_plymouth_theme_file():
    import configparser

    cp = configparser.ConfigParser()
    cp.read(BRANDING / "themes/plymouth/trota/trota.plymouth")
    assert cp["Plymouth Theme"]["ModuleName"] == "two-step"
    assert cp["two-step"]["ImageDir"] == "/usr/share/plymouth/themes/trota"


def test_grub_theme_references_existing_assets():
    theme = (BRANDING / "themes/grub/trota/theme.txt").read_text()
    assert 'desktop-image: "background.png"' in theme
    assert (BRANDING / "themes/grub/trota/background.svg").exists()


@pytest.mark.skipif(subprocess.run(["which", "rsvg-convert"], capture_output=True).returncode != 0,
                    reason="rsvg-convert not installed")
def test_render_script(tmp_path):
    p = subprocess.run(["sh", str(BRANDING / "render.sh"), str(tmp_path)], capture_output=True, text=True,
                       env={"PYTHON": sys.executable, "PATH": "/usr/bin:/bin"})
    assert p.returncode == 0, p.stderr
    for rel in ("wallpapers/trota-forge.png", "grub/trota/background.png", "plymouth/trota/watermark.png",
                "plymouth/trota/throbber-0036.png", "pixmaps/trota-logo-gdm.png",
                "icons/48x48/it.testardstudios.TrotaWelcome.png"):
        f = tmp_path / rel
        assert f.exists() and f.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", rel


def test_installer_slideshow():
    import re

    html = (BRANDING / "slideshow/slides/index.html").read_text()
    assert "http://" not in html.replace("http://www.w3.org/2000/svg", "") and "https://" not in html
    assert 'logo.src = "trota-logo-dark.svg"' in html
    # every language has the same number of slides
    en = html[html.index("en: ["):html.index("it: [")]
    it = html[html.index("it: ["):html.index("var FOOT")]
    assert len(re.findall(r"\{ t:", en)) == len(re.findall(r"\{ t:", it)) >= 4
    conf = (BRANDING / "slideshow/slideshow.conf").read_text()
    assert "width:752" in conf and "height:442" in conf
