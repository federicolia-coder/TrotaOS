#!/usr/bin/env bash
# Build the Trota OS live/installable ISO from scratch.
#
#   sudo ./scripts/build/build-iso.sh            # all stages
#   sudo ./scripts/build/build-iso.sh iso        # only re-run one stage
#   sudo ./scripts/build/build-iso.sh clean      # remove build/chroot and build/iso
#
# Stages (in order): bootstrap packages trota customize iso checksum
# The method is documented in docs/building.md and docs/architecture.md.

. "$(dirname "$0")/lib.sh"

CHROOT="$BUILD/chroot"
ISO_DIR="$BUILD/iso"
CACHE="$BUILD/cache"
PKG_DIR="$BUILD/packages"
BUILD_DATE="$(date -u +%Y%m%d)"
ISO_NAME="trota-os-${TROTA_VERSION}-${TROTA_ARCH}.iso"
ISO_FILE="$DIST/$ISO_NAME"
STAGES_ALL=(bootstrap packages trota customize iso checksum)

cleanup() { [ -d "$CHROOT" ] && chroot_umount "$CHROOT" || true; }

# Trota OS packages of the desktop image (the server ones go to build-image.sh).
desktop_debs() { find "$PKG_DIR" -maxdepth 1 -name '*.deb' ! -name 'trota-server-settings_*' ! -name 'trota-kiosk_*' ! -name 'trota-fleet-agent_*' | sort; }
trap cleanup EXIT

# ---------------------------------------------------------------------------
stage_bootstrap() {
    local tarball="$CACHE/bootstrap-${TROTA_BASE_SUITE}-${TROTA_ARCH}.tar"
    [ -d "$CHROOT" ] && safe_rm "$CHROOT"
    mkdir -p "$CHROOT" "$CACHE"
    if [ -f "$tarball" ]; then
        log "bootstrap: extracting cached $(basename "$tarball")"
        tar -C "$CHROOT" -xpf "$tarball"
    else
        log "bootstrap: debootstrap $TROTA_BASE_SUITE from $TROTA_MIRROR"
        debootstrap --arch="$TROTA_ARCH" --components="${TROTA_COMPONENTS// /,}" \
            "$TROTA_BASE_SUITE" "$CHROOT" "$TROTA_MIRROR"
        tar -C "$CHROOT" -cpf "$tarball.partial" . && mv "$tarball.partial" "$tarball"
    fi
}

# ---------------------------------------------------------------------------
stage_packages() {
    [ -d "$CHROOT/etc" ] || die "no chroot: run the bootstrap stage first"
    chroot_mount "$CHROOT"

    write_apt_sources "$CHROOT"
    echo "trota" > "$CHROOT/etc/hostname"
    printf '127.0.0.1 localhost\n127.0.1.1 trota\n::1 localhost ip6-localhost ip6-loopback\n' > "$CHROOT/etc/hosts"

    prepare_chroot "$CHROOT" "$TROTA_ROOT/packages/manifest/excluded.list"
    # Same dpkg filters as trota-desktop-settings, in place before the first
    # package is unpacked (data-centre firmware, Ubuntu wallpapers, login
    # services: see the files for details).
    local f
    for f in trota-firmware-exclude trota-desktop-exclude; do
        install -D -m 644 "$TROTA_ROOT/packaging/files/settings/$f" "$CHROOT/etc/dpkg/dpkg.cfg.d/$f"
    done
    in_chroot "$CHROOT" apt-get update
    in_chroot "$CHROOT" apt-get -y full-upgrade

    local m="$TROTA_ROOT/packages/manifest"
    log "packages: base system"
    # shellcheck disable=SC2046
    in_chroot "$CHROOT" apt-get -y install $(read_list "$m/base.list" | awk '{print $1}')
    log "packages: desktop, applications, tools, live session"
    # shellcheck disable=SC2046
    in_chroot "$CHROOT" apt-get -y install $(read_list "$m/desktop.list" "$m/applications.list" "$m/tools.list" "$m/live.list" | awk '{print $1}')

    # Privacy: no Canonical "APT news" fetched in the background (docs/privacy.md).
    # Here, before trota-release changes the system ID: pro acts only on Ubuntu.
    in_chroot "$CHROOT" pro config set apt_news=false
}

