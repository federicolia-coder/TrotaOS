# Checks run as user "trota" on the serial console of a Trota OS disk image
# (server or cloud edition) at first boot. @PASSWORD@, @FIRMWARE@, @EDITION@ and
# @DISK_GB@ are substituted by vmtest.py; helpers are prepended by vmtest.py.
PW='@PASSWORD@'
FIRMWARE='@FIRMWARE@'
EDITION='@EDITION@'
DISK_GB='@DISK_GB@'
as_root() { printf '%s\n' "$PW" | sudo -S -p '' "$@"; }

section "identity"
check os_release sh -c 'grep -q "^ID=trota" /etc/os-release && grep -q "^NAME=\"Trota OS\"" /etc/os-release && grep PRETTY_NAME /etc/os-release'
check lsb_identity sh -c 'test "$(lsb_release -is)" = Trota && test "$(lsb_release -cs)" = noble && lsb_release -ds'
check no_ubuntu_motd sh -c '! run-parts --lsbsysinit --test /etc/update-motd.d | grep -qE "00-header|10-help-text" && echo ok'
check kernel sh -c 'uname -r'
result kernel_flavour PASS "$(dpkg-query -W -f='${Package} ' 'linux-image-*-hwe-24.04' 2>/dev/null)"

section "first boot"
if as_root timeout 900 cloud-init status --wait >/dev/null 2>&1 || as_root cloud-init status | grep -q "status: done"; then
    result cloud_init PASS "$(as_root cloud-init status --long 2>&1 | grep -E 'status|detail' | tr '\n' ' ' | cut -c1-160)"
else
    result cloud_init FAIL "$(as_root cloud-init status --long 2>&1 | tr '\n' ' ' | cut -c1-200)"
fi
result datasource PASS "$(as_root cloud-init query platform 2>/dev/null || echo unknown)"
check root_grown sh -c 'size=$(df -B1 --output=size / | tail -1); test "$size" -gt $(( ($0 - 2) * 1024 * 1024 * 1024 )) && echo "/ is $((size / 1024 / 1024 / 1024)) GiB on a $0 GB disk"' "$DISK_GB"
check ssh_host_keys sh -c 'ls /etc/ssh/ssh_host_*_key.pub | wc -l | grep -qv "^0$" && ls /etc/ssh/ssh_host_*_key.pub | tr "\n" " "'
check machine_id_unique sh -c 'test -s /etc/machine-id && cat /etc/machine-id'
check network sh -c 'ip -4 -o addr show scope global | awk "{print \$2, \$4}" | grep .'
if wait_for 900 sh -c 'systemctl is-system-running | grep -qE "running|degraded"'; then
    state="$(systemctl is-system-running)"
    failed="$(systemctl --failed --no-legend --plain | awk '{print $1}' | tr '\n' ' ')"
    [ "$state" = running ] && result systemd PASS running || result systemd FAIL "$state: $failed"
else
    result systemd FAIL "boot did not complete"
fi
result boot_time PASS "$(systemd-analyze 2>/dev/null | head -1)"

section "boot loader"
if [ "$FIRMWARE" = bios ]; then
    result efi_boot SKIP "BIOS"
else
    check efi_boot test -d /sys/firmware/efi
    check esp_fallback sh -c 'printf "%s\n" "$0" | sudo -S -p "" ls /boot/efi/EFI/BOOT/ | tr "\n" " " | grep -q -i bootx64 && echo "EFI/BOOT/BOOTX64.EFI present"' "$PW"
fi
[ "$FIRMWARE" = secureboot ] && check secure_boot sh -c 'mokutil --sb-state 2>&1 | grep -q "SecureBoot enabled" && mokutil --sb-state'
check grub_trota_entry sh -c 'printf "%s\n" "$0" | sudo -S -p "" grep -m1 "^menuentry" /boot/grub/grub.cfg | grep -q "Trota OS" && echo "Trota OS entry"' "$PW"

section "security"
# Ubuntu 24.04 starts sshd on the first connection (ssh.socket).
check ssh_listening sh -c 'systemctl is-active ssh.socket ssh.service | grep -qx active && ss -Htln | grep -E ":22\b" | head -1'
check ssh_keys_only sh -c 'printf "%s\n" "$0" | sudo -S -p "" install -d -m 755 /run/sshd; printf "%s\n" "$0" | sudo -S -p "" sshd -T 2>/dev/null | grep -E "^(passwordauthentication|permitrootlogin) " | tr "\n" " " | grep -q "passwordauthentication no" && printf "%s\n" "$0" | sudo -S -p "" sshd -T | grep -E "^(passwordauthentication|permitrootlogin) " | tr "\n" " "' "$PW"
check firewall sh -c 'printf "%s\n" "$0" | sudo -S -p "" ufw status | grep -q "Status: active" && printf "%s\n" "$0" | sudo -S -p "" ufw status | grep -E "OpenSSH|22" | head -1' "$PW"
check sysctl_hardening sh -c 'test "$(sysctl -n kernel.kptr_restrict)" = 2 && test "$(sysctl -n kernel.dmesg_restrict)" = 1 && test "$(sysctl -n net.ipv4.conf.all.accept_redirects)" = 0 && echo "kptr_restrict=2 dmesg_restrict=1 accept_redirects=0"'
check apparmor sh -c 'printf "%s\n" "$0" | sudo -S -p "" aa-status --enabled && echo enabled' "$PW"
check uu_security_origin sh -c 'apt-config dump Unattended-Upgrade::Allowed-Origins | grep -q "Ubuntu:\${distro_codename}-security" && systemctl is-enabled unattended-upgrades'
check no_snapd sh -c '! command -v snap && echo "no snapd"'
if [ "$EDITION" = kiosk ]; then
    check mozilla_source_only sh -c 'ls /etc/apt/sources.list.d/ | tr "\n" " " | grep -q mozilla && echo "base archive and Mozilla (Firefox)"'
