import json
import os
from collections import namedtuple
from pathlib import Path

import pytest

from conftest import FakeRunner, fail, ok
from trota_common import diagnostics as dg
from trota_common.runner import CommandResult

Usage = namedtuple("Usage", "total used free")
GiB = 1024**3


def ctx(tmp_path, runner=None, **kw):
    return dg.Context(runner=runner or FakeRunner(), root=tmp_path, **kw)


def write(root: Path, rel: str, text: str):
    p = root / rel.lstrip("/")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


# --- disk ----------------------------------------------------------------------
@pytest.mark.parametrize("free,total,expected", [
    (200 * GiB, 500 * GiB, dg.OK),
    (4 * GiB, 50 * GiB, dg.WARNING),     # 8% free but < 5 GiB
    (30 * GiB, 500 * GiB, dg.WARNING),   # 6% free
    (0.5 * GiB, 500 * GiB, dg.ERROR),
    (12 * GiB, 500 * GiB, dg.ERROR),     # 2.4% free
])
def test_disk_thresholds(tmp_path, free, total, expected):
    r = dg.check_disk_space(ctx(tmp_path, disk_usage=lambda p: Usage(total, total - free, free)))
    assert r.status == expected
    assert bool(r.suggestion) == (expected != dg.OK)


def test_disk_same_filesystem_reported_once(tmp_path):
    r = dg.check_disk_space(ctx(tmp_path, disk_usage=lambda p: Usage(100 * GiB, 10 * GiB, 90 * GiB)))
    assert len(r.details) == 1


def test_disk_unreadable(tmp_path):
    def boom(p):
        raise PermissionError(13, "Permission denied")
    r = dg.check_disk_space(ctx(tmp_path, disk_usage=boom))
    assert r.status == dg.OK and "cannot be read" in r.details[0]


# --- network -------------------------------------------------------------------
def test_network_full(tmp_path):
    runner = FakeRunner({
        ("nmcli", "-t", "-f", "STATE,CONNECTIVITY", "general"): ok("connected:full\n"),
        ("nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device"): ok("enp3s0:ethernet:connected\nlo:loopback:unmanaged\n"),
    })
    r = dg.check_network(ctx(tmp_path, runner, resolve=lambda h: True))
    assert r.status == dg.OK
    assert any("enp3s0" in d for d in r.details) and not any(d.startswith("lo") for d in r.details)
    assert any("working" in d for d in r.details)


def test_network_portal(tmp_path):
    runner = FakeRunner({("nmcli", "-t", "-f", "STATE,CONNECTIVITY", "general"): ok("connected (site only):portal\n")})
    assert dg.check_network(ctx(tmp_path, runner)).status == dg.WARNING


def test_network_disconnected(tmp_path):
    runner = FakeRunner({("nmcli", "-t", "-f", "STATE,CONNECTIVITY", "general"): ok("disconnected:none\n")})
    r = dg.check_network(ctx(tmp_path, runner))
    assert r.status == dg.WARNING and "Not connected" in r.summary


def test_network_without_nmcli(tmp_path):
    assert dg.check_network(ctx(tmp_path)).status == dg.SKIPPED


def test_network_nmcli_error(tmp_path):
    runner = FakeRunner({("nmcli",): fail(8, stderr="Error: NetworkManager is not running.")})
    r = dg.check_network(ctx(tmp_path, runner))
    assert r.status == dg.WARNING and "NetworkManager is not running" in r.details[0]


# --- kernel --------------------------------------------------------------------
def test_kernel_up_to_date(tmp_path):
    write(tmp_path, "/boot/vmlinuz-6.8.0-45-generic", "")
    write(tmp_path, "/boot/vmlinuz-6.8.0-40-generic", "")
    r = dg.check_kernel(ctx(tmp_path, kernel_release="6.8.0-45-generic"))
    assert r.status == dg.OK


def test_kernel_newer_installed(tmp_path):
    write(tmp_path, "/boot/vmlinuz-6.8.0-45-generic", "")
    write(tmp_path, "/boot/vmlinuz-6.8.0-100-generic", "")   # numeric, not lexical, ordering
    r = dg.check_kernel(ctx(tmp_path, kernel_release="6.8.0-45-generic"))
    assert r.status == dg.INFO and "newer" in r.summary


def test_kernel_reboot_required(tmp_path):
    write(tmp_path, "/boot/vmlinuz-6.8.0-45-generic", "")
    write(tmp_path, "/var/run/reboot-required", "*** System restart required ***\n")
    write(tmp_path, "/var/run/reboot-required.pkgs", "linux-base\nlibc6\nlibc6\n")
    r = dg.check_kernel(ctx(tmp_path, kernel_release="6.8.0-45-generic"))
    assert r.status == dg.WARNING and any("libc6, linux-base" in d for d in r.details)