# ---------------------------------------------------------------------------
stage_trota() {
    ls "$PKG_DIR"/*.deb >/dev/null 2>&1 || die "no Trota OS packages in $PKG_DIR: run scripts/build/build-packages.sh first"
    chroot_mount "$CHROOT"
    local m="$TROTA_ROOT/packages/manifest"
    prepare_chroot "$CHROOT" "$TROTA_ROOT/packages/manifest/excluded.list"
    log "trota: Trota OS packages from $PKG_DIR"
    rm -rf "$CHROOT/tmp/trota-debs" && mkdir -p "$CHROOT/tmp/trota-debs"
    desktop_debs | xargs cp -t "$CHROOT/tmp/trota-debs/"
    in_chroot "$CHROOT" sh -c 'apt-get -y install --reinstall /tmp/trota-debs/*.deb'
    rm -rf "$CHROOT/tmp/trota-debs"

    # Firefox: the .deb from Mozilla's APT repository, configured by
    # trota-software-sources (Ubuntu's "firefox" only installs the snap).
    log "trota: Firefox from packages.mozilla.org"
    in_chroot "$CHROOT" apt-get update
    in_chroot "$CHROOT" apt-get -y install firefox firefox-l10n-it
    local ffver
    ffver="$(in_chroot "$CHROOT" dpkg-query -W -f='${Version}' firefox)"
    case "$ffver" in *snap*) die "firefox $ffver is Ubuntu's snap transitional package" ;; esac
    [ -x "$CHROOT/usr/lib/firefox/firefox" ] || die "firefox binary missing"
    log "trota: firefox $ffver"
    in_chroot "$CHROOT" flatpak remotes --system --columns=name | grep -qx flathub || die "Flathub remote missing"

    # Ubiquity crashes at the start of the installation without a slideshow
    # (docs/testing.md): make sure ours is installed.
    [ -f "$CHROOT/usr/share/ubiquity-slideshow/slides/index.html" ] || die "installer slideshow missing"

    # Fail the build if an excluded package slipped in anyway.
    local bad
    bad="$(read_list "$m/excluded.list" | awk '{print $1}' | while read -r p; do
        { in_chroot "$CHROOT" dpkg-query -W -f='${db:Status-Abbrev} ${Package}\n' "$p" 2>/dev/null || true; } \
            | awk '/^ii/{print $2}'
    done)"
    [ -z "$bad" ] || die "excluded packages installed: $bad"
    # The dpkg firmware filter must have kept the data-centre firmware out.
    local d
    for d in mellanox mrvl/prestera netronome qed; do
        [ -z "$(find "$CHROOT/usr/lib/firmware/$d" -type f 2>/dev/null | head -1)" ] \
            || die "firmware filter not applied: usr/lib/firmware/$d"
    done
}

# The image identifies itself as Trota OS (ID=trota) with the base codename;
# the tools that used to rely on ID=ubuntu must keep working.
check_identity() {
    [ "$(in_chroot "$CHROOT" lsb_release -is)" = Trota ] || die "lsb_release does not report Trota"
    [ "$(in_chroot "$CHROOT" lsb_release -cs)" = "$TROTA_BASE_SUITE" ] || die "lsb_release codename is not $TROTA_BASE_SUITE"
    # Security updates must still be installed automatically from the base archive.
    in_chroot "$CHROOT" python3 -c '
import apt_pkg
apt_pkg.init_config()
allowed = apt_pkg.config.value_list("Unattended-Upgrade::Allowed-Origins")
assert "Ubuntu:${distro_codename}-security" in allowed, allowed
' || die "unattended-upgrades does not allow the security archive"
    # "Software & Updates" (python-apt) must find the templates for Trota.
    in_chroot "$CHROOT" python3 -c '
from aptsources.distro import get_distro
from aptsources.sourceslist import SourcesList
d = get_distro()
d.get_sources(SourcesList())
assert d.id == "Trota" and d.source_template, d
print("python-apt:", d.id, d.codename, d.source_template.description)
' || die "python-apt cannot handle the Trota distribution"
}

# ---------------------------------------------------------------------------
stage_customize() {
    chroot_mount "$CHROOT"

    # Live session identity (casper). BUILD_SYSTEM must stay "Ubuntu": it
    # enables casper's Ubuntu integration scripts.
    cat > "$CHROOT/etc/casper.conf" <<EOF
# Trota OS live session configuration (casper)
export USERNAME="trota"
export USERFULLNAME="Trota OS live session user"
export HOST="trota"
export BUILD_SYSTEM="Ubuntu"
export FLAVOUR="Trota OS"
EOF

    printf 'LANG=en_US.UTF-8\n' > "$CHROOT/etc/default/locale"
    in_chroot "$CHROOT" locale-gen en_US.UTF-8 it_IT.UTF-8

    # Regenerate dconf and GSettings defaults shipped by trota-desktop-settings.
    # --strict: an unknown key or a wrong type in an override fails the build.
    in_chroot "$CHROOT" glib-compile-schemas --strict --dry-run /usr/share/glib-2.0/schemas
    in_chroot "$CHROOT" glib-compile-schemas /usr/share/glib-2.0/schemas
    in_chroot "$CHROOT" dconf update

    # Release upgrades to the next Ubuntu LTS are not offered automatically:
    # they are not validated for Trota OS yet (docs/architecture.md, ADR-007).
    sed -i 's/^Prompt=.*/Prompt=never/' "$CHROOT/etc/update-manager/release-upgrades"

    # Console banners (conffiles of base-files whose text does not change with
    # updates; lsb-release and the motd header are left untouched, see
    # docs/release-notes.md "Known issues").
    printf '%s %s \\n \\l\n\n' "$TROTA_NAME" "$TROTA_VERSION" > "$CHROOT/etc/issue"
    printf '%s %s\n' "$TROTA_NAME" "$TROTA_VERSION" > "$CHROOT/etc/issue.net"
    cat > "$CHROOT/etc/legal" <<EOF

$TROTA_NAME is published by $TROTA_PUBLISHER and based on Ubuntu. The programs
included with the system are free software; the exact distribution terms for
each program are described in the individual files in
/usr/share/doc/*/copyright.

$TROTA_NAME comes with ABSOLUTELY NO WARRANTY, to the extent permitted by
applicable law.

EOF

    # Login banner: the Trota OS one (05-trota-os) instead of Ubuntu's header,
    # Landscape/Ubuntu Pro links and ESM advertising. update-motd runs only
    # executable scripts; dpkg keeps the mode until Ubuntu changes these files.
    chmod -x "$CHROOT/etc/update-motd.d/00-header" "$CHROOT/etc/update-motd.d/10-help-text" \
        "$CHROOT/etc/update-motd.d/91-contract-ua-esm-status"

    # /etc/lsb-release (base-files conffile, read by a few older programs) with
    # the same identity as os-release; the codename stays the base one.
    printf 'DISTRIB_ID=Trota\nDISTRIB_RELEASE=%s\nDISTRIB_CODENAME=%s\nDISTRIB_DESCRIPTION="%s %s"\n' \
        "$TROTA_VERSION" "$TROTA_BASE_SUITE" "$TROTA_NAME" "$TROTA_VERSION" > "$CHROOT/etc/lsb-release"
    check_identity

    log "customize: initramfs with casper and the Trota OS boot splash"
    in_chroot "$CHROOT" update-initramfs -u -k all
    local initrd
    initrd="$(ls -1 "$CHROOT"/boot/initrd.img-* | sort -V | tail -1)"
    in_chroot "$CHROOT" lsinitramfs "${initrd#"$CHROOT"}" > "$BUILD/initrd-contents.txt"
    for f in usr/share/plymouth/themes/trota/trota.plymouth usr/lib/x86_64-linux-gnu/plymouth/two-step.so \
             scripts/casper; do
        grep -q "^$f\$" "$BUILD/initrd-contents.txt" || die "initrd is missing $f"
    done

    # Undo build-time-only configuration.
    rm -f "$CHROOT/usr/sbin/policy-rc.d" "$CHROOT/etc/apt/preferences.d/zz-trota-build-excluded.pref"

    # Image hygiene: no machine identity, caches or logs from the build host.
    in_chroot "$CHROOT" apt-get -y autoremove --purge
    in_chroot "$CHROOT" apt-get clean
    : > "$CHROOT/etc/machine-id"
    rm -f "$CHROOT/var/lib/dbus/machine-id"
    rm -rf "$CHROOT"/tmp/* "$CHROOT"/var/tmp/* "$CHROOT/root/.cache" "$CHROOT/root/.bash_history"
    find "$CHROOT/var/log" -type f \( -name '*.gz' -o -name '*.[0-9]' \) -delete
    find "$CHROOT/var/log" -type f -exec truncate -s 0 {} +
    rm -f "$CHROOT"/etc/ssh/ssh_host_*_key*
}

# Small APT archive on the medium with the Trota OS packages. Ubiquity always
# runs "apt-cdrom add" on the medium (it forces OVERRIDE_BASE_INSTALLABLE), and
# aborts the installation if no package index is found (seen in the VM test).
# During the installation ubiquity allows this unsigned source; afterwards the
# cdrom entry is disabled in the installed system.
make_cdrom_archive() {
    local dist="dists/$TROTA_BASE_SUITE" comp="main/binary-$TROTA_ARCH"
    mkdir -p "$ISO_DIR/pool/main/t/trota-os" "$ISO_DIR/$dist/$comp"
    desktop_debs | xargs cp -t "$ISO_DIR/pool/main/t/trota-os/"
    (cd "$ISO_DIR" && dpkg-scanpackages --arch "$TROTA_ARCH" pool/main /dev/null 2>/dev/null) \
        > "$ISO_DIR/$dist/$comp/Packages"
    gzip -9nkf "$ISO_DIR/$dist/$comp/Packages"
    printf 'Archive: %s\nComponent: main\nOrigin: Trota OS\nLabel: Trota OS\nArchitecture: %s\n' \
        "$TROTA_BASE_SUITE" "$TROTA_ARCH" > "$ISO_DIR/$dist/$comp/Release"
    {
        printf 'Origin: Trota OS\nLabel: Trota OS\nSuite: %s\nCodename: %s\nVersion: %s\n' \
            "$TROTA_BASE_SUITE" "$TROTA_BASE_SUITE" "$TROTA_VERSION"
        printf 'Date: %s\nArchitectures: %s\nComponents: main\n' "$(LC_ALL=C date -Ru)" "$TROTA_ARCH"
        printf 'Description: %s %s installation medium\n' "$TROTA_NAME" "$TROTA_VERSION"
        local sum f
        for sum in md5sum sha256sum; do
            [ "$sum" = md5sum ] && echo "MD5Sum:" || echo "SHA256:"
            for f in "$comp/Packages" "$comp/Packages.gz" "$comp/Release"; do
                printf ' %s %16d %s\n' "$(cd "$ISO_DIR/$dist" && $sum "$f" | cut -d' ' -f1)" \
                    "$(stat -c %s "$ISO_DIR/$dist/$f")" "$f"
            done
        done
    } > "$ISO_DIR/$dist/Release"
    log "iso: APT archive on the medium with $(grep -c '^Package:' "$ISO_DIR/$dist/$comp/Packages") packages"
}

# ---------------------------------------------------------------------------
stage_iso() {
    chroot_umount "$CHROOT"
    [ -d "$ISO_DIR" ] && safe_rm "$ISO_DIR"
    mkdir -p "$ISO_DIR"/{casper,.disk,boot/grub/i386-pc,boot/grub/x86_64-efi,boot/grub/fonts,EFI/boot} "$DIST"

    local kver
    kver="$(basename "$(ls -1 "$CHROOT"/boot/vmlinuz-* | sort -V | tail -1)" | sed 's/^vmlinuz-//')"
    log "iso: kernel $kver"
    cp "$CHROOT/boot/vmlinuz-$kver" "$ISO_DIR/casper/vmlinuz"
    cp "$CHROOT/boot/initrd.img-$kver" "$ISO_DIR/casper/initrd"

    # Manifests: ubiquity removes manifest-remove packages from the target.
    chroot "$CHROOT" dpkg-query -W --showformat='${Package}\t${Version}\n' > "$ISO_DIR/casper/filesystem.manifest"
    chroot "$CHROOT" dpkg-query -W --showformat='${Package}\n' \
        | grep -x -E 'casper|lupin-casper|ubiquity.*|gparted' > "$ISO_DIR/casper/filesystem.manifest-remove" || true
    du -sx --block-size=1 "$CHROOT" | cut -f1 > "$ISO_DIR/casper/filesystem.size"

    log "iso: squashfs ($TROTA_SQUASHFS_COMP)"
    rm -f "$ISO_DIR/casper/filesystem.squashfs"
    # xz: 1 MiB blocks and the x86 BCJ filter make the image ~5% smaller.
    local sqopts=()
    [ "$TROTA_SQUASHFS_COMP" = xz ] && sqopts=(-b 1M -Xbcj x86)
    mksquashfs "$CHROOT" "$ISO_DIR/casper/filesystem.squashfs" -noappend -comp "$TROTA_SQUASHFS_COMP" "${sqopts[@]}" \
        -wildcards -e 'proc/*' 'sys/*' 'dev/*' 'run/*' 'tmp/*' 'var/tmp/*' 'var/cache/apt/archives/*.deb'

    # Medium identity, read by casper and ubiquity (RELEASE name in the UI).
    # Ubiquity reads "<name> <version> ...", with "-" for the spaces of the name.
    printf '%s %s "%s" - Release %s (%s)\n' "${TROTA_NAME// /-}" "$TROTA_VERSION" "$TROTA_CODENAME" "$TROTA_ARCH" "$BUILD_DATE" > "$ISO_DIR/.disk/info"
    echo "full_cd/single" > "$ISO_DIR/.disk/cd_type"
    # No .disk/base_installable: the medium cannot install a base system with
    # debootstrap; ubiquity copies the squashfs (see make_cdrom_archive).
    echo "https://github.com/federicolia-coder/TrotaOS/blob/main/docs/release-notes.md" > "$ISO_DIR/.disk/release_notes_url"

    # --- GRUB: menu, theme and fonts --------------------------------------
    local cfgsrc="$TROTA_ROOT/packages/config/iso"
    sed -e "s/@VERSION@/$TROTA_VERSION/g" "$cfgsrc/grub.cfg" > "$ISO_DIR/boot/grub/grub.cfg"
    cp "$cfgsrc/loopback.cfg" "$ISO_DIR/boot/grub/loopback.cfg"
    cp -r "$CHROOT/usr/share/grub/themes/trota" "$ISO_DIR/boot/grub/themes-trota.tmp"
    mkdir -p "$ISO_DIR/boot/grub/themes" && mv "$ISO_DIR/boot/grub/themes-trota.tmp" "$ISO_DIR/boot/grub/themes/trota"
    cp "$CHROOT/usr/share/grub/unicode.pf2" "$ISO_DIR/boot/grub/fonts/unicode.pf2"
    [ -f "$CHROOT/boot/memtest86+x64.bin" ] && cp "$CHROOT/boot/memtest86+x64.bin" "$ISO_DIR/boot/"

    # --- BIOS: El Torito image + modules, hybrid MBR for USB sticks --------
    cp "$CHROOT"/usr/lib/grub/i386-pc/*.mod "$CHROOT"/usr/lib/grub/i386-pc/*.lst "$ISO_DIR/boot/grub/i386-pc/"
    chroot "$CHROOT" grub-mkimage -O i386-pc-eltorito -p /boot/grub -o /tmp/eltorito.img \
        biosdisk iso9660 part_msdos part_gpt
    mv "$CHROOT/tmp/eltorito.img" "$ISO_DIR/boot/grub/i386-pc/eltorito.img"

    # --- UEFI: Canonical-signed shim + GRUB, so Secure Boot keeps working ---
    cp "$CHROOT"/usr/lib/grub/x86_64-efi/*.mod "$CHROOT"/usr/lib/grub/x86_64-efi/*.lst "$ISO_DIR/boot/grub/x86_64-efi/"
    cp "$CHROOT/usr/lib/shim/shimx64.efi.signed.latest" "$ISO_DIR/EFI/boot/bootx64.efi" 2>/dev/null \
        || cp "$CHROOT/usr/lib/shim/shimx64.efi.signed" "$ISO_DIR/EFI/boot/bootx64.efi"
    cp "$CHROOT/usr/lib/shim/mmx64.efi" "$ISO_DIR/EFI/boot/mmx64.efi"
    cp "$CHROOT/usr/lib/grub/x86_64-efi-signed/gcdx64.efi.signed" "$ISO_DIR/EFI/boot/grubx64.efi"

    make_cdrom_archive

    # Checksums of the medium, verified by casper-md5check at live boot.
    # eltorito.img is excluded: xorriso patches its boot-info-table later.
    (cd "$ISO_DIR" && find . -type f ! -name md5sum.txt ! -name boot.catalog ! -name eltorito.img -print0 | sort -z \
        | xargs -0 md5sum > md5sum.txt)

    local efi_img="$BUILD/efi.img"
    rm -f "$efi_img"
    mkfs.msdos -C -n TROTA_EFI "$efi_img" 10240 >/dev/null
    mmd -i "$efi_img" ::/EFI ::/EFI/boot
    mcopy -i "$efi_img" "$ISO_DIR"/EFI/boot/*.efi ::/EFI/boot/

    log "iso: xorriso -> $ISO_FILE"
    rm -f "$ISO_FILE"
    xorriso -as mkisofs -r -J -joliet-long -V "$TROTA_ISO_VOLID" -o "$ISO_FILE" \
        --grub2-mbr "$CHROOT/usr/lib/grub/i386-pc/boot_hybrid.img" \
        -partition_offset 16 --mbr-force-bootable \
        -append_partition 2 28732ac11ff8d211ba4b00a0c93ec93b "$efi_img" \
        -appended_part_as_gpt \
        -iso_mbr_part_type a2a0d0ebe5b9334487c068b6b72699c7 \
        -c /boot.catalog \
        -b /boot/grub/i386-pc/eltorito.img -no-emul-boot -boot-load-size 4 -boot-info-table --grub2-boot-info \
        -eltorito-alt-boot \
        -e '--interval:appended_partition_2:::' -no-emul-boot \
        "$ISO_DIR"
    cp "$ISO_DIR/casper/filesystem.manifest" "$DIST/${ISO_NAME%.iso}.manifest"
}

# ---------------------------------------------------------------------------
stage_checksum() {
    [ -f "$ISO_FILE" ] || die "no ISO at $ISO_FILE"
    mkdir -p "$CHECKSUMS"
    (cd "$DIST" && sha256sum "$ISO_NAME") > "$CHECKSUMS/${ISO_NAME}.sha256"
    cp "$CHECKSUMS/${ISO_NAME}.sha256" "$DIST/"
    log "checksum: $(cat "$CHECKSUMS/${ISO_NAME}.sha256")"
    "$TROTA_ROOT/scripts/verify/verify-iso.sh" "$ISO_FILE"
}

stage_clean() {
    cleanup
    for d in "$CHROOT" "$ISO_DIR"; do [ -e "$d" ] && safe_rm "$d"; done
    log "clean: removed chroot and ISO tree (cache and packages kept)"
}

# ---------------------------------------------------------------------------
main() {
    require_root
    require_cmds debootstrap mksquashfs unsquashfs xorriso mkfs.msdos mmd mcopy sha256sum findmnt
    mkdir -p "$BUILD" "$LOGS"
    local stages=("$@")
    [ ${#stages[@]} -gt 0 ] || stages=("${STAGES_ALL[@]}")
    local logfile
    logfile="$LOGS/build-iso-$(timestamp).log"
    log "Trota OS $TROTA_VERSION ($TROTA_BASE_SUITE/$TROTA_ARCH) — stages: ${stages[*]} — log: $logfile"
    exec > >(tee -a "$logfile") 2>&1
    for s in "${stages[@]}"; do
        declare -F "stage_$s" >/dev/null || die "unknown stage: $s (valid: ${STAGES_ALL[*]} clean)"
        local t0=$SECONDS
        log "=== stage $s ==="
        "stage_$s"
        log "=== stage $s done in $((SECONDS - t0))s ==="
    done
}

main "$@"
