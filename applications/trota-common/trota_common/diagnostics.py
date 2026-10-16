"""Non-destructive health checks for Trota Diagnostics.

Design rules (see docs/security.md):

* every check is read-only: no file is deleted, no configuration is changed,
  nothing is "repaired" automatically;
* no check needs administrator privileges; when a source is not readable as a
  normal user, the check says so instead of asking for a password;
* suggestions are cautious and point to the standard Ubuntu tools;
* a failing check never stops the others.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from .i18n import _, ngettext
from .runner import Runner, run
from .sysinfo import format_bytes

OK, INFO, WARNING, ERROR, SKIPPED = "ok", "info", "warning", "error", "skipped"
SEVERITY = {OK: 0, SKIPPED: 0, INFO: 1, WARNING: 2, ERROR: 3}

# Services whose state is reported.  "required" ones are expected to run on
# every Trota OS installation; the others are only reported when present.
SERVICES = (
    ("NetworkManager.service", True),
    ("systemd-resolved.service", True),
    ("apparmor.service", True),
    ("unattended-upgrades.service", True),
    ("gdm.service", False),
    ("cups.service", False),
    ("bluetooth.service", False),
    ("snapd.service", False),
)


@dataclass
class CheckResult:
    id: str
    title: str
    status: str
    summary: str
    details: list[str] = field(default_factory=list)
    suggestion: str = ""


@dataclass
class Context:
    """Everything a check reads from the system, injectable for tests."""

    runner: Runner = run
    disk_usage: Callable = shutil.disk_usage
    root: Path = Path("/")
    now: Callable[[], float] = time.time
    kernel_release: str = field(default_factory=lambda: os.uname().release)
    resolve: Callable[[str], bool] | None = None

    def path(self, p: str) -> Path:
        return self.root / p.lstrip("/")


# --- individual checks -----------------------------------------------------
def check_disk_space(ctx: Context) -> CheckResult:
    paths = ["/"]
    home = os.path.expanduser("~")
    if home not in ("/", "~"):
        paths.append(home)
    details, worst = [], OK
    seen = set()
    for p in paths:
        try:
            u = ctx.disk_usage(p)
        except OSError as exc:
            details.append(_("{path}: cannot be read ({error})").format(path=p, error=exc.strerror or exc))
            continue
        key = (u.total, u.free)
        if key in seen:
            continue
        seen.add(key)
        free_pct = 100.0 * u.free / u.total if u.total else 100.0
        if u.free < 1 * 1024**3 or free_pct < 3:
            state = ERROR
        elif u.free < 5 * 1024**3 or free_pct < 10:
            state = WARNING
        else:
            state = OK
        worst = max(worst, state, key=SEVERITY.get)
        details.append(
            _("{path}: {free} free of {total} ({pct} free)").format(
                path=p, free=format_bytes(u.free), total=format_bytes(u.total), pct=f"{free_pct:.0f}%"
            )
        )
    summaries = {
        OK: _("There is enough free disk space."),
        WARNING: _("Free disk space is getting low."),
        ERROR: _("The disk is almost full."),
    }
    suggestion = ""
    if worst != OK:
        suggestion = _(
            "Use \"Disk Usage Analyzer\" to find large files, empty the Trash, "
            "and remove applications you no longer use. Updates may fail when the disk is full."
        )
    return CheckResult("disk", _("Disk space"), worst, summaries[worst], details, suggestion)


def check_network(ctx: Context) -> CheckResult:
    res = ctx.runner(["nmcli", "-t", "-f", "STATE,CONNECTIVITY", "general"], 10)
    title = _("Network")
    if res.missing:
        return CheckResult("network", title, SKIPPED, _("NetworkManager command line tool (nmcli) is not installed."))
    if not res.ok:
        return CheckResult("network", title, WARNING, _("Could not query NetworkManager."), [res.stderr.strip()],
                           _("Make sure the NetworkManager service is running."))
    state, _sep, connectivity = res.stdout.strip().partition(":")
    details = [_("NetworkManager state: {state}").format(state=state),
               _("Connectivity: {c}").format(c=connectivity or "unknown")]
    dev = ctx.runner(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device"], 10)
    if dev.ok:
        for line in dev.stdout.splitlines():
            parts = line.split(":")
            if len(parts) >= 3 and parts[1] not in ("loopback",):
                details.append(f"{parts[0]} ({parts[1]}): {parts[2]}")
    if ctx.resolve is not None:
        ok = ctx.resolve("archive.ubuntu.com")
        details.append(_("Name resolution of archive.ubuntu.com: {r}").format(r=_("working") if ok else _("failed")))
    if connectivity == "full":
        return CheckResult("network", title, OK, _("Connected to the Internet."), details)
    if state.startswith("connected") or connectivity in ("limited", "portal"):
        return CheckResult("network", title, WARNING, _("Connected, but Internet access is limited."), details,
                           _("If you are on a public network, open the browser to complete the login page (captive portal)."))
    return CheckResult("network", title, WARNING, _("Not connected to a network."), details,
                       _("Open Settings → Network or Wi-Fi to connect."))


def check_kernel(ctx: Context) -> CheckResult:
    running = ctx.kernel_release
    details = [_("Running kernel: {k}").format(k=running)]
    installed = []
    try:
        for p in ctx.path("/boot").glob("vmlinuz-*"):
            installed.append(p.name[len("vmlinuz-"):])
    except OSError:
        pass
    installed.sort(key=_version_key)
    if installed:
        details.append(_("Installed kernels: {k}").format(k=", ".join(installed)))
    tainted = (_read(ctx.path("/proc/sys/kernel/tainted")) or "0").strip()
    if tainted not in ("", "0"):
        details.append(_("Kernel taint flags: {t} (normal with proprietary or out-of-tree drivers)").format(t=tainted))
    reboot = ctx.path("/var/run/reboot-required")
    if reboot.exists():
        pkgs = (_read(ctx.path("/var/run/reboot-required.pkgs")) or "").split()
        if pkgs:
            details.append(_("Requested by: {p}").format(p=", ".join(sorted(set(pkgs)))))
        return CheckResult("kernel", _("Kernel"), WARNING, _("A restart is required to complete updates."), details,
                           _("Save your work and restart the computer."))
    if installed and running not in installed:
        return CheckResult("kernel", _("Kernel"), INFO, _("The running kernel is not among the installed ones."), details,
                           _("This is normal in the live session. On an installed system, restart to use the current kernel."))
    if installed and _version_key(installed[-1]) > _version_key(running):
        return CheckResult("kernel", _("Kernel"), INFO, _("A newer kernel is installed."), details,
                           _("Restart the computer to start using it."))
    return CheckResult("kernel", _("Kernel"), OK, _("Running the latest installed kernel."), details)


def check_security(ctx: Context) -> CheckResult:
    details, status = [], OK
    enabled = (_read(ctx.path("/sys/module/apparmor/parameters/enabled")) or "").strip()
    if enabled == "Y":
        details.append(_("AppArmor: enabled"))
    else:
        details.append(_("AppArmor: not enabled"))
        status = WARNING
    res = ctx.runner(["apt-config", "dump", "APT::Periodic"], 10)
    if res.ok:
        conf = dict(re.findall(r'^(APT::Periodic::[\w-]+) "([^"]*)";', res.stdout, re.M))
        lists = conf.get("APT::Periodic::Update-Package-Lists", "0")
        unattended = conf.get("APT::Periodic::Unattended-Upgrade", "0")
        details.append(_("Automatic update check: {v}").format(v=_("on") if lists != "0" else _("off")))
        details.append(_("Automatic security updates: {v}").format(v=_("on") if unattended != "0" else _("off")))
        if unattended == "0" or lists == "0":
            status = WARNING
    else:
        details.append(_("APT configuration could not be read."))
    ufw = _read(ctx.path("/etc/ufw/ufw.conf")) or ""
    if re.search(r"^ENABLED=yes", ufw, re.M):
        details.append(_("Firewall (ufw): enabled"))
    elif ufw:
        details.append(_("Firewall (ufw): installed, not enabled (no service listens on the network by default)"))
    summary = _("Security features are active.") if status == OK else _("Some security features are not active.")
    suggestion = "" if status == OK else _(
        "Open \"Software & Updates\" → Updates and enable automatic security updates. "
        "AppArmor should never be disabled on Trota OS."
    )
    return CheckResult("security", _("Security"), status, summary, details, suggestion)


def check_services(ctx: Context) -> CheckResult:
    title = _("System services")
    names = [s for s, _required in SERVICES]
    res = ctx.runner(["systemctl", "show", "--property=Id,LoadState,ActiveState,SubState", *names], 15)
    if res.missing:
        return CheckResult("services", title, SKIPPED, _("systemctl is not available."))
    if not res.ok and "Id=" not in res.stdout:
        return CheckResult("services", title, SKIPPED, _("The service manager could not be queried."),
                           [line for line in res.stderr.strip().splitlines()[:2]])
    states: dict[str, dict] = {}
    for block in res.stdout.strip().split("\n\n"):
        props = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
        if "Id" in props:
            states[props["Id"]] = props
    details, status, problems = [], OK, []
    for name, required in SERVICES:
        p = states.get(name)
        if not p or p.get("LoadState") == "not-found":
            if required:
                details.append(_("{name}: not installed").format(name=name))
                problems.append(name)
            continue
        active = p.get("ActiveState", "unknown")
        details.append(f"{name}: {active} ({p.get('SubState', '')})")
        if required and active not in ("active", "activating", "reloading"):
            problems.append(name)
    failed = ctx.runner(["systemctl", "--failed", "--no-legend", "--plain", "--no-pager"], 15)
    failed_units = [line.split()[0] for line in failed.stdout.splitlines() if line.strip()] if failed.ok else []
    if failed_units:
        details.append(_("Failed units: {u}").format(u=", ".join(failed_units)))
    if problems:
        status = ERROR if "NetworkManager.service" in problems else WARNING
    elif failed_units:
        status = WARNING
    if status == OK:
        summary = _("Core services are running.")
        suggestion = ""
    else:
        summary = ngettext("{n} service needs attention.", "{n} services need attention.",
                           len(problems) + len(failed_units)).format(n=len(problems) + len(failed_units))
        suggestion = _("Inspect a service with: systemctl status <name>. Use \"Logs\" to read its messages.")
    return CheckResult("services", title, status, summary, details, suggestion)


def check_logs(ctx: Context) -> CheckResult:
    title = _("Recent errors in the system log")
    res = ctx.runner(["journalctl", "-b", "-p", "err", "-q", "--no-pager", "-o", "short-iso", "-n", "200"], 20)
    if res.missing:
        return CheckResult("logs", title, SKIPPED, _("journalctl is not available."))
    if not res.ok and not res.stdout:
        return CheckResult("logs", title, SKIPPED, _("The system log could not be read."), [res.stderr.strip()])
    lines = [line for line in res.stdout.splitlines() if line.strip()]
    restricted = "not seeing messages from other users and the system" in (res.stderr or "")
    details = lines[-8:]
    if restricted:
        details.insert(0, _("Only your own messages are visible: members of the \"adm\" group can read the full system log."))
    if not lines:
        return CheckResult("logs", title, OK, _("No errors logged since the last boot."), details)
    status = INFO if len(lines) < 20 else WARNING
    summary = ngettext("{n} error message since the last boot.", "{n} error messages since the last boot.",
                       len(lines)).format(n=len(lines))
    return CheckResult("logs", title, status, summary, details,
                       _("Some errors are harmless (hardware probing, optional drivers). Open \"Logs\" for details "
                         "and include them when you report a problem."))


def check_updates(ctx: Context) -> CheckResult:
    title = _("Software updates")
    details = []
    stamp = ctx.path("/var/lib/apt/periodic/update-success-stamp")
    lists_dir = ctx.path("/var/lib/apt/lists")
    last = None
    for p in (stamp, lists_dir):
        try:
            last = p.stat().st_mtime
            break
        except OSError:
            continue
    stale = False
    if last is not None:
        days = (ctx.now() - last) / 86400
        details.append(ngettext("Package lists refreshed {n} day ago.", "Package lists refreshed {n} days ago.",
                                int(days)).format(n=int(days)))
        stale = days > 7
    res = ctx.runner(["/usr/lib/update-notifier/apt-check"], 60)
    total = security = None
    if res.ok or (res.returncode == 0 and res.stderr):
        m = re.search(r"(\d+);(\d+)", res.stderr + res.stdout)
        if m:
            total, security = int(m.group(1)), int(m.group(2))
    if total is None:
        sim = ctx.runner(["apt-get", "-s", "-o", "Debug::NoLocking=1", "upgrade"], 60)
        if sim.ok:
            inst = [line for line in sim.stdout.splitlines() if line.startswith("Inst ")]
            total = len(inst)
            security = sum(1 for line in inst if "-security" in line)
    if total is None:
        return CheckResult("updates", title, SKIPPED, _("Update information is not available."), details)
    details.append(_("Updates available: {t} (security: {s})").format(t=total, s=security))
    if security:
        status, summary = WARNING, ngettext("{n} security update is available.", "{n} security updates are available.",
                                            security).format(n=security)
    elif total:
        status, summary = INFO, ngettext("{n} update is available.", "{n} updates are available.", total).format(n=total)
    else:
        status, summary = OK, _("The system is up to date.")
    if stale:
        status = max(status, WARNING, key=SEVERITY.get)
        summary += " " + _("Package lists are more than a week old.")
    suggestion = _("Open \"Software Updater\" to install updates.") if status != OK else ""
    return CheckResult("updates", title, status, summary, details, suggestion)


CHECKS: tuple[Callable[[Context], CheckResult], ...] = (
    check_disk_space,
    check_network,
    check_kernel,
    check_security,
    check_services,
    check_logs,
    check_updates,
)


def run_check(check: Callable[[Context], CheckResult], ctx: Context) -> CheckResult:
    try:
        return check(ctx)
    except Exception as exc:  # a broken check must never stop the others
        name = check.__name__.removeprefix("check_")
        return CheckResult(name, name, ERROR, _("The check could not run."), [f"{type(exc).__name__}: {exc}"],
                           _("Please report this problem to the Trota OS developers."))


def run_all(ctx: Context | None = None, checks=CHECKS) -> list[CheckResult]:
    ctx = ctx or Context()
    return [run_check(c, ctx) for c in checks]


def overall_status(results: list[CheckResult]) -> str:
    return max((r.status for r in results), key=SEVERITY.get, default=OK)


def to_json(results: list[CheckResult]) -> str:
    return json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False)


# --- helpers ---------------------------------------------------------------
def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _version_key(v: str):
    # (0, int) sorts before (1, str): never compares int with str.
    return [(0, int(x)) if x.isdigit() else (1, x) for x in re.split(r"[.\-+~]", v)]


def resolve_host(host: str, timeout: float = 5.0) -> bool:
    """DNS lookup with a timeout (getaddrinfo itself has none)."""
    import socket
    import threading

    result = {"ok": False}

    def worker():
        try:
            socket.getaddrinfo(host, 443)
            result["ok"] = True
        except OSError:
            pass

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout)
    return result["ok"]