def test_kernel_live_session(tmp_path):
    r = dg.check_kernel(ctx(tmp_path, kernel_release="6.8.0-45-generic"))
    assert r.status == dg.OK   # no /boot kernels visible: nothing to compare
    write(tmp_path, "/boot/vmlinuz-6.11.0-1-generic", "")
    assert dg.check_kernel(ctx(tmp_path, kernel_release="6.8.0-45-generic")).status == dg.INFO


def test_kernel_tainted_is_reported(tmp_path):
    write(tmp_path, "/proc/sys/kernel/tainted", "4097\n")
    r = dg.check_kernel(ctx(tmp_path, kernel_release="6.8.0-45-generic"))
    assert any("4097" in d for d in r.details)


# --- security ------------------------------------------------------------------
APT_ON = 'APT::Periodic "";\nAPT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n'
APT_OFF = 'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "0";\n'


def test_security_all_good(tmp_path):
    write(tmp_path, "/sys/module/apparmor/parameters/enabled", "Y\n")
    write(tmp_path, "/etc/ufw/ufw.conf", "ENABLED=no\n")
    r = dg.check_security(ctx(tmp_path, FakeRunner({("apt-config", "dump"): ok(APT_ON)})))
    assert r.status == dg.OK
    assert any("Firewall" in d for d in r.details)


def test_security_unattended_off(tmp_path):
    write(tmp_path, "/sys/module/apparmor/parameters/enabled", "Y\n")
    r = dg.check_security(ctx(tmp_path, FakeRunner({("apt-config", "dump"): ok(APT_OFF)})))
    assert r.status == dg.WARNING and r.suggestion


def test_security_apparmor_disabled(tmp_path):
    write(tmp_path, "/sys/module/apparmor/parameters/enabled", "N\n")
    r = dg.check_security(ctx(tmp_path, FakeRunner({("apt-config", "dump"): ok(APT_ON)})))
    assert r.status == dg.WARNING


# --- services ------------------------------------------------------------------
def show_output(states):
    blocks = []
    for name, _req in dg.SERVICES:
        load, active = states.get(name, ("loaded", "active"))
        blocks.append(f"Id={name}\nLoadState={load}\nActiveState={active}\nSubState=running")
    return "\n\n".join(blocks) + "\n"


def test_services_ok(tmp_path):
    runner = FakeRunner({("systemctl", "show"): ok(show_output({})), ("systemctl", "--failed"): ok("")})
    assert dg.check_services(ctx(tmp_path, runner)).status == dg.OK


def test_services_networkmanager_down_is_error(tmp_path):
    runner = FakeRunner({
        ("systemctl", "show"): ok(show_output({"NetworkManager.service": ("loaded", "failed")})),
        ("systemctl", "--failed"): ok("NetworkManager.service loaded failed failed Network Manager\n"),
    })
    r = dg.check_services(ctx(tmp_path, runner))
    assert r.status == dg.ERROR and any("Failed units" in d for d in r.details)


def test_services_optional_missing_is_fine(tmp_path):
    runner = FakeRunner({("systemctl", "show"): ok(show_output({"cups.service": ("not-found", "inactive")})),
                         ("systemctl", "--failed"): ok("")})
    assert dg.check_services(ctx(tmp_path, runner)).status == dg.OK


def test_services_required_missing_is_warning(tmp_path):
    runner = FakeRunner({("systemctl", "show"): ok(show_output({"apparmor.service": ("not-found", "inactive")})),
                         ("systemctl", "--failed"): ok("")})
    assert dg.check_services(ctx(tmp_path, runner)).status == dg.WARNING


def test_services_failed_optional_unit_is_warning(tmp_path):
    runner = FakeRunner({("systemctl", "show"): ok(show_output({})),
                         ("systemctl", "--failed"): ok("foo.service loaded failed failed Foo\n")})
    assert dg.check_services(ctx(tmp_path, runner)).status == dg.WARNING


def test_services_no_systemd(tmp_path):
    runner = FakeRunner({("systemctl",): fail(1, stderr="System has not been booted with systemd")})
    assert dg.check_services(ctx(tmp_path, runner)).status == dg.SKIPPED


# --- logs ----------------------------------------------------------------------
def test_logs_clean(tmp_path):
    assert dg.check_logs(ctx(tmp_path, FakeRunner({("journalctl",): ok("")}))).status == dg.OK


def test_logs_some_errors(tmp_path):
    out = "".join(f"2026-10-16T10:00:{i:02d}+0000 host kernel: error {i}\n" for i in range(5))
    r = dg.check_logs(ctx(tmp_path, FakeRunner({("journalctl",): ok(out)})))
    assert r.status == dg.INFO and "5" in r.summary and len(r.details) == 5


