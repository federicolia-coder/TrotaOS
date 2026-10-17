#!/usr/bin/env bash
# Build a Trota OS disk image, ready to boot (no installer):
#
#   sudo ./scripts/build/build-image.sh server   # servers, edge devices, VMs
#   sudo ./scripts/build/build-image.sh cloud    # public and private clouds
#   sudo ./scripts/build/build-image.sh kiosk    # kiosks, totems, digital signage
#
# Output in dist/: trota-os-<edition>-<version>-amd64.qcow2 (VMs and clouds)
# and .img.xz (raw disk, to write to a disk or USB drive), with .sha256.
# The image boots with BIOS and UEFI (Secure Boot) and is configured on first
# boot by cloud-init. Method and editions: docs/editions.md.

. "$(dirname "$0")/lib.sh"

EDITION="${1:-}"
case "$EDITION" in
    server) KERNEL=linux-image-generic-hwe-24.04 ;;   # firmware for real hardware
    cloud)  KERNEL=linux-image-virtual-hwe-24.04 ;;   # smaller, virtual hardware only
    kiosk)  KERNEL=linux-image-generic-hwe-24.04 ;;   # real screens and GPUs
    *) die "usage: build-image.sh server|cloud|kiosk" ;;
esac

WORK="$BUILD/image-$EDITION"
ROOT="$WORK/root"
MNT="$WORK/mnt"
RAW="$WORK/disk.img"
CACHE="$BUILD/cache"
PKG_DIR="$BUILD/packages"
NAME="trota-os-$EDITION-$TROTA_VERSION-$TROTA_ARCH"
SIZE="${TROTA_IMAGE_SIZE:-4G}"
M="$TROTA_ROOT/packages/manifest"
LOOP=""

cleanup() {
    [ -d "$MNT" ] && chroot_umount "$MNT" 2>/dev/null || true
    for m in "$MNT/boot/efi" "$MNT"; do mountpoint -q "$m" && umount "$m"; done
    [ -d "$ROOT" ] && chroot_umount "$ROOT" || true
    if [ -n "$LOOP" ]; then partx -d "$LOOP" 2>/dev/null || true; losetup -d "$LOOP" || true; LOOP=""; fi
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
build_root() {
    local tarball="$CACHE/bootstrap-${TROTA_BASE_SUITE}-${TROTA_ARCH}.tar"
    [ -d "$WORK" ] && safe_rm "$WORK"
    mkdir -p "$ROOT" "$CACHE"
    if [ -f "$tarball" ]; then
        log "root: cached $(basename "$tarball")"
        tar -C "$ROOT" -xpf "$tarball"
    else
        log "root: debootstrap $TROTA_BASE_SUITE"
        debootstrap --arch="$TROTA_ARCH" --components="${TROTA_COMPONENTS// /,}" \
            "$TROTA_BASE_SUITE" "$ROOT" "$TROTA_MIRROR"
        tar -C "$ROOT" -cpf "$tarball.partial" . && mv "$tarball.partial" "$tarball"
    fi
    chroot_mount "$ROOT"
    write_apt_sources "$ROOT"
    echo "trota-$EDITION" > "$ROOT/etc/hostname"
    printf '127.0.0.1 localhost\n127.0.1.1 trota-%s\n::1 localhost ip6-localhost ip6-loopback\n' "$EDITION" > "$ROOT/etc/hosts"
    prepare_chroot "$ROOT" "$M/server-excluded.list"
    [ "$EDITION" != cloud ] && install -D -m 644 "$TROTA_ROOT/packaging/files/settings/trota-firmware-exclude" \
        "$ROOT/etc/dpkg/dpkg.cfg.d/trota-firmware-exclude"
    # Installed systems keep their kernel and boot loader updated through
    # these debconf answers (no interactive question during upgrades).
    in_chroot "$ROOT" sh -c 'echo "grub-pc grub-pc/install_devices_empty boolean true" | debconf-set-selections'

    in_chroot "$ROOT" apt-get update
    in_chroot "$ROOT" apt-get -y full-upgrade
    log "packages: $EDITION ($KERNEL)"
    local lists=("$M/server.list")
    [ "$EDITION" = kiosk ] && lists+=("$M/kiosk.list")
    # shellcheck disable=SC2046
    in_chroot "$ROOT" apt-get -y --no-install-recommends install "$KERNEL" $(read_list "${lists[@]}" | awk '{print $1}')
    [ "$EDITION" = cloud ] && in_chroot "$ROOT" apt-get -y --no-install-recommends install qemu-guest-agent
    in_chroot "$ROOT" pro config set apt_news=false

    log "packages: Trota OS"
    rm -rf "$ROOT/tmp/trota-debs" && mkdir -p "$ROOT/tmp/trota-debs"
    cp "$PKG_DIR"/trota-release_*.deb "$PKG_DIR"/trota-server-settings_*.deb "$ROOT/tmp/trota-debs/"
    in_chroot "$ROOT" sh -c 'apt-get -y --no-install-recommends install /tmp/trota-debs/*.deb'
    if [ "$EDITION" = kiosk ]; then
        # Firefox comes from Mozilla's repository, configured by trota-software-sources.
        cp "$PKG_DIR"/trota-software-sources_*.deb "$ROOT/tmp/trota-debs/"
        in_chroot "$ROOT" sh -c 'apt-get -y --no-install-recommends install /tmp/trota-debs/trota-software-sources_*.deb'
        in_chroot "$ROOT" apt-get update
        cp "$PKG_DIR"/trota-kiosk_*.deb "$ROOT/tmp/trota-debs/"
        in_chroot "$ROOT" sh -c 'apt-get -y --no-install-recommends install /tmp/trota-debs/trota-kiosk_*.deb firefox-l10n-it'
        case "$(in_chroot "$ROOT" dpkg-query -W -f='${Version}' firefox)" in
            *snap*) die "firefox is Ubuntu's snap transitional package" ;;
        esac
        in_chroot "$ROOT" systemctl set-default graphical.target
        [ "$(in_chroot "$ROOT" systemctl is-enabled trota-kiosk.service)" = enabled ] || die "trota-kiosk.service not enabled"
    fi
    rm -rf "$ROOT/tmp/trota-debs"

    local bad
    bad="$(read_list "$M/server-excluded.list" | awk '{print $1}' | while read -r p; do
        { in_chroot "$ROOT" dpkg-query -W -f='${db:Status-Abbrev} ${Package}\n' "$p" 2>/dev/null || true; } \
            | awk '/^ii/{print $2}'
    done)"
    [ -z "$bad" ] || die "excluded packages installed: $bad"
}

