#!/usr/bin/env python3
"""Generate the wallpaper of the internal edition (branding/wallpapers/trota-internal.svg).

The text is converted to outlines, so the SVG does not depend on installed
fonts (tests/test_branding.py). Unlike generate.py this needs fontTools and
the Inter font, so it is run by hand when the wallpaper changes and the SVG
is committed:

    pip install fonttools
    python3 branding/make-internal-wallpaper.py [--font-dir /usr/share/fonts/opentype/inter]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate import CARBON, FROST, GRAPHITE, ORANGE, STEEL, BODY, grid, svg, symbol  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "wallpapers/trota-internal.svg"


def outline(font: TTFont, text: str, size: float, x: float, y: float, fill: str, tracking: float = 0) -> tuple[str, float]:
    """Return an SVG <g> with `text` as paths (baseline at y) and its width."""
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    scale = size / font["head"].unitsPerEm
    paths, pen_x = [], 0.0
    for ch in text:
        name = cmap.get(ord(ch), ".notdef")
        pen = SVGPathPen(glyphs)
        glyphs[name].draw(pen)
        d = pen.getCommands()
        if d:
            paths.append(f'<path transform="translate({pen_x:.1f} 0)" d="{d}"/>')
        pen_x += glyphs[name].width + tracking / scale
    width = pen_x * scale
    return (f'<g fill="{fill}" transform="translate({x:.1f} {y:.1f}) scale({scale:.5f} {-scale:.5f})">'
            + "".join(paths) + "</g>", width)


def wallpaper(fonts: Path) -> str:
    bold = TTFont(fonts / "Inter-Bold.otf")
    medium = TTFont(fonts / "Inter-Medium.otf")
    w, h, uid = 3840, 2160, "internal"

    # The big question, left-aligned on a 12-column grid, the trout dimmed behind it.
    line1, _ = outline(bold, "Hey, sei un dipendente di Testard?", 150, 360, 980, FROST)
    line2, _ = outline(bold, "Come hai avuto questa distro?", 150, 360, 1180, ORANGE)
    note, _ = outline(medium, "Se non lo sei: complimenti per l'intraprendenza. Ora restituiscila.", 54, 366, 1330, STEEL)

    # A rubber stamp, slightly crooked, top right.
    stamp_w = 1020
    stamp_text, tw = outline(bold, "USO INTERNO", 120, 0, 0, ORANGE, tracking=12)
    stamp_sub, sw = outline(medium, "NON DISTRIBUIRE", 52, 0, 0, ORANGE, tracking=14)
    stamp = (
        f'<g transform="translate(3020 420) rotate(-8)" opacity="0.85">'
        f'<rect x="{-stamp_w / 2}" y="-150" width="{stamp_w}" height="300" rx="18" fill="none" stroke="{ORANGE}" stroke-width="12"/>'
        f'<rect x="{-stamp_w / 2 + 26}" y="-124" width="{stamp_w - 52}" height="248" rx="10" fill="none" stroke="{ORANGE}" stroke-width="4"/>'
        f'<g transform="translate({-tw / 2:.1f} 30)">{stamp_text}</g>'
        f'<g transform="translate({-sw / 2:.1f} 100)">{stamp_sub}</g></g>'
    )

    footer, _ = outline(medium, "Trota OS · edizione interna TestardStudios", 44, 366, h - 170, STEEL)
    scale = 6
    tx, ty = w - 240 * scale - 220, h - 162 * scale - 240   # bottom right, clear of the text
    body = (
        f'<defs><linearGradient id="bg-{uid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{GRAPHITE}"/><stop offset="1" stop-color="{CARBON}"/></linearGradient>'
        f'<linearGradient id="fish-{uid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="#22262B"/><stop offset="1" stop-color="#15181B"/></linearGradient>'
        f"{grid(uid, FROST, 0.02, 0.035)}</defs>"
        f'<rect width="{w}" height="{h}" fill="url(#bg-{uid})"/>'
        f'<rect width="{w}" height="{h}" fill="url(#minor-{uid})"/>'
        f'<rect width="{w}" height="{h}" fill="url(#major-{uid})"/>'
        f'<g transform="translate({tx:g} {ty:g}) scale({scale})" opacity="0.7">'
        f'{symbol(uid, f"url(#fish-{uid})", ORANGE)}'
        f'<path d="{BODY}" fill="none" stroke="#2F353C" stroke-width="0.6"/></g>'
        f"{line1}{line2}{note}{stamp}{footer}"
    )
    return svg(w, h, body, title="Trota OS internal edition wallpaper")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--font-dir", type=Path, default=Path("/usr/share/fonts/opentype/inter"))
    args = ap.parse_args(argv)
    OUT.write_text(wallpaper(args.font_dir))
    print(OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