def test_logs_many_errors_and_restricted_access(tmp_path):
    out = "".join(f"line {i}\n" for i in range(40))
    stderr = "Hint: You are currently not seeing messages from other users and the system."
    r = dg.check_logs(ctx(tmp_path, FakeRunner({("journalctl",): ok(out, stderr)})))
    assert r.status == dg.WARNING and "adm" in r.details[0]


# --- updates -------------------------------------------------------------------
def test_updates_security_pending(tmp_path):
    write(tmp_path, "/var/lib/apt/periodic/update-success-stamp", "")
    runner = FakeRunner({("/usr/lib/update-notifier/apt-check",): ok("", "12;3")})
    r = dg.check_updates(ctx(tmp_path, runner))
    assert r.status == dg.WARNING and "3" in r.summary


def test_updates_up_to_date(tmp_path):
    write(tmp_path, "/var/lib/apt/periodic/update-success-stamp", "")
    runner = FakeRunner({("/usr/lib/update-notifier/apt-check",): ok("", "0;0")})
    assert dg.check_updates(ctx(tmp_path, runner)).status == dg.OK


def test_updates_stale_lists(tmp_path):
    p = write(tmp_path, "/var/lib/apt/periodic/update-success-stamp", "")
    old = p.stat().st_mtime - 30 * 86400
    os.utime(p, (old, old))
    runner = FakeRunner({("/usr/lib/update-notifier/apt-check",): ok("", "0;0")})
    r = dg.check_updates(ctx(tmp_path, runner))
    assert r.status == dg.WARNING and "week" in r.summary


def test_updates_fallback_to_apt_simulation(tmp_path):
    sim = ("Inst libc6 [2.39-0ubuntu8.4] (2.39-0ubuntu8.5 Ubuntu:24.04/noble-security [amd64])\n"
           "Inst vim [2:9.1] (2:9.1.1 Ubuntu:24.04/noble-updates [amd64])\n")
    runner = FakeRunner({("apt-get", "-s"): ok(sim)})
    r = dg.check_updates(ctx(tmp_path, runner))
    assert r.status == dg.WARNING and any("security: 1" in d for d in r.details)


def test_updates_unavailable(tmp_path):
    assert dg.check_updates(ctx(tmp_path)).status == dg.SKIPPED


# --- runner / framework ----------------------------------------------------------
def test_broken_check_does_not_stop_others(tmp_path):
    def check_broken(c):
        raise RuntimeError("boom")

    def check_fine(c):
        return dg.CheckResult("fine", "Fine", dg.OK, "ok")

    results = dg.run_all(ctx(tmp_path), checks=(check_broken, check_fine))
    assert [r.status for r in results] == [dg.ERROR, dg.OK]
    assert "boom" in results[0].details[0]


def test_overall_status():
    mk = lambda s: dg.CheckResult("x", "x", s, "")  # noqa: E731
    assert dg.overall_status([mk(dg.OK), mk(dg.INFO)]) == dg.INFO
    assert dg.overall_status([mk(dg.SKIPPED), mk(dg.ERROR), mk(dg.WARNING)]) == dg.ERROR
    assert dg.overall_status([]) == dg.OK


def test_json_export(tmp_path):
    data = json.loads(dg.to_json([dg.CheckResult("a", "A", dg.OK, "fine", ["d"], "")]))
    assert data[0]["id"] == "a" and data[0]["details"] == ["d"]


def test_checks_never_run_privileged_or_destructive_commands(tmp_path):
    """Every command the checks run must be on a read-only allow-list."""
    runner = FakeRunner()
    dg.run_all(ctx(tmp_path, runner, disk_usage=lambda p: Usage(1, 0, 1)))
    allowed = {"nmcli", "apt-config", "systemctl", "journalctl", "/usr/lib/update-notifier/apt-check", "apt-get"}
    for call in runner.calls:
        assert call[0] in allowed, call
        assert not {"sudo", "pkexec", "rm", "install", "remove", "purge"} & set(call), call
        if call[0] == "apt-get":
            assert "-s" in call   # simulation only
        if call[0] == "systemctl":
            assert call[1] in ("show", "--failed")


def test_resolve_host_timeout(monkeypatch):
    import socket
    import time as _time

    monkeypatch.setattr(socket, "getaddrinfo", lambda *a: _time.sleep(2))
    t0 = _time.time()
    assert dg.resolve_host("example.invalid", timeout=0.2) is False
    assert _time.time() - t0 < 1.5


def test_real_system_run_completes():
    results = dg.run_all(dg.Context())
    assert len(results) == len(dg.CHECKS)
    assert all(r.status in dg.SEVERITY for r in results)
