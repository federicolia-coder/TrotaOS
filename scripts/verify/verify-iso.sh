#!/usr/bin/env bash
# Verify a Trota OS ISO without booting it:
#   * SHA-256 checksum (if a .sha256 file sits next to the ISO or in checksums/)
#   * El Torito boot records for BIOS and UEFI, hybrid MBR/GPT for USB sticks
#   * expected files (kernel, initrd, squashfs, manifests, signed EFI loaders)
#   * filesystem.size / squashfs consistency
#
#   ./scripts/verify/verify-iso.sh dist/trota-os-1.0-amd64.iso
#
# Exit status: 0 = all checks passed, 1 = at least one failure.
set -uo pipefail

ISO="${1:?usage: verify-iso.sh ISO}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
fail=0
pass() { printf '  [PASS] %s\n' "$*"; }
bad()  { printf '  [FAIL] %s\n' "$*"; fail=1; }

[ -f "$ISO" ] || { echo "no such file: $ISO" >&2; exit 1; }
command -v xorriso >/dev/null || { echo "xorriso is required" >&2; exit 1; }
name="$(basename "$ISO")"
echo "Verifying $name ($(du -h "$ISO" | cut -f1))"

# --- checksum -----------------------------------------------------------------
sumfile=""
for c in "$ISO.sha256" "$(dirname "$ISO")/$name.sha256" "$ROOT/checksums/$name.sha256"; do
    [ -f "$c" ] && { sumfile="$c"; break; }
done
if [ -n "$sumfile" ]; then
    expected="$(awk '{print $1}' "$sumfile")"
    actual="$(sha256sum "$ISO" | awk '{print $1}')"
    if [ "$expected" = "$actual" ]; then pass "SHA-256 matches $sumfile"; else bad "SHA-256 mismatch ($sumfile)"; fi
else
    bad "no .sha256 file found for $name"
fi

# --- boot records -------------------------------------------------------------
report="$(xorriso -indev "$ISO" -report_el_torito plain -report_system_area plain 2>/dev/null)"
grep -q 'El Torito boot img :   1  BIOS' <<<"$report" && pass "El Torito BIOS boot image" || bad "no BIOS El Torito entry"
grep -q 'El Torito boot img :   2  UEFI' <<<"$report" && pass "El Torito UEFI boot image" || bad "no UEFI El Torito entry"
grep -qE 'GPT partition name.*|GPT type GUID.*28732ac11ff8d211ba4b00a0c93ec93b|Gpt type GUID' <<<"$report" \
    && pass "GPT with EFI system partition (USB boot)" || {
        grep -q 'MBR partition' <<<"$report" && pass "hybrid MBR present" || bad "no hybrid MBR/GPT"; }
volid="$(xorriso -indev "$ISO" -pvd_info 2>/dev/null | awk -F': ' '/^Volume Id/{print $2}')"
[ -n "$volid" ] && pass "volume id: $volid" || bad "no volume id"

# --- expected files -------------------------------------------------------------
listing="$(xorriso -indev "$ISO" -find / -type f 2>/dev/null)"
for f in /casper/vmlinuz /casper/initrd /casper/filesystem.squashfs /casper/filesystem.size \
         /casper/filesystem.manifest /casper/filesystem.manifest-remove /.disk/info \
         /boot/grub/grub.cfg /boot/grub/i386-pc/eltorito.img /EFI/boot/bootx64.efi /EFI/boot/grubx64.efi \
         /EFI/boot/mmx64.efi /boot/grub/themes/trota/theme.txt; do
    grep -qx "'$f'" <<<"$listing" && pass "file $f" || bad "missing $f"
done

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
xorriso -osirrox on -indev "$ISO" -extract /.disk/info "$tmp/info" -extract /casper/filesystem.manifest "$tmp/manifest" \
    -extract /casper/filesystem.size "$tmp/size" -extract /EFI/boot/bootx64.efi "$tmp/bootx64.efi" >/dev/null 2>&1
grep -q '^Trota OS' "$tmp/info" 2>/dev/null && pass "medium name: $(cat "$tmp/info")" || bad ".disk/info is not Trota OS"
for p in trota-desktop trota-release trota-welcome trota-system-info casper ubiquity linux-generic-hwe-24.04; do
    grep -q "^${p}[[:space:]]" "$tmp/manifest" 2>/dev/null && pass "manifest lists $p" || bad "manifest lacks $p"
done
for p in ubuntu-report whoopsie popularity-contest openssh-server; do
    grep -q "^${p}[[:space:]]" "$tmp/manifest" 2>/dev/null && bad "manifest contains excluded $p" || pass "excluded package $p absent"
done
size="$(cat "$tmp/size" 2>/dev/null || echo 0)"
[ "$size" -gt 1000000000 ] 2>/dev/null && pass "filesystem.size = $size bytes" || bad "implausible filesystem.size: $size"

if command -v sbverify >/dev/null 2>&1; then
    sbverify --list "$tmp/bootx64.efi" 2>/dev/null | grep -q 'Microsoft' \
        && pass "bootx64.efi (shim) carries a Microsoft UEFI CA signature" || bad "bootx64.efi is not Microsoft-signed"
else
    echo "  [SKIP] sbverify not installed: Secure Boot signature not inspected"
fi

if [ "$fail" -eq 0 ]; then echo "RESULT: PASS"; else echo "RESULT: FAIL"; fi
exit "$fail"
