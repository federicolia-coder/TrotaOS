# Checks run as the live user "trota" on the serial console of the live session.
# Shared helpers (result/check/wait_for) are prepended by vmtest.py.

section "identity"
check os_release grep -q '^NAME="Trota OS"' /etc/os-release
check ubuntu_base_kept test -s /usr/lib/os-release.ubuntu
check lsb_compat sh -c 'test "$(lsb_release -is)" = Ubuntu && lsb_release -ds | grep -q "Trota OS"'
check aptsources_ubuntu python3 -c 'from aptsources.distro import get_distro; d = get_distro(); assert type(d).__name__ == "UbuntuDistribution", d; print(d.id, d.codename)'
check medium_name grep -q '^Trota OS' /cdrom/.disk/info

section "boot"
if wait_for 900 sh -c 'systemctl is-system-running | grep -qE "running|degraded"'; then
    state="$(systemctl is-system-running)"
    failed="$(systemctl --failed --no-legend --plain | awk '{print $1}' | tr '\n' ' ')"
    if [ "$state" = running ]; then result systemd PASS "running"; else result systemd FAIL "$state: $failed"; fi
else
    result systemd FAIL "boot did not complete: $(systemctl is-system-running)"
fi
check plymouth_theme sh -c 'update-alternatives --query default.plymouth | grep -q "^Value: /usr/share/plymouth/themes/trota/trota.plymouth"'
check apparmor sudo -n aa-status --enabled
result apparmor_profiles PASS "$(sudo -n aa-status 2>/dev/null | head -2 | tr '\n' ' ')"

section "desktop"
if wait_for 900 pgrep -u trota -x gnome-shell; then
    result gnome_shell PASS "$(gnome-shell --version)"
else
    result gnome_shell FAIL "gnome-shell not running for the live user"
fi
sid="$(loginctl list-sessions --no-legend | awk '$3=="trota"{print $1; exit}')"
result session_type PASS "$(loginctl show-session "$sid" -p Type -p Desktop 2>/dev/null | tr '\n' ' ')"
check wallpaper_default sh -c 'XDG_CURRENT_DESKTOP=ubuntu:GNOME gsettings get org.gnome.desktop.background picture-uri-dark | grep -q trota-forge'
check dark_style sh -c 'XDG_CURRENT_DESKTOP=ubuntu:GNOME gsettings get org.gnome.desktop.interface color-scheme | grep -q prefer-dark'
check terminal_palette sh -c 'dconf read /org/gnome/terminal/legacy/profiles:/:b1dcc9dd-5262-4d8d-a863-c897e6d979b9/background-color | grep -qi 101214'
check gdm_logo sh -c 'XDG_CURRENT_DESKTOP=GNOME-Greeter:GNOME gsettings get org.gnome.login-screen logo | grep -q trota-logo-gdm'
check welcome_autostart test -f /etc/xdg/autostart/trota-welcome.desktop
check installer_present sh -c 'command -v ubiquity'

section "applications"
check system_info sh -c 'trota-system-info --text | grep -E "^(Operating system|Kernel)"'
trota-system-info --text
trota-diagnostics --text --no-dns; rc=$?
[ $rc -le 1 ] && result diagnostics PASS "exit $rc" || result diagnostics FAIL "exit $rc"
check package_helper_backend python3 -c 'from trota_common import packages; r = packages.search("htop"); print(len(r), "results")'
check italian_translation sh -c 'LANGUAGE=it python3 -c "from trota_common.i18n import _; print(_(\"Welcome to Trota OS\"))" | grep -q Benvenuto'
# Start the GUI applications inside the running desktop session (screenshot taken by vmtest.py).
uid="$(id -u)"
for app in trota-system-info trota-welcome; do
    XDG_RUNTIME_DIR=/run/user/$uid WAYLAND_DISPLAY=wayland-0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$uid/bus \
        setsid "$app" >/tmp/$app.log 2>&1 < /dev/null &
done
sleep 30
for app in trota-system-info trota-welcome; do
    if pgrep -f "/usr/bin/$app" >/dev/null; then result "gui_$app" PASS "running in the session"
    else result "gui_$app" FAIL "$(tail -2 /tmp/$app.log | tr '\n' ' ')"; fi
done

