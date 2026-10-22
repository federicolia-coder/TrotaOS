"""Read-only checks of a PC for virtual reality, and the optional VR software.

Everything the checks read comes through a Context (command runner, file
system root, home directory), so the tests can feed them recorded output.
Installing WiVRn or Steam is the only action that changes the system, and it
only runs when the user asks for it (Flatpak asks for the password itself).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from trota_common import runner as _runner
from trota_common.diagnostics import CheckResult
from trota_common.i18n import _

OK, INFO, WARNING, ERROR = "ok", "info", "warning", "error"

# USB vendors of PC VR headsets (lsusb). Standalone headsets (Meta Quest, Pico)
# are used over Wi-Fi with WiVRn, so they are not expected here.
HEADSET_VENDORS = {
    "28de": "Valve (Index, lighthouse devices)",
    "0bb4": "HTC (Vive)",
    "2833": "Oculus / Meta",
    "35bd": "Bigscreen (Beyond)",
}


@dataclass(frozen=True)
class App:
    key: str
    flatpak_id: str
    name: str
    purpose: str


APPS = (
    App("wivrn", "io.github.wivrn.wivrn", "WiVRn",
        _("Play PC VR on Meta Quest, Pico and other standalone headsets, over Wi-Fi")),
    App("steam", "com.valvesoftware.Steam", "Steam",
        _("SteamVR and VR games, for PC headsets such as Valve Index and HTC Vive")),
)

# Ports used by WiVRn (open them only if a firewall is active).
WIVRN_PORTS = ("9757/tcp", "9757/udp")


@dataclass
class Context:
    runner: _runner.Runner = _runner.run
    root: Path = Path("/")
    home: Path = field(default_factory=Path.home)

    def path(self, p: str) -> Path:
        return self.root / p.lstrip("/")


# --- graphics card -------------------------------------------------------------
@dataclass
class Gpu:
    name: str
    vendor: str
    driver: str


def parse_lspci(text: str) -> list[Gpu]:
    """GPUs and their kernel driver from `lspci -nnk`."""
    gpus, current = [], None
    for line in text.splitlines():
        if line and not line[0].isspace():
            current = None
            m = re.match(r"\S+ (?:VGA compatible controller|3D controller|Display controller) \[03\d\d\]: (.+?) \[([0-9a-f]{4}):[0-9a-f]{4}\]", line)
            if m:
                current = Gpu(m.group(1), m.group(2), "")
                gpus.append(current)
        elif current is not None and "Kernel driver in use:" in line:
            current.driver = line.split(":", 1)[1].strip()
    return gpus


def check_gpu(ctx: Context) -> CheckResult:
    title = _("Graphics card")
    r = ctx.runner(("lspci", "-nnk"), 15)
    if not r.ok:
        return CheckResult("gpu", title, WARNING, _("Could not read the graphics cards (lspci)."))
    gpus = parse_lspci(r.stdout)
    if not gpus:
        return CheckResult("gpu", title, WARNING, _("No graphics card found."))
    details = [f"{g.name} — {_('driver')}: {g.driver or _('none')}" for g in gpus]
    nvidia_open = [g for g in gpus if g.vendor == "10de" and g.driver != "nvidia"]
    if nvidia_open:
        return CheckResult("gpu", title, WARNING, _("NVIDIA card without the NVIDIA driver."), details,
                           _("Install the recommended NVIDIA driver from Additional Drivers and restart: "
                             "VR needs it for good performance."))
    if any(g.vendor in ("10de", "1002") for g in gpus):
        return CheckResult("gpu", title, OK, _("Dedicated graphics card ready for VR."), details)
    return CheckResult("gpu", title, WARNING, _("Only integrated graphics."), details,
                       _("Enough to try WiVRn with simple apps, too slow for most VR games. "
                         "A recent AMD or NVIDIA card is recommended."))


# --- Vulkan --------------------------------------------------------------------
def parse_vulkaninfo(text: str) -> list[tuple[str, str]]:
    """(deviceName, deviceType) pairs from `vulkaninfo --summary`."""
    names = re.findall(r"deviceName\s*=\s*(.+)", text)
    types = re.findall(r"deviceType\s*=\s*(\S+)", text)
    return [(n.strip(), t.replace("PHYSICAL_DEVICE_TYPE_", "")) for n, t in zip(names, types)]


def check_vulkan(ctx: Context) -> CheckResult:
    title = _("Vulkan")
    r = ctx.runner(("vulkaninfo", "--summary"), 30)
    if r.missing:
        return CheckResult("vulkan", title, ERROR, _("vulkaninfo is not installed."), [],
                           _("Install the vulkan-tools package."))
    devices = parse_vulkaninfo(r.stdout)
    hw = [d for d in devices if d[1] != "CPU"]
    details = [f"{n} ({t.lower().replace('_', ' ')})" for n, t in devices]
    if not hw:
        return CheckResult("vulkan", title, ERROR, _("No graphics card supports Vulkan."), details,
                           _("VR runtimes need Vulkan: install the graphics driver, then check again."))
    return CheckResult("vulkan", title, OK, _("Vulkan works on {device}.").format(device=hw[0][0]), details)


# --- headsets ------------------------------------------------------------------
def check_headset(ctx: Context) -> CheckResult:
    title = _("PC VR headset")
    r = ctx.runner(("lsusb",), 15)
    found = []
    for line in r.stdout.splitlines():
        m = re.search(r"ID ([0-9a-f]{4}):([0-9a-f]{4})\s*(.*)", line)
        if m and m.group(1) in HEADSET_VENDORS:
            found.append(m.group(3).strip() or HEADSET_VENDORS[m.group(1)])
    if found:
        return CheckResult("headset", title, OK, _("Headset devices connected."), sorted(set(found)))
    return CheckResult("headset", title, INFO, _("No PC VR headset connected by USB."), [],
                       _("Standalone headsets (Meta Quest, Pico) connect over Wi-Fi with WiVRn."))


# --- OpenXR runtime ------------------------------------------------------------
def runtime_files(ctx: Context) -> list[Path]:
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(ctx.home / ".config")
    return [Path(xdg) / "openxr/1/active_runtime.json",
            ctx.path("/etc/xdg/openxr/1/active_runtime.json"),
            ctx.path("/usr/share/openxr/1/active_runtime.json")]


def runtime_name(data: dict, path: Path) -> str:
    rt = data.get("runtime", {}) if isinstance(data, dict) else {}
    text = f"{rt.get('name', '')} {rt.get('library_path', '')} {path}".lower()
    for key, name in (("wivrn", "WiVRn"), ("steamvr", "SteamVR"), ("monado", "Monado")):
        if key in text:
            return name
    return rt.get("name") or str(rt.get("library_path", "?"))


def check_runtime(ctx: Context) -> CheckResult:
    title = _("OpenXR runtime")
    for p in runtime_files(ctx):
        try:
            data = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        return CheckResult("runtime", title, OK, _("Active runtime: {name}.").format(name=runtime_name(data, p)),
                           [str(p)])
    return CheckResult("runtime", title, WARNING, _("No OpenXR runtime is active."), [],
                       _("Start WiVRn or SteamVR once, or install the monado-service package."))


# --- device permissions --------------------------------------------------------
def check_udev(ctx: Context) -> CheckResult:
    title = _("Headset permissions")
    rules = []
    for d in ("/usr/lib/udev/rules.d", "/lib/udev/rules.d", "/etc/udev/rules.d"):
        try:
            rules += [f.name for f in ctx.path(d).iterdir()]
        except OSError:
            pass
    xr = any("xrhardware" in n or "xr-hardware" in n for n in rules)
    steam = any("steam" in n for n in rules)
    details = [f"xr-hardware: {_('yes') if xr else _('no')}", f"steam-devices: {_('yes') if steam else _('no')}"]
    if xr and steam:
        return CheckResult("udev", title, OK, _("Headsets and controllers can be used without root."), details)
    return CheckResult("udev", title, WARNING, _("Some device rules are missing."), details,
                       _("Install the xr-hardware and steam-devices packages, then reconnect the headset."))


# --- network for WiVRn ---------------------------------------------------------
def parse_nmcli_devices(text: str) -> list[tuple[str, str, str]]:
    """(device, type, state) from `nmcli -t -f DEVICE,TYPE,STATE device`."""
    out = []
    for line in text.splitlines():
        parts = line.split(":")
        if len(parts) >= 3:
            out.append((parts[0], parts[1], parts[2]))
    return out


def check_network(ctx: Context) -> CheckResult:
    title = _("Network for WiVRn")
    r = ctx.runner(("nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device"), 15)
    if not r.ok:
        return CheckResult("network", title, INFO, _("Could not read the network connections."))
    up = [(d, t) for d, t, s in parse_nmcli_devices(r.stdout) if s == "connected" and t in ("ethernet", "wifi")]
    if not up:
        return CheckResult("network", title, WARNING, _("Not connected to a network."), [],
                           _("Standalone headsets stream from the PC over the local network: connect the PC "
                             "to the router, by cable if possible."))
    details = []
    for dev, _type in up:
        a = ctx.runner(("nmcli", "-t", "-g", "IP4.ADDRESS", "device", "show", dev), 15)
        ips = [x.split("/")[0] for x in a.stdout.replace("|", "\n").split() if x] if a.ok else []
        details.append(f"{dev} ({_type}): {', '.join(ips) or '-'}")
    if any(t == "ethernet" for _d, t in up):
        return CheckResult("network", title, OK, _("PC connected by cable: best for streaming."), details)
    w = ctx.runner(("nmcli", "-t", "-f", "ACTIVE,FREQ", "device", "wifi", "list", "--rescan", "no"), 15)
    freqs = [int(m) for line in w.stdout.splitlines() if line.startswith("yes:")
             for m in re.findall(r"(\d{4})", line)]
    if freqs and max(freqs) < 3000:
        return CheckResult("network", title, WARNING, _("Wi-Fi at 2.4 GHz: too slow for VR streaming."), details,
                           _("Connect the PC by cable, or use the 5 GHz network of the router; the headset "
                             "should be on 5 GHz (or 6 GHz) too."))
    return CheckResult("network", title, OK, _("Wi-Fi connected."), details,
                       _("For the smoothest image connect the PC to the router by cable and keep the "
                         "headset on 5 GHz Wi-Fi."))


# --- firewall --------------------------------------------------------------------
FIREWALL_COMMAND = ("pkexec", "ufw", "allow", "WiVRn")


def check_firewall(ctx: Context) -> CheckResult:
    title = _("Firewall")
    r = ctx.runner(("systemctl", "is-active", "ufw"), 10)
    active = r.stdout.strip() == "active"
    if not active:
        return CheckResult("firewall", title, OK, _("No firewall is blocking WiVRn."))
    return CheckResult("firewall", title, INFO, _("The firewall is on: WiVRn needs its ports open."),
                       ["9757/tcp", "9757/udp"],
                       _("Use \"Open WiVRn ports\" below, or run: sudo ufw allow WiVRn"))


def open_firewall(ctx: Context | None = None) -> _runner.CommandResult:
    """Allow the WiVRn ufw profile (asks for the administrator password)."""
    ctx = ctx or Context()
    return ctx.runner(FIREWALL_COMMAND, 300)


# --- VR software ---------------------------------------------------------------
def installed_apps(ctx: Context) -> set[str]:
    r = ctx.runner(("flatpak", "list", "--app", "--columns=application"), 20)
    return {line.strip() for line in r.stdout.splitlines() if line.strip()} if r.ok else set()


def check_software(ctx: Context) -> CheckResult:
    title = _("VR software")
    have = installed_apps(ctx)
    details = [f"{a.name}: {_('installed') if a.flatpak_id in have else _('not installed')}" for a in APPS]
    if any(a.flatpak_id in have for a in APPS):
        return CheckResult("software", title, OK, _("VR software installed."), details)
    return CheckResult("software", title, INFO, _("No VR software installed yet."), details,
                       _("Install WiVRn for standalone headsets or Steam for PC headsets."))


CHECKS = (check_gpu, check_vulkan, check_headset, check_runtime, check_udev, check_network, check_firewall,
          check_software)


def run_all(ctx: Context | None = None) -> list[CheckResult]:
    ctx = ctx or Context()
    out = []
    for check in CHECKS:
        try:
            out.append(check(ctx))
        except Exception as exc:  # one broken check must not hide the others
            out.append(CheckResult(check.__name__, check.__name__, "skipped", str(exc)))
    return out


def install_command(app: App) -> tuple[str, ...]:
    return ("flatpak", "install", "--system", "-y", "--noninteractive", "flathub", app.flatpak_id)


def install(app: App, ctx: Context | None = None) -> _runner.CommandResult:
    """Install *app* from Flathub. Flatpak asks for the administrator password."""
    ctx = ctx or Context()
    return ctx.runner(install_command(app), 1800)


def find_app(key: str) -> App:
    for a in APPS:
        if a.key == key:
            return a
    raise KeyError(key)
