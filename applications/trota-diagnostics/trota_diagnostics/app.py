"""Trota Diagnostics main window."""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from trota_common import diagnostics, ui  # noqa: E402
from trota_common.i18n import _  # noqa: E402

from . import APP_ID  # noqa: E402
from .cli import format_text  # noqa: E402

OVERALL = {
    "ok": (_("Everything looks good"), _("No problems were found.")),
    "info": (_("Everything looks good"), _("There are a few notes you may want to read.")),
    "warning": (_("Some items need attention"), _("Read the suggestions below. Nothing was changed on your system.")),
    "error": (_("Problems found"), _("Read the suggestions below. Nothing was changed on your system.")),
    "skipped": (_("Checks completed"), ""),
}

# Tools suggested next to a check result (all part of the default install).
CHECK_TOOLS = {
    "disk": ("disk_usage", _("Disk Usage Analyzer")),
    "network": ("network", _("Network settings")),
    "updates": ("updates", _("Software Updater")),
    "logs": ("logs", _("Logs")),
    "services": ("system_monitor", _("System Monitor")),
    "security": ("software_sources", _("Software & Updates")),
}


class DiagnosticsWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=_("Diagnostics"), default_width=760, default_height=720)
        self.results: list[diagnostics.CheckResult] = []
        self.toasts = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        header = ui.header_bar()
        self.run_button = Gtk.Button(label=_("Run checks"), css_classes=["trota-orange"])
        self.run_button.connect("clicked", lambda *_a: self.run_checks())
        header.pack_start(self.run_button)
        self.copy_button = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text=_("Copy report"), sensitive=False)
        self.copy_button.connect("clicked", lambda b: ui.copy_to_clipboard(b, format_text(self.results)))
        header.pack_start(self.copy_button)
        view.add_top_bar(header)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        intro = Adw.StatusPage(
            icon_name=APP_ID,
            title=_("Check the health of your system"),
            description=_("Disk space, network, kernel, security features, services, recent errors and updates.\n"
                          "All checks are read-only: nothing is changed, deleted or repaired automatically."),
        )
        start = Gtk.Button(label=_("Run checks"), halign=Gtk.Align.CENTER, css_classes=["pill", "trota-orange"])
        start.connect("clicked", lambda *_a: self.run_checks())
        intro.set_child(start)
        self.stack.add_named(intro, "intro")
        busy = Adw.StatusPage(title=_("Running checks…"))
        busy.set_child(Gtk.Spinner(spinning=True, width_request=32, height_request=32, halign=Gtk.Align.CENTER))
        self.stack.add_named(busy, "busy")
        view.set_content(self.stack)
        self.toasts.set_child(view)
        self.set_content(self.toasts)

    def run_checks(self):
        self.run_button.set_sensitive(False)
        self.copy_button.set_sensitive(False)
        self.stack.set_visible_child_name("busy")

        def worker():
            ctx = diagnostics.Context(resolve=diagnostics.resolve_host)
            results = diagnostics.run_all(ctx)
            GLib.idle_add(self._show, results)

        threading.Thread(target=worker, daemon=True).start()

    def _show(self, results):
        self.results = results
        self.run_button.set_sensitive(True)
        self.copy_button.set_sensitive(True)
        old = self.stack.get_child_by_name("results")
        if old is not None:
            self.stack.remove(old)
        self.stack.add_named(self._build(results), "results")
        self.stack.set_visible_child_name("results")
        return GLib.SOURCE_REMOVE

    def _build(self, results) -> Gtk.Widget:
        page = Adw.PreferencesPage()
        overall = diagnostics.overall_status(results)
        title, description = OVERALL[overall]
        head = Adw.PreferencesGroup(title=title, description=description)
        page.add(head)
        group = Adw.PreferencesGroup()
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
                if tool and r.status in ("warning", "error", "info"):
                    s.add_suffix(ui.launch_button(tool[0], tool[1], self.toasts))
                row.add_row(s)
            if r.status in ("warning", "error"):
                row.set_expanded(True)
            group.add(row)
        page.add(group)
        return page


class DiagnosticsApp(ui.TrotaApplication):
    app_name = _("Trota Diagnostics")
    app_comments = _("Safe, read-only health checks")

    def __init__(self):
        super().__init__(APP_ID)

    def do_activate(self):
        win = self.get_active_window() or DiagnosticsWindow(self)
        win.present()

