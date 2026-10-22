"""Trota VR main window."""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from trota_common import diagnostics, ui  # noqa: E402
from trota_common.i18n import _  # noqa: E402

from . import APP_ID, checks  # noqa: E402
from .cli import format_text  # noqa: E402

OVERALL = {
    "ok": (_("This PC is ready for VR"), _("Install the VR software below and connect your headset.")),
    "info": (_("This PC is ready for VR"), _("Read the notes below.")),
    "warning": (_("Some items need attention"), _("VR may not work well until you follow the suggestions below.")),
    "error": (_("VR cannot work yet"), _("Follow the suggestions below, then check again.")),
    "skipped": (_("Checks completed"), ""),
}

CHECK_TOOLS = {"gpu": ("drivers", _("Additional Drivers")), "vulkan": ("drivers", _("Additional Drivers"))}


class VRWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Trota VR", default_width=760, default_height=760)
        self.results = []
        self.busy = False
        self.toasts = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        header = ui.header_bar()
        self.run_button = Gtk.Button(label=_("Check again"), css_classes=["trota-orange"])
        self.run_button.connect("clicked", lambda *_a: self.run_checks())
        header.pack_start(self.run_button)
        self.copy_button = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text=_("Copy report"), sensitive=False)
        self.copy_button.connect("clicked", lambda b: ui.copy_to_clipboard(b, format_text(self.results)))
        header.pack_start(self.copy_button)
        view.add_top_bar(header)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        busy = Adw.StatusPage(icon_name=APP_ID, title=_("Checking this PC for VR…"))
        busy.set_child(Gtk.Spinner(spinning=True, width_request=32, height_request=32, halign=Gtk.Align.CENTER))
        self.stack.add_named(busy, "busy")
        view.set_content(self.stack)
        self.toasts.set_child(view)
        self.set_content(self.toasts)
        self.run_checks()

    def run_checks(self):
        if self.busy:
            return
        self.busy = True
        self.run_button.set_sensitive(False)
        self.copy_button.set_sensitive(False)
        self.stack.set_visible_child_name("busy")

        def worker():
            ctx = checks.Context()
            results = checks.run_all(ctx)
            installed = checks.installed_apps(ctx)
            GLib.idle_add(self._show, results, installed)

        threading.Thread(target=worker, daemon=True).start()

    def _show(self, results, installed):
        self.busy = False
        self.results = results
        self.run_button.set_sensitive(True)
        self.copy_button.set_sensitive(True)
        old = self.stack.get_child_by_name("results")
        if old is not None:
            self.stack.remove(old)
        self.stack.add_named(self._build(results, installed), "results")
        self.stack.set_visible_child_name("results")
        return GLib.SOURCE_REMOVE

    def _build(self, results, installed) -> Gtk.Widget:
        page = Adw.PreferencesPage()
        title, description = OVERALL[diagnostics.overall_status(results)]
        page.add(Adw.PreferencesGroup(title=title, description=description))

        apps = Adw.PreferencesGroup(title=_("VR software"),
                                    description=_("Free to install from Flathub. Steam and SteamVR are "
                                                  "Valve's proprietary software."))
        for app in checks.APPS:
            row = ui.plain(Adw.ActionRow, title=app.name, subtitle=app.purpose)
            if app.flatpak_id in installed:
                info = Gio.DesktopAppInfo.new(app.flatpak_id + ".desktop")
                button = Gtk.Button(label=_("Open"), valign=Gtk.Align.CENTER, sensitive=info is not None)
                if info is not None:
                    button.connect("clicked", lambda _b, i=info: i.launch([], None))
            else:
                button = Gtk.Button(label=_("Install"), valign=Gtk.Align.CENTER, css_classes=["suggested-action"])
                button.connect("clicked", self._on_install, app)
            row.add_suffix(button)
            apps.add(row)
        page.add(apps)

        group = Adw.PreferencesGroup(title=_("This PC"))
        for r in results:
            row = ui.plain(Adw.ExpanderRow, title=r.title, subtitle=r.summary)
            icon = Gtk.Image(icon_name=ui.STATUS_ICONS.get(r.status, "dialog-question-symbolic"),
                             css_classes=[f"status-{r.status}"], pixel_size=20)
            icon.update_property([Gtk.AccessibleProperty.LABEL], [r.status])
            row.add_prefix(icon)
            if r.details:
                row.add_row(Gtk.Label(label="\n".join(r.details), xalign=0, wrap=True, selectable=True,
                                      css_classes=["trota-mono", "caption"], margin_top=10, margin_bottom=10,
                                      margin_start=14, margin_end=14))
            if r.suggestion:
                s = ui.plain(Adw.ActionRow, title=_("Suggestion"), subtitle=r.suggestion)
                s.add_prefix(Gtk.Image(icon_name="dialog-information-symbolic"))
                tool = CHECK_TOOLS.get(r.id)
                if tool and r.status in ("warning", "error"):
                    s.add_suffix(ui.launch_button(tool[0], tool[1], self.toasts))
                if r.id == "firewall" and r.status == "info":
                    fw = Gtk.Button(label=_("Open WiVRn ports"), valign=Gtk.Align.CENTER)
                    fw.connect("clicked", self._on_open_firewall)
                    s.add_suffix(fw)
                row.add_row(s)
            if r.status in ("warning", "error"):
                row.set_expanded(True)
            group.add(row)
        page.add(group)
        return page

    def _on_open_firewall(self, button):
        button.set_sensitive(False)

        def worker():
            r = checks.open_firewall()
            msg = _("WiVRn ports are open.") if r.ok else _("The firewall was not changed.")
            GLib.idle_add(lambda: (self.toasts.add_toast(Adw.Toast(title=msg, timeout=5)), button.set_sensitive(True))
                          and GLib.SOURCE_REMOVE)

        threading.Thread(target=worker, daemon=True).start()

    def _on_install(self, button, app):
        button.set_sensitive(False)
        button.set_label(_("Installing…"))
        self.toasts.add_toast(Adw.Toast(title=_("Installing {name}: this can take a few minutes.").format(name=app.name),
                                        timeout=5))

        def worker():
            r = checks.install(app)
            GLib.idle_add(self._installed, app, r)

        threading.Thread(target=worker, daemon=True).start()

    def _installed(self, app, result):
        if result.ok:
            msg = _("{name} is installed.").format(name=app.name)
        else:
            msg = _("Could not install {name}: {error}").format(
                name=app.name, error=(result.stderr.strip().splitlines() or [_("unknown error")])[-1])
        self.toasts.add_toast(Adw.Toast(title=msg, timeout=6))
        self.run_checks()
        return GLib.SOURCE_REMOVE


class VRApp(ui.TrotaApplication):
    app_name = "Trota VR"
    app_comments = _("Check this PC for virtual reality and install the VR software")

    def __init__(self):
        super().__init__(APP_ID)

    def do_activate(self):
        win = self.get_active_window() or VRWindow(self)
        win.present()
