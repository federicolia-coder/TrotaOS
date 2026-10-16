# Checks run as the installed user on the serial console of the installed
# system (first boot). @PASSWORD@ and @FIRMWARE@ are substituted by vmtest.py.
# Shared helpers (result/check/wait_for) are prepended by vmtest.py.
PW='@PASSWORD@'
FIRMWARE='@FIRMWARE@'
as_root() { printf '%s\n' "$PW" | sudo -S -p '' "$@"; }

section "identity and installation"
check os_release grep -q '^NAME="Trota OS"' /etc/os-release
check live_packages_removed sh -c '! dpkg-query -W -f="\${db:Status-Abbrev} \${Package}\n" casper ubiquity 2>/dev/null | grep -q "^ii"'
check root_ext4 sh -c 'findmnt -no FSTYPE / | grep -qx ext4 && findmnt -no FSTYPE /'
check user_groups sh -c 'id -nG | tr " " "\n" | grep -qx sudo && id -nG'
check sudo_with_password as_root true
check swap sh -c 'swapon --show --noheadings | grep -q . && swapon --show --noheadings | head -1'

section "boot"
if wait_for 900 sh -c 'systemctl is-system-running | grep -qE "running|degraded"'; then
    state="$(systemctl is-system-running)"
    failed="$(systemctl --failed --no-legend --plain | awk '{print $1}' | tr '\n' ' ')"
    [ "$state" = running ] && result systemd PASS running || result systemd FAIL "$state: $failed"
else
    result systemd FAIL "boot did not complete"
fi
check grub_menu_name sh -c 'grep -m1 "^menuentry" /boot/grub/grub.cfg'
check grub_trota_entry grep -q "menuentry 'Trota OS'" /boot/grub/grub.cfg
if [ "$FIRMWARE" = bios ]; then
    result efi_boot SKIP "BIOS installation"
else
    check efi_boot test -d /sys/firmware/efi
    result efi_entries PASS "$(as_root efibootmgr 2>/dev/null | grep -iE 'boot0|trota|ubuntu' | tr '\n' ';' | cut -c1-150)"
    result esp_dirs PASS "$(as_root ls /boot/efi/EFI | tr '\n' ' ')"
fi
if [ "$FIRMWARE" = secureboot ]; then
    check secure_boot sh -c 'mokutil --sb-state 2>&1 | grep -q "SecureBoot enabled" && mokutil --sb-state'
fi
check plymouth_theme sh -c 'update-alternatives --query default.plymouth | grep -q "^Value: /usr/share/plymouth/themes/trota/trota.plymouth"'
check apparmor sh -c 'printf "%s\n" "$0" | sudo -S -p "" aa-status --enabled && echo enabled' "$PW"

section "desktop"
if wait_for 600 pgrep -u "$USER" -x gnome-shell; then result gnome_shell PASS "$(gnome-shell --version)"
else result gnome_shell FAIL "no gnome-shell for $USER (autologin)"; fi
sid="$(loginctl list-sessions --no-legend | awk -v u="$USER" '$3==u && $0 !~ /tty|ttyS/ {print $1; exit}')"
result session_type PASS "$(loginctl show-session "$sid" -p Type -p Desktop 2>/dev/null | tr '\n' ' ')"
if wait_for 120 pgrep -u "$USER" -f trota-welcome; then result welcome_autostart PASS "Trota Welcome started at login"
else result welcome_autostart FAIL "trota-welcome not running after login"; fi
check wallpaper sh -c 'XDG_CURRENT_DESKTOP=ubuntu:GNOME gsettings get org.gnome.desktop.background picture-uri-dark | grep trota-forge'
if wait_for 120 pgrep -u "$USER" -x pipewire; then result audio_pipewire PASS "pipewire running"; else result audio_pipewire FAIL "no pipewire"; fi
check audio_device sh -c 'aplay -l | grep -m1 "^card"'

section "applications"
check system_info sh -c 'trota-system-info --text | grep -E "^(Operating system|Based on)"'
trota-system-info --text
trota-diagnostics --text --no-dns; rc=$?
[ $rc -le 1 ] && result diagnostics PASS "exit $rc" || result diagnostics FAIL "exit $rc"

section "software and updates"
if wait_for 1200 sh -c 'snap list firefox && snap list snap-store'; then
    result snaps_installed PASS "$(snap list | awk 'NR>1{print $1}' | tr '\n' ' ')"
else
    result snaps_installed FAIL "$(snap changes 2>&1 | tail -3 | tr '\n' ' ')"
fi
echo "--- snapd diagnostics"; snap changes 2>&1 | tail -8; systemctl status snapd.seeded.service --no-pager 2>&1 | head -8
check snapd_seeded_service systemctl is-active snapd.seeded.service
check firefox_runs sh -c 'timeout 300 snap run firefox --version'
check unattended_upgrades sh -c 'apt-config dump APT::Periodic | grep -q "Unattended-Upgrade \"1\"" && systemctl is-enabled unattended-upgrades'
wait_for 120 sh -c 'nmcli -t -f STATE general | grep -q "^connected"' && result network PASS "$(nmcli -t -f STATE,CONNECTIVITY general)" || result network FAIL "$(nmcli -t general 2>&1)"
if as_root apt-get update >/tmp/apt-update.log 2>&1; then
    result apt_update PASS "$(grep -c '^\(Hit\|Get\)' /tmp/apt-update.log) indexes"
    n="$(apt-get -s -o Debug::NoLocking=1 upgrade | grep -c '^Inst ')"
    result apt_upgrade_simulation PASS "$n packages upgradable"
    check unattended_upgrade_dry_run sh -c 'printf "%s\n" "$0" | sudo -S -p "" timeout 900 unattended-upgrade --dry-run 2>&1 | tail -1; exit 0' "$PW"
    check package_helper_search python3 -c 'from trota_common import packages; r = packages.search("htop"); assert r; i = packages.info(r[0].name); print(i.name, i.version, i.summary)'
else
    result apt_update FAIL "$(tail -2 /tmp/apt-update.log | tr '\n' ' ')"
fi
listen="$(ss -Htln 2>/dev/null | awk '{print $4}' | grep -vE '^(127\.|\[::1\]|::1)' | tr '\n' ' ')"
[ -z "$listen" ] && result no_open_tcp_ports PASS "no TCP service listening on external addresses" || result no_open_tcp_ports FAIL "$listen"
bad="$(dpkg-query -W -f='${db:Status-Abbrev} ${Package}\n' ubuntu-report whoopsie popularity-contest apport kerneloops openssh-server 2>/dev/null | awk '/^ii/{print $2}')"
[ -z "$bad" ] && result no_telemetry PASS "none of the excluded packages installed" || result no_telemetry FAIL "$bad"
check apt_news_disabled sh -c 'pro config show apt_news 2>/dev/null | grep -q False && echo apt_news=False'
check release_upgrade_prompt sh -c 'grep -E "^Prompt=" /etc/update-manager/release-upgrades'
section "measurements"
result measure_memory PASS "$(free -m | awk '/^Mem:/{printf "used %d MiB of %d MiB (available %d MiB)", $3, $2, $7}')"
result measure_disk PASS "$(df -BM --output=used,size / | awk 'NR==2{printf "root used %s of %s", $1, $2}')"
result measure_boot_time PASS "$(systemd-analyze 2>/dev/null | head -1 | cut -c1-140)"
echo CHECKS-DONE
