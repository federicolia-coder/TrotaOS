"""Local system information for Trota System Info and Trota Welcome.

Everything is read from /proc, /sys, the os-release files and a few
read-only commands.  Nothing is sent anywhere: there is no network access in
this module.  Every collector is fault tolerant and returns ``None`` / empty
values instead of raising, so a partially readable system (containers, live
sessions, unusual hardware) still produces a report.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import osinfo
from .runner import Runner, run

# Filesystems shown in the "Storage" section; pseudo and image filesystems
# (squashfs of snaps, tmpfs, overlay of containers...) are skipped except "/".
REAL_FS = {"ext2", "ext3", "ext4", "btrfs", "xfs", "f2fs", "vfat", "exfat", "ntfs", "ntfs3", "zfs", "jfs", "reiserfs"}


@dataclass
class CPUInfo:
    model: str = "Unknown"
    logical_cpus: int = 0
    physical_cores: int | None = None
    max_mhz: float | None = None


@dataclass
class MemoryInfo:
    total_bytes: int = 0
    available_bytes: int = 0
    swap_total_bytes: int = 0
    swap_free_bytes: int = 0


@dataclass
class DiskInfo:
    mountpoint: str
    device: str
    fstype: str
    total_bytes: int
    used_bytes: int
    free_bytes: int

    @property
    def used_percent(self) -> float:
        return 100.0 * self.used_bytes / self.total_bytes if self.total_bytes else 0.0


@dataclass
class NetInterface:
    name: str
    kind: str  # "ethernet", "wireless", "loopback", "virtual", "other"
    state: str
    mac: str = ""
    addresses: list[str] = field(default_factory=list)


@dataclass
class SystemReport:
    os_name: str
    os_version: str
    os_pretty_name: str
    base: str
    kernel: str
    architecture: str
    hostname: str
    uptime_seconds: float | None
    desktop: str
    session_type: str
    cpu: CPUInfo
    memory: MemoryInfo
    gpus: list[str]
    disks: list[DiskInfo]
    network: list[NetInterface]

    def to_dict(self) -> dict:
        d = asdict(self)
        for disk, src in zip(d["disks"], self.disks):
            disk["used_percent"] = round(src.used_percent, 1)
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


# --- helpers -----------------------------------------------------------------
def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def format_bytes(n: int | float | None) -> str:
    """Human readable size with binary prefixes: 1536 -> '1.5 KiB'."""
    if n is None:
        return "—"
    n = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if abs(n) < 1024 or unit == "PiB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PiB"  # pragma: no cover


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts = []
    if days:
        parts.append(f"{days} d")
    if hours or days:
        parts.append(f"{hours} h")
    parts.append(f"{minutes} min")
    return " ".join(parts)


# --- collectors ----------------------------------------------------------------
def cpu_info(proc: Path = Path("/proc"), sys_root: Path = Path("/sys")) -> CPUInfo:
    info = CPUInfo(logical_cpus=os.cpu_count() or 0)
    text = _read(proc / "cpuinfo") or ""
    cores = set()
    physical = core = None
    logical = 0
    for line in text.splitlines():
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if key == "processor":
            logical += 1
        elif key == "model name" and info.model == "Unknown":
            info.model = re.sub(r"\s+", " ", value)
        elif key == "physical id":
            physical = value
        elif key == "core id":
            core = value
        elif not line.strip():
            if core is not None:
                cores.add((physical, core))
            physical = core = None
    if core is not None:
        cores.add((physical, core))
    if logical:
        info.logical_cpus = logical
    info.physical_cores = len(cores) or None
    freq = _read(sys_root / "devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq")
    if freq and freq.strip().isdigit():
        info.max_mhz = int(freq.strip()) / 1000.0
    return info


def memory_info(proc: Path = Path("/proc")) -> MemoryInfo:
    values: dict[str, int] = {}
    for line in (_read(proc / "meminfo") or "").splitlines():
        m = re.match(r"(\w+):\s+(\d+)\s*kB", line)
        if m:
            values[m.group(1)] = int(m.group(2)) * 1024
    return MemoryInfo(
        total_bytes=values.get("MemTotal", 0),
        available_bytes=values.get("MemAvailable", values.get("MemFree", 0)),
        swap_total_bytes=values.get("SwapTotal", 0),
        swap_free_bytes=values.get("SwapFree", 0),
    )


def _unescape_mount(s: str) -> str:
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), s)


def disk_info(mounts_file: Path = Path("/proc/self/mounts"), usage=shutil.disk_usage) -> list[DiskInfo]:
    disks: list[DiskInfo] = []
    seen_devices: set[str] = set()
    for line in (_read(mounts_file) or "").splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        device, mountpoint, fstype = _unescape_mount(parts[0]), _unescape_mount(parts[1]), parts[2]
        if mountpoint != "/" and fstype not in REAL_FS:
            continue
        if mountpoint.startswith(("/snap/", "/var/snap/", "/run/", "/proc", "/sys", "/dev")):
            continue
        if device in seen_devices and mountpoint != "/":
            continue  # bind mounts of the same device
        try:
            u = usage(mountpoint)
        except OSError:
            continue
        seen_devices.add(device)
        disks.append(DiskInfo(mountpoint, device, fstype, u.total, u.used, u.free))
    disks.sort(key=lambda d: (d.mountpoint != "/", d.mountpoint))
    return disks


def _net_kind(name: str, iface_dir: Path) -> str:
    if name == "lo":
        return "loopback"
    if (iface_dir / "wireless").exists() or (iface_dir / "phy80211").exists():
        return "wireless"
    if not (iface_dir / "device").exists():
        return "virtual"
    if (_read(iface_dir / "type") or "").strip() == "1":
        return "ethernet"
    return "other"


def network_info(sys_net: Path = Path("/sys/class/net"), runner: Runner = run) -> list[NetInterface]:
    addresses: dict[str, list[str]] = {}
    res = runner(["ip", "-j", "addr", "show"], 5)
    if res.ok:
        try:
            for entry in json.loads(res.stdout or "[]"):
                addrs = [f"{a['local']}/{a.get('prefixlen', '')}" for a in entry.get("addr_info", []) if "local" in a]
                addresses[entry.get("ifname", "")] = addrs
        except (ValueError, TypeError, KeyError):
            pass
    result = []
    try:
        names = sorted(p.name for p in sys_net.iterdir())
    except OSError:
        names = sorted(addresses)
    for name in names:
        d = sys_net / name
        result.append(
            NetInterface(
                name=name,
                kind=_net_kind(name, d),
                state=(_read(d / "operstate") or "unknown").strip(),
                mac=(_read(d / "address") or "").strip(),
                addresses=addresses.get(name, []),
            )
        )
    return result


def gpu_info(runner: Runner = run) -> list[str]:
    res = runner(["lspci", "-mm"], 5)
    if not res.ok:
        return []
    gpus = []
    for line in res.stdout.splitlines():
        # lspci -mm: slot "class" "vendor" "device" ...
        fields = re.findall(r'"([^"]*)"', line)
        if len(fields) >= 3 and re.search(r"VGA|3D|Display", fields[0]):
            gpus.append(f"{fields[1]} {fields[2]}".strip())
    return gpus


def desktop_info(env=os.environ, runner: Runner = run) -> tuple[str, str]:
    desktop = env.get("XDG_CURRENT_DESKTOP", "") or env.get("DESKTOP_SESSION", "")
    session = env.get("XDG_SESSION_TYPE", "")
    if "GNOME" in desktop.upper():
        res = runner(["gnome-shell", "--version"], 5)
        if res.ok and res.stdout.strip():
            desktop = res.stdout.strip()  # e.g. "GNOME Shell 46.0"
    return desktop or "—", session or "—"


def uptime(proc: Path = Path("/proc")) -> float | None:
    text = _read(proc / "uptime")
    try:
        return float(text.split()[0]) if text else None
    except (ValueError, IndexError):
        return None


def collect(runner: Runner = run, root: str = "/") -> SystemReport:
    rel = osinfo.release_info(root)
    desktop, session = desktop_info(runner=runner)
    uname = platform.uname()
    return SystemReport(
        os_name=rel.name,
        os_version=rel.version,
        os_pretty_name=rel.pretty_name,
        base=rel.base_description,
        kernel=uname.release,
        architecture=uname.machine,
        hostname=uname.node,
        uptime_seconds=uptime(),
        desktop=desktop,
        session_type=session,
        cpu=cpu_info(),
        memory=memory_info(),
        gpus=gpu_info(runner),
        disks=disk_info(),
        network=network_info(runner=runner),
    )


def report_text(r: SystemReport) -> str:
    """Plain-text report, suitable for a terminal or a bug report."""
    lines = [
        f"Operating system : {r.os_pretty_name}",
        f"Based on         : {r.base or '—'}",
        f"Kernel           : {r.kernel}",
        f"Architecture     : {r.architecture}",
        f"Hostname         : {r.hostname}",
        f"Uptime           : {format_duration(r.uptime_seconds)}",
        f"Desktop          : {r.desktop} ({r.session_type})",
        f"CPU              : {r.cpu.model} — {r.cpu.logical_cpus} threads"
        + (f", {r.cpu.physical_cores} cores" if r.cpu.physical_cores else ""),
        f"Memory           : {format_bytes(r.memory.total_bytes)} total, {format_bytes(r.memory.available_bytes)} available",
        f"Swap             : {format_bytes(r.memory.swap_total_bytes)}",
    ]
    for g in r.gpus or ["—"]:
        lines.append(f"Graphics         : {g}")
    for d in r.disks:
        lines.append(
            f"Disk {d.mountpoint:<11} : {format_bytes(d.used_bytes)} used of {format_bytes(d.total_bytes)}"
            f" ({d.used_percent:.0f}%), {d.fstype} on {d.device}"
        )
    for n in r.network:
        if n.kind == "loopback":
            continue
        addrs = ", ".join(n.addresses) or "no address"
        lines.append(f"Network {n.name:<8} : {n.kind}, {n.state}, {addrs}")
    return "\n".join(lines)
