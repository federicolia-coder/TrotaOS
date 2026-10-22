#!/bin/sh
# Render the Trota OS artwork to PNG.  Usage: branding/render.sh OUTDIR
# Requires: python3, rsvg-convert (librsvg2-bin).  Used by debian/rules.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:?usage: render.sh OUTDIR}"
PY="${PYTHON:-python3}"
mkdir -p "$OUT/wallpapers" "$OUT/plymouth/trota" "$OUT/grub/trota" "$OUT/pixmaps" "$OUT/icons"

"$PY" "$HERE/generate.py" --check

for w in forge steel ingot; do
    rsvg-convert -w 3840 -h 2160 "$HERE/wallpapers/trota-$w.svg" -o "$OUT/wallpapers/trota-$w.png"
done

rsvg-convert -w 1920 -h 1080 "$HERE/themes/grub/trota/background.svg" -o "$OUT/grub/trota/background.png"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
"$PY" "$HERE/generate.py" --plymouth-frames "$tmp"
for f in "$tmp"/*.svg; do
    rsvg-convert "$f" -o "$OUT/plymouth/trota/$(basename "${f%.svg}").png"
done
rsvg-convert -w 420 "$HERE/logo/trota-logo-dark.svg" -o "$OUT/plymouth/trota/watermark.png"

# Logos for GDM, the Welcome app and documentation.
rsvg-convert -h 64 "$HERE/logo/trota-logo-dark.svg" -o "$OUT/pixmaps/trota-logo-gdm.png"
rsvg-convert -w 256 "$HERE/logo/trota-symbol.svg" -o "$OUT/pixmaps/trota-symbol-256.png"
for s in 16 24 32 48 64 128 256 512; do
    mkdir -p "$OUT/icons/${s}x${s}"
    for i in "$HERE"/icons/*.svg; do
        rsvg-convert -w "$s" -h "$s" "$i" -o "$OUT/icons/${s}x${s}/$(basename "${i%.svg}").png"
    done
done
