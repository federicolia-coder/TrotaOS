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
# grub.cfg is readable by root only on Ubuntu 24.04
check grub_menu_name sh -c 'printf "%s\n" "$0" | sudo -S -p "" grep -m1 "^menuentry" /boot/grub/grub.cfg' "$PW"
check grub_trota_entry sh -c 'printf "%s\n" "$0" | sudo -S -p "" grep -q "menuentry .Trota OS" /boot/grub/grub.cfg' "$PW"
echo "--- grub.cfg modules and fonts"; as_root grep -nE 'insmod|loadfont|font=|gfx|theme' /boot/grub/grub.cfg | head -25
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

section "identity and lightness"
check no_ubuntu_motd sh -c '! run-parts --lsbsysinit --test /etc/update-motd.d | grep -qE "00-header|10-help-text" && /etc/update-motd.d/05-trota-os | grep -m1 Welcome'
check uu_security_origin sh -c 'apt-config dump Unattended-Upgrade::Allowed-Origins | grep -q "Ubuntu:\${distro_codename}-security" && apt-config dump Unattended-Upgrade::Origins-Pattern | grep -q packages.mozilla.org && echo "base security archive and Mozilla allowed"'
check gdm_session_name sh -c 'grep -h "^Name=" /usr/share/wayland-sessions/*.desktop /usr/share/xsessions/*.desktop | sort -u | tr "\n" " " | grep -v Ubuntu'
check no_ubuntu_wallpapers sh -c '! ls /usr/share/gnome-background-properties | grep -qv trota && ls /usr/share/gnome-background-properties'
check tracker_masked sh -c 'test "$(readlink /etc/systemd/user/tracker-miner-fs-3.service)" = /dev/null && echo masked'
check no_software_autostart sh -c '! test -e /etc/xdg/autostart/org.gnome.Software.desktop && ! test -e /etc/xdg/autostart/ubuntu-advantage-notification.desktop && echo "not started at login"'
check flatpak_update_timer systemctl is-enabled trota-flatpak-update.timer
check dock_icon_trota sh -c '! test -e /usr/share/icons/Yaru/scalable/actions/view-app-grid-ubuntu-symbolic.svg && test -e /usr/share/icons/hicolor/scalable/actions/view-app-grid-ubuntu-symbolic.svg && echo "Trota grid icon"'
check no_live_leftovers sh -c '! test -e /etc/xdg/autostart/trota-live-installer-icon.desktop && echo "live-only files removed"'
check no_sssd sh -c '! systemctl list-unit-files sssd.service --no-legend | grep -q . && echo "sssd not installed"'
result memory_after_login PASS "$(free -m | awk '/^Mem:/{print $3 " MB used of " $2 " MB"}')"

section "applications"
check system_info sh -c 'trota-system-info --text | grep -E "^(Operating system|Based on)"'
trota-system-info --text
trota-diagnostics --text --no-dns; rc=$?
[ $rc -le 1 ] && result diagnostics PASS "exit $rc" || result diagnostics FAIL "exit $rc"

