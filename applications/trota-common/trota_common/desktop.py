"""Launch desktop applications, settings panels and documents.

Each target lists alternatives (desktop file IDs or commands); the first one
available on the system is used.  Buttons in the UI are disabled when no
alternative exists, so no button is ever "decorative".
"""

from __future__ import annotations

from dataclasses import dataclass

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402


@dataclass(frozen=True)
class Target:
    desktop_ids: tuple[str, ...] = ()
    commands: tuple[tuple[str, ...], ...] = ()

    def resolve(self):
        """Return a Gio.AppInfo or a command tuple, or None if unavailable."""
        for did in self.desktop_ids:
            try:
                info = Gio.DesktopAppInfo.new(did)
            except TypeError:  # pragma: no cover - older PyGObject
                info = None
            if info is not None:
                return info
        for cmd in self.commands:
            if GLib.find_program_in_path(cmd[0]):
                return cmd
        return None

    @property
    def available(self) -> bool:
        return self.resolve() is not None

    def launch(self) -> None:
        """Start the target. Raises GLib.Error / OSError / LookupError on failure."""
        resolved = self.resolve()
        if resolved is None:
            raise LookupError("not installed")
        if isinstance(resolved, Gio.AppInfo):
            resolved.launch([], None)
        else:
            Gio.Subprocess.new(list(resolved), Gio.SubprocessFlags.NONE)


def settings_panel(panel: str) -> Target:
    return Target(commands=(("gnome-control-center", panel),))


TARGETS: dict[str, Target] = {
    "settings": Target(("org.gnome.Settings.desktop", "gnome-control-center.desktop")),
    "appearance": settings_panel("ubuntu"),
    "background": settings_panel("background"),
    "display": settings_panel("display"),
    "network": settings_panel("network"),
    "wifi": settings_panel("wifi"),
    "accessibility": settings_panel("universal-access"),
    "privacy": settings_panel("privacy"),
    "users": settings_panel("users"),
    "updates": Target(("update-manager.desktop",), (("update-manager",),)),
    "software_sources": Target(("software-properties-gtk.desktop",), (("software-properties-gtk",),)),
    "drivers": Target(("software-properties-drivers.desktop",), (("software-properties-gtk", "--open-tab=4"),)),
    "app_center": Target(("org.gnome.Software.desktop", "snap-store_snap-store.desktop", "io.snapcraft.Store.desktop")),
    "help": Target(("yelp.desktop",), (("yelp",),)),
    "terminal": Target(("org.gnome.Terminal.desktop",)),
    "files": Target(("org.gnome.Nautilus.desktop",)),
    "system_monitor": Target(("org.gnome.SystemMonitor.desktop", "gnome-system-monitor.desktop")),
    "disks": Target(("org.gnome.DiskUtility.desktop",)),
    "disk_usage": Target(("org.gnome.baobab.desktop",)),
    "logs": Target(("org.gnome.Logs.desktop",)),
    "browser": Target(("firefox.desktop", "firefox_firefox.desktop")),
    "trota_welcome": Target(("it.testardstudios.TrotaWelcome.desktop",)),
    "trota_system_info": Target(("it.testardstudios.TrotaSystemInfo.desktop",)),
    "trota_diagnostics": Target(("it.testardstudios.TrotaDiagnostics.desktop",)),
    "trota_package_helper": Target(("it.testardstudios.TrotaPackageHelper.desktop",)),
}


def launch(name: str) -> None:
    TARGETS[name].launch()


def available(name: str) -> bool:
    return TARGETS[name].available


def open_uri(uri: str) -> None:
    """Open a URI (web page or local file) with the default application."""
    Gio.AppInfo.launch_default_for_uri(uri, None)


def local_docs_uri() -> str | None:
    """Offline HTML documentation installed by the trota-docs package."""
    path = "/usr/share/doc/trota-docs/html/index.html"
    return GLib.filename_to_uri(path, None) if GLib.file_test(path, GLib.FileTest.EXISTS) else None