else
    check no_mozilla_source sh -c '! test -e /etc/apt/sources.list.d/mozilla.sources && echo "base archive only"'
fi
check no_pro_apt_hook sh -c 'systemctl is-enabled esm-cache.service apt-news.service 2>&1 | tr "\n" " " | grep -q "^masked masked" && echo masked'
bad="$(dpkg-query -W -f='${db:Status-Abbrev} ${Package}\n' ubuntu-report whoopsie popularity-contest apport snapd landscape-common 2>/dev/null | awk '/^ii/{print $2}')"
[ -z "$bad" ] && result no_telemetry PASS "none installed" || result no_telemetry FAIL "$bad"
listen="$(ss -Htln 2>/dev/null | awk '{print $4}' | grep -vE '^(127\.|\[::1\]|::1)' | grep -vE ':22$' | tr '\n' ' ')"
[ -z "$listen" ] && result open_tcp_ports PASS "only SSH (22) on external addresses" || result open_tcp_ports FAIL "$listen"
check journald_limit sh -c 'systemd-analyze cat-config systemd/journald.conf 2>/dev/null | grep -q "^SystemMaxUse=500M" && echo "SystemMaxUse=500M"'

section "containers"
check podman_rootless sh -c 'podman info --format "{{.Host.Security.Rootless}} {{.Version.Version}}" 2>&1 | grep -q "^true" && podman info --format "rootless {{.Version.Version}}, {{.Host.NetworkBackend}}"'
# A rootless container without downloads: the host file system as read-only rootfs.
check podman_run sh -c 'out=$(timeout 600 podman run --rm --network none --read-only --rootfs / /bin/echo container-ok 2>&1); echo "$out" | grep -q container-ok && echo "rootless container ran" || { echo "$out" | tail -1; exit 1; }'
if out="$(timeout 600 podman pull -q docker.io/library/busybox:latest 2>&1)"; then
    result podman_pull PASS "busybox pulled from Docker Hub"
else
    result podman_pull SKIP "registry not reachable from the test VM: $(echo "$out" | tail -1 | cut -c1-100)"
fi

if [ "$EDITION" = kiosk ]; then
    section "kiosk"
    check kiosk_service systemctl is-active trota-kiosk.service
    check kiosk_default_target sh -c 'test "$(systemctl get-default)" = graphical.target && echo graphical.target'
    if wait_for 600 pgrep -u kiosk -x cage; then result kiosk_cage PASS "cage running as kiosk"
    else result kiosk_cage FAIL "$(journalctl -u trota-kiosk -b --no-pager 2>/dev/null | tail -3 | tr '\n' ' ')"; fi
    if wait_for 600 pgrep -u kiosk -f firefox; then result kiosk_firefox PASS "firefox running as kiosk"
    else result kiosk_firefox FAIL "no firefox for the kiosk user"; fi
    check kiosk_policies sh -c 'python3 -c "import json; p = json.load(open(\"/etc/firefox/policies/policies.json\"))[\"policies\"]; assert p[\"DisableTelemetry\"]; print(len(p), \"policies\")"'
    check kiosk_restart_timer systemctl is-enabled trota-kiosk-restart.timer
    check kiosk_no_vt_switch sh -c 'grep -q "^TROTA_KIOSK_VT_SWITCH=no" /etc/trota-kiosk.conf && echo "VT switching off"'
    check kiosk_firefox_mozilla sh -c 'v=$(dpkg-query -W -f="\${Version}" firefox) && case "$v" in *snap*) exit 1;; esac && echo "firefox $v"'
    # Restart on crash: kill the browser, the service brings it back.
    pkill_out="$(printf '%s\n' "$PW" | sudo -S -p '' pkill -u kiosk -x cage; sleep 20; pgrep -u kiosk -x cage)"
    [ -n "$pkill_out" ] && result kiosk_restarts PASS "cage back after being killed" || result kiosk_restarts FAIL "not restarted"
fi

section "updates"
if as_root timeout 900 apt-get update >/tmp/apt-update.log 2>&1; then
    result apt_update PASS "$(grep -c '^\(Hit\|Get\)' /tmp/apt-update.log) indexes"
    check unattended_upgrade_dry_run sh -c 'printf "%s\n" "$0" | sudo -S -p "" timeout 900 unattended-upgrade --dry-run --debug 2>&1 | grep -m1 -i "allowed origins"' "$PW"
else
    result apt_update FAIL "$(tail -2 /tmp/apt-update.log | tr '\n' ' ')"
fi

section "resources"
result memory PASS "$(free -m | awk '/^Mem:/{print $3 " MB used of " $2 " MB"}')"
result disk_used PASS "$(df -h / | awk 'NR==2{print $3 " used on /"}')"
result packages PASS "$(dpkg-query -W -f='.' | wc -c) packages"
echo CHECKS-DONE