configure_root() {
    log "configure: identity, cloud-init, SSH, firewall, boot"
    # Identity (as in the desktop image, see build-iso.sh)
    chmod -x "$ROOT/etc/update-motd.d/00-header" "$ROOT/etc/update-motd.d/10-help-text"
    [ -f "$ROOT/etc/update-motd.d/91-contract-ua-esm-status" ] && chmod -x "$ROOT/etc/update-motd.d/91-contract-ua-esm-status"
    printf 'DISTRIB_ID=Trota\nDISTRIB_RELEASE=%s\nDISTRIB_CODENAME=%s\nDISTRIB_DESCRIPTION="%s %s %s"\n' \
        "$TROTA_VERSION" "$TROTA_BASE_SUITE" "$TROTA_NAME" "${EDITION^}" "$TROTA_VERSION" > "$ROOT/etc/lsb-release"
    [ "$(in_chroot "$ROOT" lsb_release -is)" = Trota ] || die "lsb_release does not report Trota"
    in_chroot "$ROOT" python3 -c '
import apt_pkg
apt_pkg.init_config()
assert "Ubuntu:${distro_codename}-security" in apt_pkg.config.value_list("Unattended-Upgrade::Allowed-Origins")
' || die "unattended-upgrades does not allow the security archive"

    # cloud-init: Trota OS default user. On "server" the image also boots
    # without any cloud-init data source (bare metal, edge devices): the user
    # "trota" then has the password "trota", to be changed at the first login
    # on the console (SSH accepts keys only).
    local lock=true
    [ "$EDITION" != cloud ] && lock=false
    cat > "$ROOT/etc/cloud/cloud.cfg.d/90-trota.cfg" <<EOF
# Trota OS $EDITION image defaults (scripts/build/build-image.sh).
system_info:
  distro: ubuntu
  default_user:
    name: trota
    gecos: Trota OS
    groups: [adm, sudo, systemd-journal]
    sudo: ["ALL=(ALL) ALL"]
    shell: /bin/bash
    lock_passwd: $lock
EOF
    if [ "$EDITION" != cloud ]; then
        # No data source: cloud-init still runs (growpart, SSH host keys).
        printf 'datasource_list: [ NoCloud, ConfigDrive, OpenStack, Ec2, Azure, GCE, Oracle, None ]\n' \
            > "$ROOT/etc/cloud/cloud.cfg.d/91-trota-datasources.cfg"
        in_chroot "$ROOT" useradd -m -s /bin/bash -c "Trota OS" -G adm,sudo,systemd-journal trota
        echo 'trota:trota' | in_chroot "$ROOT" chpasswd
        in_chroot "$ROOT" chage -d 0 trota
    fi

    # Firewall on, SSH allowed.
    in_chroot "$ROOT" ufw allow OpenSSH >/dev/null
    sed -i 's/^ENABLED=.*/ENABLED=yes/' "$ROOT/etc/ufw/ufw.conf"

    # Boot: serial and screen console, short menu.
    cat > "$ROOT/etc/default/grub.d/60-trota-image.cfg" <<'EOF'
# Trota OS disk image: console on screen and on the first serial port.
GRUB_TIMEOUT=2
GRUB_TIMEOUT_STYLE=menu
GRUB_CMDLINE_LINUX_DEFAULT=""
GRUB_CMDLINE_LINUX="console=tty1 console=ttyS0,115200n8"
GRUB_TERMINAL="console serial"
GRUB_SERIAL_COMMAND="serial --speed=115200"
EOF

    # Image hygiene (as in the desktop image).
    rm -f "$ROOT/usr/sbin/policy-rc.d" "$ROOT/etc/apt/preferences.d/zz-trota-build-excluded.pref"
    in_chroot "$ROOT" apt-get -y autoremove --purge
    in_chroot "$ROOT" apt-get clean
    : > "$ROOT/etc/machine-id"
    rm -f "$ROOT/var/lib/dbus/machine-id" "$ROOT"/etc/ssh/ssh_host_*_key*
    rm -rf "$ROOT"/tmp/* "$ROOT"/var/tmp/* "$ROOT/root/.cache" "$ROOT/root/.bash_history"
    find "$ROOT/var/log" -type f -exec truncate -s 0 {} +
    in_chroot "$ROOT" dpkg-query -W --showformat='${Package}\t${Version}\n' > "$WORK/manifest"
    chroot_umount "$ROOT"
}

# GPT disk: BIOS boot partition, EFI system partition, root (grown on first boot).
make_disk() {
    log "disk: $SIZE raw image"
    rm -f "$RAW"
    truncate -s "$SIZE" "$RAW"
    printf 'label: gpt\n,1MiB,21686148-6449-6E6F-744E-656564454649,name="bios"\n,255MiB,U,name="ESP"\n,,L,name="root"\n' \
        | sfdisk -q "$RAW"
    LOOP="$(losetup -f --show "$RAW")"
    partx -a "$LOOP"
    mkfs.vfat -F 32 -n TROTA-ESP "${LOOP}p2" >/dev/null
    mkfs.ext4 -q -L trota-root "${LOOP}p3"
    mkdir -p "$MNT"
    mount "${LOOP}p3" "$MNT"
    rsync -aHAX "$ROOT"/ "$MNT"/
    mkdir -p "$MNT/boot/efi"
    mount "${LOOP}p2" "$MNT/boot/efi"
    printf 'UUID=%s / ext4 defaults,discard,errors=remount-ro 0 1\nUUID=%s /boot/efi vfat umask=0077 0 1\n' \
        "$(blkid -s UUID -o value "${LOOP}p3")" "$(blkid -s UUID -o value "${LOOP}p2")" > "$MNT/etc/fstab"

    log "disk: boot loader (BIOS + UEFI with the signed shim)"
    chroot_mount "$MNT"
    in_chroot "$MNT" grub-install --target=i386-pc "$LOOP"
    in_chroot "$MNT" grub-install --target=x86_64-efi --efi-directory=/boot/efi --uefi-secure-boot --no-nvram
    # Fallback path, used by firmware without a boot entry (new disks, clouds).
    in_chroot "$MNT" grub-install --target=x86_64-efi --efi-directory=/boot/efi --uefi-secure-boot --no-nvram --removable
    in_chroot "$MNT" update-initramfs -u -k all
    in_chroot "$MNT" update-grub
    grep -q 'menuentry .Trota OS' "$MNT/boot/grub/grub.cfg" || die "no Trota OS entry in grub.cfg"
    chroot_umount "$MNT"
    umount "$MNT/boot/efi" "$MNT"
    partx -d "$LOOP"; losetup -d "$LOOP"; LOOP=""
}

export_image() {
    mkdir -p "$DIST" "$CHECKSUMS"
    log "export: qcow2 and img.xz"
    rm -f "$DIST/$NAME.qcow2" "$DIST/$NAME.img.xz"
    qemu-img convert -c -O qcow2 "$RAW" "$DIST/$NAME.qcow2"
    xz -T0 -6 -c "$RAW" > "$DIST/$NAME.img.xz"
    cp "$WORK/manifest" "$DIST/$NAME.manifest"
    (cd "$DIST" && sha256sum "$NAME.qcow2" "$NAME.img.xz") > "$CHECKSUMS/$NAME.sha256"
    cp "$CHECKSUMS/$NAME.sha256" "$DIST/"
    ls -l "$DIST/$NAME".* >&2
}

main() {
    require_root
    require_cmds debootstrap sfdisk losetup partx mkfs.vfat mkfs.ext4 blkid rsync qemu-img xz sha256sum
    ls "$PKG_DIR"/trota-server-settings_*.deb >/dev/null 2>&1 || die "no Trota OS packages: run scripts/build/build-packages.sh first"
    [ "$EDITION" != kiosk ] || ls "$PKG_DIR"/trota-kiosk_*.deb >/dev/null 2>&1 || die "no trota-kiosk package: run scripts/build/build-packages.sh"
    mkdir -p "$BUILD" "$LOGS"
    exec > >(tee -a "$LOGS/build-image-$EDITION-$(timestamp).log") 2>&1
    local t0=$SECONDS
    build_root
    configure_root
    make_disk
    export_image
    log "image $NAME done in $((SECONDS - t0))s"
}

main
