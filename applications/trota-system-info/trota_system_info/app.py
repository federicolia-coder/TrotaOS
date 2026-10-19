"""Trota System Info main window."""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from trota_common import sysinfo, ui  # noqa: E402
from trota_common.i18n import _  # noqa: E402
from trota_common.sysinfo import format_bytes, format_duration  # noqa: E402

from . import APP_ID  # noqa: E402

NET_KIND = {
    "ethernet": _("Wired"),
    "wireless": _("Wireless"),
    "virtual": _("Virtual"),
    "other": _("Other"),
}


def info_row(title: str, value: str) -> Adw.ActionRow:
    row = ui.plain(Adw.ActionRow, title=title, subtitle=value or "—", subtitle_selectable=True)
    row.add_css_class("property")
    return row


def meter(fraction: float) -> Gtk.LevelBar:
    bar = Gtk.LevelBar(min_value=0, max_value=1, value=max(0.0, min(1.0, fraction)),
                       valign=Gtk.Align.CENTER, width_request=140, css_classes=["trota-meter"])
    bar.add_offset_value("filled", 0.80)
    bar.add_offset_value("high", 0.90)
    bar.add_offset_value("full", 1.0)
    return bar


class SystemInfoWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=_("System Info"), default_width=760, default_height=720)
        self.report: sysinfo.SystemReport | None = None
        self.toasts = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        header = ui.header_bar()
        self.refresh_button = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text=_("Refresh"))
        self.refresh_button.connect("clicked", lambda *_a: self.refresh())
        header.pack_start(self.refresh_button)
        copy = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text=_("Copy report"))
        copy.connect("clicked", self._on_copy)
        header.pack_start(copy)
        save = Gtk.Button(icon_name="document-save-symbolic", tooltip_text=_("Save report…"))
        save.connect("clicked", self._on_save)
        header.pack_start(save)
        view.add_top_bar(header)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        spinner = Gtk.Spinner(spinning=True, width_request=32, height_request=32,
                              halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.stack.add_named(spinner, "loading")
        view.set_content(self.stack)
        self.toasts.set_child(view)
        self.set_content(self.toasts)
        self.refresh()

    # --- data --------------------------------------------------------------
    def refresh(self):
        self.refresh_button.set_sensitive(False)
        self.stack.set_visible_child_name("loading")

        def worker():
            try:
                report = sysinfo.collect()
                GLib.idle_add(self._show, report, None)
            except Exception as exc:  # never leave the window stuck on the spinner
                GLib.idle_add(self._show, None, exc)

        threading.Thread(target=worker, daemon=True).start()

    def _show(self, report, error):
        self.refresh_button.set_sensitive(True)
        old = self.stack.get_child_by_name("report")
        if old is not None:
            self.stack.remove(old)
        if error is not None:
            page = Adw.StatusPage(icon_name="dialog-error-symbolic", title=_("Information could not be collected"),
                                  description=str(error))
        else:
            self.report = report
            page = self._build(report)
        self.stack.add_named(page, "report")
        self.stack.set_visible_child_name("report")
        return GLib.SOURCE_REMOVE

    def _build(self, r: sysinfo.SystemReport) -> Gtk.Widget:
        page = Adw.PreferencesPage()

        system = Adw.PreferencesGroup(title=_("Software"))
        system.add(info_row(_("Operating system"), r.os_pretty_name))
        system.add(info_row(_("Based on"), r.base))
        system.add(info_row(_("Kernel"), r.kernel))
        system.add(info_row(_("Architecture"), r.architecture))
        system.add(info_row(_("Desktop"), f"{r.desktop} · {r.session_type}"))
        system.add(info_row(_("Computer name"), r.hostname))
        system.add(info_row(_("Uptime"), format_duration(r.uptime_seconds)))
        page.add(system)

        hw = Adw.PreferencesGroup(title=_("Hardware"))
        cpu = r.cpu.model
        details = [_("{n} threads").format(n=r.cpu.logical_cpus)]
        if r.cpu.physical_cores:
            details.append(_("{n} cores").format(n=r.cpu.physical_cores))
        if r.cpu.max_mhz:
            details.append(f"{r.cpu.max_mhz / 1000:.2f} GHz max")
        hw.add(info_row(_("Processor"), f"{cpu}\n{', '.join(details)}"))
        mem = r.memory
        mem_row = info_row(_("Memory"), _("{total} total · {avail} available").format(
            total=format_bytes(mem.total_bytes), avail=format_bytes(mem.available_bytes)))
        if mem.total_bytes:
            mem_row.add_suffix(meter(1 - mem.available_bytes / mem.total_bytes))
        hw.add(mem_row)
        hw.add(info_row(_("Swap"), format_bytes(mem.swap_total_bytes) if mem.swap_total_bytes else _("None")))
        for gpu in r.gpus or [_("Not detected")]:
            hw.add(info_row(_("Graphics"), gpu))
        page.add(hw)

        storage = Adw.PreferencesGroup(title=_("Storage"))
        for d in r.disks:
            row = info_row(d.mountpoint, _("{used} used of {total} · {free} free · {fs} on {dev}").format(
                used=format_bytes(d.used_bytes), total=format_bytes(d.total_bytes),
                free=format_bytes(d.free_bytes), fs=d.fstype, dev=d.device))
            row.add_suffix(meter(d.used_percent / 100))
            storage.add(row)
        page.add(storage)

        net = Adw.PreferencesGroup(title=_("Network"))
        shown = 0
        for n in r.network:
            if n.kind == "loopback":
                continue
            shown += 1
            row = ui.plain(Adw.ExpanderRow, title=n.name, subtitle=f"{NET_KIND.get(n.kind, n.kind)} · {n.state}")
            row.add_row(info_row(_("Hardware address"), n.mac))
            for a in n.addresses or [_("No address")]:
                row.add_row(info_row(_("Address"), a))
            net.add(row)
        if not shown:
            net.add(info_row(_("Interfaces"), _("No network interface found")))
        page.add(net)

        privacy = Adw.PreferencesGroup(description=_(
            "All information is read locally from this computer and is never sent anywhere."))
        page.add(privacy)
        return page

    # --- actions -----------------------------------------------------------
    def _on_copy(self, button):
        if self.report:
            ui.copy_to_clipboard(button, sysinfo.report_text(self.report))

    def _on_save(self, _button):
        if not self.report:
            return
        dialog = Gtk.FileDialog(title=_("Save report"), initial_name="trota-system-info.txt")
        dialog.save(self, None, self._on_save_done)

    def _on_save_done(self, dialog, result):
        try:
            gfile = dialog.save_finish(result)
        except GLib.Error:
            return  # cancelled
        if gfile is None:
            return
        path = gfile.get_path() or ""
        text = self.report.to_json() if path.endswith(".json") else sysinfo.report_text(self.report) + "\n"
        try:
            gfile.replace_contents(text.encode("utf-8"), None, False, Gio.FileCreateFlags.REPLACE_DESTINATION, None)
            ui.toast(self.toasts, _("Report saved"))
        except GLib.Error as exc:
            ui.toast(self.toasts, _("Could not save the report: {error}").format(error=exc.message))


class SystemInfoApp(ui.TrotaApplication):
    app_name = _("Trota System Info")
    app_comments = _("Information about this computer, collected locally")

    def __init__(self):
        super().__init__(APP_ID)

    def do_activate(self):
        win = self.get_active_window() or SystemInfoWindow(self)
        win.present()
