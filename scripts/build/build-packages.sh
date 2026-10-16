#!/usr/bin/env bash
# Build the Trota OS .deb packages inside a clean Ubuntu chroot (same suite
# as the image), so the result does not depend on the build host.
#
#   sudo ./scripts/build/build-packages.sh
#
# Output: build/packages/*.deb (+ .buildinfo/.changes), log in logs/.

. "$(dirname "$0")/lib.sh"

PKG_CHROOT="$BUILD/pkg-chroot"
CACHE="$BUILD/cache"
PKG_DIR="$BUILD/packages"
SRC_NAME="trota-os"

cleanup() { [ -d "$PKG_CHROOT" ] && chroot_umount "$PKG_CHROOT" || true; }
trap cleanup EXIT

main() {
    require_root
    require_cmds debootstrap rsync
    mkdir -p "$BUILD" "$LOGS" "$CACHE" "$PKG_DIR"
    exec > >(tee -a "$LOGS/build-packages-$(timestamp).log") 2>&1

    local tarball="$CACHE/bootstrap-${TROTA_BASE_SUITE}-${TROTA_ARCH}.tar"
    if [ ! -x "$PKG_CHROOT/usr/bin/dpkg-buildpackage" ]; then
        [ -d "$PKG_CHROOT" ] && safe_rm "$PKG_CHROOT"
        mkdir -p "$PKG_CHROOT"
        if [ -f "$tarball" ]; then
            log "packages: build chroot from cached $(basename "$tarball")"
            tar -C "$PKG_CHROOT" -xpf "$tarball"
        else
            log "packages: debootstrap build chroot"
            debootstrap --arch="$TROTA_ARCH" --variant=buildd "$TROTA_BASE_SUITE" "$PKG_CHROOT" "$TROTA_MIRROR"
        fi
        cat > "$PKG_CHROOT/etc/apt/sources.list" <<EOF
deb $TROTA_MIRROR $TROTA_BASE_SUITE main universe
deb $TROTA_MIRROR $TROTA_BASE_SUITE-updates main universe
deb $TROTA_SECURITY_MIRROR $TROTA_BASE_SUITE-security main universe
EOF
        rm -f "$PKG_CHROOT/etc/apt/sources.list.d/ubuntu.sources"
        chroot_mount "$PKG_CHROOT"
        in_chroot "$PKG_CHROOT" apt-get update
        in_chroot "$PKG_CHROOT" apt-get -y --no-install-recommends install \
            build-essential dpkg-dev debhelper dh-python python3 python3-pytest \
            gettext librsvg2-bin python3-markdown shellcheck
    fi
    chroot_mount "$PKG_CHROOT"
    # Make sure the declared Build-Depends are satisfied (fails loudly if not).
    in_chroot "$PKG_CHROOT" apt-get -y --no-install-recommends install \
        build-essential dpkg-dev debhelper dh-python python3 python3-pytest gettext librsvg2-bin python3-markdown

    local version src="/build/$SRC_NAME"
    version="$(dpkg-parsechangelog -l "$TROTA_ROOT/packaging/debian/changelog" -S Version)"
    log "packages: $SRC_NAME $version"
    rm -rf "$PKG_CHROOT/build" && mkdir -p "$PKG_CHROOT$src"
    rsync -a --delete \
        --exclude '/build/' --exclude '/dist/' --exclude '/logs/' --exclude '/checksums/' --exclude '/.git/' \
        --exclude '__pycache__' --exclude '.pytest_cache' \
        "$TROTA_ROOT/" "$PKG_CHROOT$src/"
    cp -r "$TROTA_ROOT/packaging/debian" "$PKG_CHROOT$src/debian"

    in_chroot "$PKG_CHROOT" sh -c "cd $src && dpkg-buildpackage -b -us -uc"
    rm -f "$PKG_DIR"/*.deb "$PKG_DIR"/*.buildinfo "$PKG_DIR"/*.changes
    cp "$PKG_CHROOT"/build/*.deb "$PKG_CHROOT"/build/*.buildinfo "$PKG_CHROOT"/build/*.changes "$PKG_DIR/"
    log "packages: built $(find "$PKG_DIR" -name '*.deb' | wc -l) packages in $PKG_DIR"
    for deb in "$PKG_DIR"/*.deb; do
        printf '  %s\n' "$(basename "$deb")"
    done
}

main "$@"