section "software and updates"
check no_snapd sh -c '! command -v snap && ! dpkg-query -W -f="\${db:Status-Abbrev}\n" snapd 2>/dev/null | grep -q "^ii"; test $? -eq 0 && echo "snapd not installed"'
check snapd_blocked sh -c '! apt-get -s -o Debug::NoLocking=1 install snapd >/dev/null 2>&1 && apt-cache policy snapd | grep -m1 "Candidate"'
check firefox_mozilla_deb sh -c 'v="$(dpkg-query -W -f="\${Version}" firefox)" && case "$v" in *snap*) exit 1;; esac && test -f /etc/apt/sources.list.d/mozilla.sources && echo "firefox $v"'
check firefox_runs sh -c 'timeout 300 firefox --version'
check firefox_italian sh -c 'dpkg-query -W -f="\${Package} \${Version}\n" firefox-l10n-it'
check gnome_software sh -c 'command -v gnome-software && dpkg-query -W -f="\${Package} \${Version}\n" gnome-software-plugin-flatpak'
check flathub_remote sh -c 'flatpak remotes --system --columns=name,url | grep "^flathub"'
check no_pro_apt_hook sh -c 'test -z "$(apt-config dump binary::apt::AptCli::Hooks::Upgrade | grep -v "^binary::apt::AptCli::Hooks::Upgrade \"\";")" && systemctl is-enabled esm-cache.service apt-news.service 2>&1 | tr "\n" " " | grep -q "^masked masked" && echo "hook cleared, esm-cache/apt-news masked"'
check no_pro_motd sh -c '! run-parts --lsbsysinit --test /etc/update-motd.d | grep -qE "10-help-text|91-contract-ua-esm-status" && echo "$(run-parts --lsbsysinit --test /etc/update-motd.d | wc -l) motd scripts"'
check unattended_upgrades sh -c 'apt-config dump APT::Periodic | grep -q "Unattended-Upgrade \"1\"" && systemctl is-enabled unattended-upgrades'
wait_for 120 sh -c 'nmcli -t -f STATE general | grep -q "^connected"' && result network PASS "$(nmcli -t -f STATE,CONNECTIVITY general)" || result network FAIL "$(nmcli -t general 2>&1)"
if as_root apt-get update >/tmp/apt-update.log 2>&1; then
    result apt_update PASS "$(grep -c '^\(Hit\|Get\)' /tmp/apt-update.log) indexes"
    n="$(apt-get -s -o Debug::NoLocking=1 upgrade | grep -c '^Inst ')"
    result apt_upgrade_simulation PASS "$n packages upgradable"
    check unattended_upgrade_dry_run sh -c 'printf "%s\n" "$0" | sudo -S -p "" timeout 900 unattended-upgrade --dry-run 2>&1 | tail -1; exit 0' "$PW"
    check ppa_add sh -c 'printf "%s\n" "$0" | sudo -S -p "" timeout 300 add-apt-repository -y -n ppa:git-core/ppa >/dev/null 2>&1; f=$(ls /etc/apt/sources.list.d/ | grep -m1 git-core) && grep -h "^Suites:" "/etc/apt/sources.list.d/$f" | grep -q noble && echo "$f (noble)"; r=$?; printf "%s\n" "$0" | sudo -S -p "" add-apt-repository -y -n -r ppa:git-core/ppa >/dev/null 2>&1; exit $r' "$PW"
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
section "desktop session diagnostics"
# "Oh no! Something has gone wrong" means gnome-session lost a required component.
if journalctl -b --no-pager 2>/dev/null | grep -qE 'Unrecoverable failure in required component|gnome-session-failed|fail-whale|gnome-shell.*(segfault|killed by signal|dumped core)'; then
    result gnome_session_healthy FAIL "$(journalctl -b --no-pager 2>/dev/null | grep -E 'Unrecoverable failure|gnome-session-failed|fail-whale|segfault|killed by signal' | tail -2 | tr '\n' ' ' | cut -c1-200)"
else
    result gnome_session_healthy PASS "no gnome-session failure logged"
fi
as_root sh -c 'journalctl -b --no-pager -o short-monotonic > /mnt/journal-full.txt' || true
echo "--- gnome session journal"
journalctl -b --no-pager -o short-monotonic 2>/dev/null | grep -iE 'gnome-session|gnome-shell|gsd-|mutter|Xwayland|gdm' | grep -iE 'fail|error|crit|timeout|exit|killed|segfault' | grep -v 'Overwriting existing binding' | tail -60

section "measurements"
result measure_memory PASS "$(free -m | awk '/^Mem:/{printf "used %d MiB of %d MiB (available %d MiB)", $3, $2, $7}')"
result measure_disk PASS "$(df -BM --output=used,size / | awk 'NR==2{printf "root used %s of %s", $1, $2}')"
result measure_boot_time PASS "$(systemd-analyze 2>/dev/null | head -1 | cut -c1-140)"
echo CHECKS-DONE