section "software"
check no_snapd sh -c '! command -v snap && ! dpkg-query -W -f="\${db:Status-Abbrev}\n" snapd 2>/dev/null | grep -q "^ii"; test $? -eq 0 && echo "snapd not installed"'
check snapd_blocked sh -c '! apt-get -s -o Debug::NoLocking=1 install snapd >/dev/null 2>&1 && apt-cache policy snapd | grep -m1 "Candidate"'
check firefox_mozilla_deb sh -c 'v="$(dpkg-query -W -f="\${Version}" firefox)" && case "$v" in *snap*) exit 1;; esac && test -f /etc/apt/sources.list.d/mozilla.sources && echo "firefox $v"'
check firefox_runs sh -c 'timeout 300 firefox --version'
check firefox_italian sh -c 'dpkg-query -W -f="\${Package} \${Version}\n" firefox-l10n-it'
check gnome_software sh -c 'command -v gnome-software && dpkg-query -W -f="\${Package} \${Version}\n" gnome-software-plugin-flatpak'
check flathub_remote sh -c 'flatpak remotes --system --columns=name,url | grep "^flathub"'
check no_pro_apt_hook sh -c 'test -z "$(apt-config dump binary::apt::AptCli::Hooks::Upgrade | grep -v "^binary::apt::AptCli::Hooks::Upgrade \"\";")" && systemctl is-enabled esm-cache.service apt-news.service 2>&1 | tr "\n" " " | grep -q "^masked masked" && echo "hook cleared, esm-cache/apt-news masked"'
check no_pro_motd sh -c '! run-parts --lsbsysinit --test /etc/update-motd.d | grep -qE "10-help-text|91-contract-ua-esm-status" && echo "$(run-parts --lsbsysinit --test /etc/update-motd.d | wc -l) motd scripts"'
for u in casper-md5check.service; do
    systemctl status "$u" --no-pager 2>&1 | head -6; journalctl -b -u "$u" --no-pager 2>/dev/null | tail -5
done
check unattended_upgrades sh -c 'apt-config dump APT::Periodic | grep -q "Unattended-Upgrade \"1\""'
bad="$(dpkg-query -W -f='${db:Status-Abbrev} ${Package}\n' ubuntu-report whoopsie popularity-contest apport kerneloops openssh-server gnome-remote-desktop 2>/dev/null | awk '/^ii/{print $2}')"
[ -z "$bad" ] && result no_telemetry PASS "none of the excluded packages installed" || result no_telemetry FAIL "$bad"

section "network and hardware"
wait_for 120 sh -c 'nmcli -t -f STATE general | grep -q "^connected"' && result network PASS "$(nmcli -t -f STATE,CONNECTIVITY general)" || result network FAIL "$(nmcli -t general 2>&1)"
listen="$(ss -Htlnp 2>/dev/null | awk '{print $4}' | grep -vE '^(127\.|\[::1\]|::1)' | tr '\n' ' ')"
[ -z "$listen" ] && result no_open_tcp_ports PASS "no TCP service listening on external addresses" || result no_open_tcp_ports FAIL "$listen"
check audio_device sh -c 'aplay -l | grep -m1 "^card"'
if wait_for 120 pgrep -u trota -x pipewire; then result audio_pipewire PASS "pipewire running for the live user"; else result audio_pipewire FAIL "no pipewire"; fi
section "desktop session diagnostics"
# "Oh no! Something has gone wrong" means gnome-session lost a required component.
if journalctl -b --no-pager 2>/dev/null | grep -qE 'Unrecoverable failure in required component|gnome-session-failed|fail-whale|gnome-shell.*(segfault|killed by signal|dumped core)'; then
    result gnome_session_healthy FAIL "$(journalctl -b --no-pager 2>/dev/null | grep -E 'Unrecoverable failure|gnome-session-failed|fail-whale|segfault|killed by signal' | tail -2 | tr '\n' ' ' | cut -c1-200)"
else
    result gnome_session_healthy PASS "no gnome-session failure logged"
fi
sudo -n sh -c 'journalctl -b --no-pager -o short-monotonic > /mnt/journal-full.txt' || true
echo "--- gnome session journal"
journalctl -b --no-pager -o short-monotonic 2>/dev/null | grep -iE 'gnome-session|gnome-shell|gsd-|mutter|Xwayland|gdm' | grep -iE 'fail|error|crit|timeout|exit|killed|segfault' | grep -v 'Overwriting existing binding' | tail -60

section "measurements"
result measure_memory PASS "$(free -m | awk '/^Mem:/{printf "used %d MiB of %d MiB (available %d MiB)", $3, $2, $7}')"
result measure_disk PASS "$(df -BM --output=used,size / | awk 'NR==2{printf "root used %s of %s", $1, $2}')"
result measure_boot_time PASS "$(systemd-analyze 2>/dev/null | head -1 | cut -c1-140)"
echo CHECKS-DONE
