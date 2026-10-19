"""The status report sent at every check-in.

Only what the panel shows is collected: system and edition, uptime, load,
memory, root disk, addresses, pending updates and, on the kiosk, the page on
screen. No file contents, user names or logs leave the device.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

from trota_fleet_agent import __version__
from trota_fleet_agent.config import read_conf

ROOT = Path("/")
# Pending updates come from a simulated upgrade, which takes a few seconds:
# it is repeated at most once an hour.
UPDATES_EVERY = 3600
_updates_cache: dict = {}


def run(args, timeout=60) -> tuple[int | None, str]:
    """Run a command without a shell; (exit code, output). None if missing."""
    if shutil.which(args[0]) is None:
        return None, ""
    env = dict(os.environ, LC_ALL="C.UTF-8", LANG="C.UTF-8")
    try:
        p = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=timeout,
                           env=env, stdin=subprocess.DEVNULL, check=False)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return None, str(exc)
    return p.returncode, (p.stdout + p.stderr)


def edition(root: Path = ROOT) -> str:
    try:
        name = (root / "etc/trota-edition").read_text().strip()
    except OSError:
        name = ""
    if name:
        return name
    if (root / "usr/lib/trota-kiosk").is_dir():
        return "kiosk"
    return "server"


def os_name(root: Path = ROOT) -> str:
    v = read_conf(root / "etc/os-release") or read_conf(root / "usr/lib/os-release")
    return v.get("PRETTY_NAME", "Linux")


def uptime(root: Path = ROOT) -> int:
    try:
        return int(float((root / "proc/uptime").read_text().split()[0]))
    except (OSError, ValueError, IndexError):
        return 0


def load(root: Path = ROOT) -> float:
    try:
        return float((root / "proc/loadavg").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return 0.0


def memory(root: Path = ROOT) -> dict:
    info = {}
    try:
        for line in (root / "proc/meminfo").read_text().splitlines():
            key, _, rest = line.partition(":")
            if key in ("MemTotal", "MemAvailable"):
                info[key] = int(rest.split()[0]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return {"total": info.get("MemTotal", 0), "available": info.get("MemAvailable", 0)}


def disk(path: str = "/") -> dict:
    try:
        u = shutil.disk_usage(path)
    except OSError:
        return {"total": 0, "used": 0}
    return {"total": u.total, "used": u.used}


def addresses() -> list[str]:
    code, out = run(["ip", "-j", "addr", "show", "scope", "global"], timeout=10)
    if code != 0:
        return []
    try:
        links = json.loads(out)
    except ValueError:
        return []
    return [f"{a['local']}" for link in links for a in link.get("addr_info", []) if a.get("local")]


def pending_updates(now: float | None = None) -> int | None:
    now = time.time() if now is None else now
    if now - _updates_cache.get("at", 0) < UPDATES_EVERY:
        return _updates_cache.get("count")
    code, out = run(["apt-get", "-s", "-o", "Debug::NoLocking=1", "upgrade"], timeout=300)
    count = sum(1 for line in out.splitlines() if line.startswith("Inst ")) if code == 0 else None
    _updates_cache.update(at=now, count=count)
    return count


def kiosk(root: Path = ROOT) -> dict | None:
    if not (root / "usr/lib/trota-kiosk").is_dir():
        return None
    code, out = run(["systemctl", "is-active", "trota-kiosk.service"], timeout=10)
    return {"url": read_conf(root / "etc/trota-kiosk.conf").get("TROTA_KIOSK_URL", ""),
            "active": out.strip() == "active"}


def collect(root: Path = ROOT) -> dict:
    return {
        "agent": __version__,
        "hostname": socket.gethostname(),
        "os": os_name(root),
        "edition": edition(root),
        "kernel": os.uname().release,
        "uptime": uptime(root),
        "load": load(root),
        "memory": memory(root),
        "disk": disk(str(root)),
        "addresses": addresses(),
        "updates": pending_updates(),
        "reboot_required": (root / "run/reboot-required").exists(),
        "kiosk": kiosk(root),
    }
