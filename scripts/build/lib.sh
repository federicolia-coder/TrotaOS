# shellcheck shell=bash
# Shared helpers for the Trota OS build scripts. Source, do not execute.

set -euo pipefail

TROTA_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export TROTA_ROOT
# shellcheck source=scripts/build/config.env
. "$TROTA_ROOT/scripts/build/config.env"

BUILD="$TROTA_ROOT/$TROTA_BUILD_DIR"
DIST="$TROTA_ROOT/$TROTA_DIST_DIR"
LOGS="$TROTA_ROOT/$TROTA_LOG_DIR"
CHECKSUMS="$TROTA_ROOT/$TROTA_CHECKSUM_DIR"
export BUILD DIST LOGS CHECKSUMS

log()  { printf '\033[1;38;5;208m[trota]\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[1;33m[trota] WARNING:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[trota] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

require_root() {
    [ "$(id -u)" -eq 0 ] || die "this step must run as root (it uses debootstrap, chroot and mount)"
}

require_cmds() {
    local missing=()
    for c in "$@"; do command -v "$c" >/dev/null 2>&1 || missing+=("$c"); done
    [ ${#missing[@]} -eq 0 ] || die "missing host tools: ${missing[*]} (see docs/building.md)"
}

# Refuse to operate on anything that is not inside $BUILD: every rm -rf and
# mount in the build goes through these guards.
assert_in_build() {
    local p
    p="$(realpath -m "$1")"
    case "$p" in
        "$BUILD"/?*) ;;
        *) die "refusing to touch path outside $BUILD: $p" ;;
    esac
}

safe_rm() {
    for p in "$@"; do
        assert_in_build "$p"
        if findmnt -rn -o TARGET | grep -q "^$(realpath -m "$p")\(/\|$\)"; then
            die "refusing to delete $p: something is still mounted below it"
        fi
        rm -rf --one-file-system -- "$p"
    done
}

# --- chroot mounts ----------------------------------------------------------
chroot_mount() {
    local root="$1"
    assert_in_build "$root"
    mountpoint -q "$root/proc"    || mount -t proc  proc   "$root/proc"
    mountpoint -q "$root/sys"     || mount -t sysfs sysfs  "$root/sys"
    mountpoint -q "$root/dev"     || mount --bind /dev     "$root/dev"
    mountpoint -q "$root/dev/pts" || mount -t devpts devpts "$root/dev/pts" -o gid=5,mode=620,newinstance,ptmxmode=0666
    mountpoint -q "$root/run"     || mount -t tmpfs tmpfs  "$root/run"
    mkdir -p "$root/run/lock" "$root/run/systemd/resolve"
    # Name resolution for the build only: /etc/resolv.conf in the image is a
    # symlink into /run, which is a tmpfs here, so nothing reaches the image.
    cp -L /etc/resolv.conf "$root/run/systemd/resolve/stub-resolv.conf"
    cp -L /etc/resolv.conf "$root/run/systemd/resolve/resolv.conf"
    # Optional extra CA bundle (e.g. a TLS-inspecting build proxy), also on /run.
    if [ -n "${TROTA_BUILD_CA_BUNDLE:-}" ]; then
        cp "$TROTA_BUILD_CA_BUNDLE" "$root/run/trota-build-ca.crt"
    fi
}

chroot_umount() {
    local root="$1" m
    assert_in_build "$root"
    # Unmount everything below $root, deepest first.
    findmnt -rn -o TARGET | grep "^$(realpath -m "$root")/" | sort -r | while read -r m; do
        umount -l "$m" || warn "could not unmount $m"
    done
}

# Run a command inside the chroot with a clean, predictable environment.
in_chroot() {
    local root="$1"; shift
    chroot "$root" /usr/bin/env -i \
        HOME=/root TERM=dumb LANG=C.UTF-8 LC_ALL=C.UTF-8 \
        PATH=/usr/sbin:/usr/bin:/sbin:/bin \
        DEBIAN_FRONTEND=noninteractive DEBCONF_NONINTERACTIVE_SEEN=true \
        ${HTTP_PROXY:+HTTP_PROXY="$HTTP_PROXY" http_proxy="$HTTP_PROXY"} \
        ${HTTPS_PROXY:+HTTPS_PROXY="$HTTPS_PROXY" https_proxy="$HTTPS_PROXY"} \
        ${NO_PROXY:+NO_PROXY="$NO_PROXY" no_proxy="$NO_PROXY"} \
        ${TROTA_BUILD_CA_BUNDLE:+SSL_CERT_FILE=/run/trota-build-ca.crt} \
        "$@"
}

# Read a package list: strips comments and blank lines.
read_list() {
    sed -e 's/#.*//' -e 's/[[:space:]]*$//' -e '/^$/d' "$@"
}

timestamp() { date -u +%Y%m%dT%H%M%SZ; }
