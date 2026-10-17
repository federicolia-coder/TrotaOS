"""Trota Package Helper main window.

APT stays the reference package system: this application only searches and
describes packages and explains how to install them.  It never runs a
privileged command itself.
"""

from __future__ import annotations

import sys
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from trota_common import packages, ui  # noqa: E402
from trota_common.i18n import _  # noqa: E402
from trota_common.sysinfo import format_bytes  # noqa: E402

from . import APP_ID  # noqa: E402

TIPS = (
    (_("Graphical applications"),
     _("Software installs applications from the Ubuntu archive and from Flathub (Steam, VS Code, Spotify, "
       "Discord…) as Flatpak packages, isolated from the system and updated automatically.")),
    (_("Command line tools and libraries"),
     _("Install them from the Ubuntu archive with APT, for example: sudo apt install htop")),
    (_("Software from other websites"),
     _("Prefer the Ubuntu archive or Flathub. Add third-party repositories (PPA) only from sources you trust: "
       "they get full access to your system.")),
)


class PackageHelperWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=_("Package Helper"), default_width=760, default_height=720)
        self._search_serial = 0
        self.toasts = Adw.ToastOverlay()
        self.nav = Adw.NavigationView()
        self.nav.add(self._search_page())
        self.toasts.set_child(self.nav)
        self.set_content(self.toasts)

    # --- search page -------------------------------------------------------
    def _search_page(self) -> Adw.NavigationPage:
        view = Adw.ToolbarView()
        header = ui.header_bar()
        header.pack_start(ui.launch_button("app_center", _("Software"), self.toasts))
        view.add_top_bar(header)

        self.entry = Gtk.SearchEntry(placeholder_text=_("Search packages, e.g. “python”, “video editor”"),
                                     hexpand=True, search_delay=400)
        self.entry.connect("search-changed", self._on_search_changed)
        self.entry.connect("activate", self._on_search_changed)
        bar = Gtk.Box(margin_top=12, margin_bottom=6, margin_start=12, margin_end=12)
        bar.append(Adw.Clamp(child=self.entry, maximum_size=640, hexpand=True))
        view.add_top_bar(bar)

        self.banner = Adw.Banner(title=_("Package lists have not been downloaded yet. Open Software Updater to refresh them."),
                                 button_label=_("Software Updater"))
        self.banner.connect("button-clicked", lambda *_a: self._launch("updates"))
        view.add_top_bar(self.banner)
        threading.Thread(target=self._check_lists, daemon=True).start()

        self.results_stack = Gtk.Stack()
        tips = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title=_("How to install software on Trota OS"))
        for title, text in TIPS:
            group.add(ui.plain(Adw.ActionRow, title=title, subtitle=text))
        tips.add(group)
        self.results_stack.add_named(tips, "tips")
        self.results_stack.add_named(Adw.StatusPage(title=_("Searching…")), "busy")
        self.empty_page = Adw.StatusPage(icon_name="edit-find-symbolic", title=_("No packages found"),
                                         description=_("Try a different or shorter search."))
        self.results_stack.add_named(self.empty_page, "empty")
        self.error_page = Adw.StatusPage(icon_name="dialog-error-symbolic", title=_("Search failed"))
        self.results_stack.add_named(self.error_page, "error")
        self.listbox = Gtk.ListBox(css_classes=["boxed-list"], selection_mode=Gtk.SelectionMode.NONE)
        self.listbox.connect("row-activated", self._on_row_activated)
        self.count_label = Gtk.Label(xalign=0, css_classes=["dim-label"])
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=12, margin_bottom=24,
                      margin_start=12, margin_end=12)
        box.append(self.count_label)
        box.append(self.listbox)
        self.results_stack.add_named(
            Gtk.ScrolledWindow(child=Adw.Clamp(child=box, maximum_size=760), vexpand=True), "results")
        view.set_content(self.results_stack)
        return Adw.NavigationPage(title=_("Package Helper"), child=view, tag="search")

    def _check_lists(self):
        ok = packages.lists_available()
        GLib.idle_add(self.banner.set_revealed, not ok)

    def _on_search_changed(self, entry):
        text = entry.get_text().strip()
        self._search_serial += 1
        serial = self._search_serial
        if len(text) < 2:
            self.results_stack.set_visible_child_name("tips")
            return
        self.results_stack.set_visible_child_name("busy")

        def worker():
            try:
                res, err = packages.search(text), None
            except packages.PackageError as exc:
                res, err = [], str(exc)
            GLib.idle_add(self._show_results, serial, res, err)

        threading.Thread(target=worker, daemon=True).start()

    def _show_results(self, serial, results, error):
        if serial != self._search_serial:  # a newer search is running
            return GLib.SOURCE_REMOVE
        if error:
            self.error_page.set_description(error)
            self.results_stack.set_visible_child_name("error")
            return GLib.SOURCE_REMOVE
        if not results:
            self.results_stack.set_visible_child_name("empty")
            return GLib.SOURCE_REMOVE
        self.listbox.remove_all()
        for r in results:
            row = ui.plain(Adw.ActionRow, title=r.name, subtitle=r.summary, activatable=True)
            row.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
            row.package_name = r.name
            self.listbox.append(row)
        limit = packages.DEFAULT_LIMIT
        self.count_label.set_label(
            _("Showing the first {n} results").format(n=limit) if len(results) >= limit
            else _("{n} results").format(n=len(results)))
        self.results_stack.set_visible_child_name("results")
        return GLib.SOURCE_REMOVE

    def _on_row_activated(self, _listbox, row):
        self.show_package(row.package_name)

    # --- details page ------------------------------------------------------
    def show_package(self, name: str):
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        stack = Gtk.Stack()
        stack.add_named(Adw.StatusPage(title=_("Loading…")), "busy")
        view.set_content(stack)
        self.nav.push(Adw.NavigationPage(title=name, child=view))

        def worker():
            try:
                info, err = packages.info(name), None
            except packages.PackageError as exc:
                info, err = None, str(exc)
            GLib.idle_add(self._show_details, stack, info, err)

        threading.Thread(target=worker, daemon=True).start()

    def _show_details(self, stack, info, error):
        if error:
            stack.add_named(Adw.StatusPage(icon_name="dialog-error-symbolic", title=_("Package not available"),
                                           description=error), "error")
            stack.set_visible_child_name("error")
            return GLib.SOURCE_REMOVE
        page = Adw.PreferencesPage()
        head = Adw.PreferencesGroup(title=info.name, description=info.summary)
        state = (_("Installed (version {v})").format(v=info.installed_version) if info.installed
                 else _("Not installed"))
        head.add(self._row(_("Status"), state))
        head.add(self._row(_("Available version"), info.version))
        head.add(self._row(_("Section"), f"{info.section} — {info.support_note}".strip(" —")))
        if info.installed_size_kib is not None:
            head.add(self._row(_("Installed size"), format_bytes(info.installed_size_kib * 1024)))
        if info.download_size is not None:
            head.add(self._row(_("Download size"), format_bytes(info.download_size)))
        if info.homepage:
            head.add(ui.uri_row(info.homepage, _("Homepage"), info.homepage))
        page.add(head)

        if info.description:
            desc = Adw.PreferencesGroup(title=_("Description"))
            desc.add(Gtk.Label(label=info.description, wrap=True, xalign=0, selectable=True))
            page.add(desc)

        how = Adw.PreferencesGroup(
            title=_("How to remove") if info.installed else _("How to install"),
            description=_("Run this command in the Terminal. You will be asked for your password: "
                          "only administrators can install or remove software."),
        )
        cmd = packages.remove_command(info.name) if info.installed else packages.install_command(info.name)
        cmd_row = ui.plain(Adw.ActionRow, title=cmd, title_selectable=True, css_classes=["trota-mono"])
        copy = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text=_("Copy command"), valign=Gtk.Align.CENTER)
        copy.connect("clicked", lambda b: ui.copy_to_clipboard(b, cmd))
        cmd_row.add_suffix(copy)
        how.add(cmd_row)
        how.add(ui.launch_row("terminal", _("Open Terminal"), _("Paste the command with Ctrl+Shift+V"),
                              "utilities-terminal-symbolic"))
        how.add(ui.launch_row("app_center", _("Open Software"),
                              _("Graphical applications may also be available there"), "system-software-install-symbolic"))
        page.add(how)
        stack.add_named(page, "page")
        stack.set_visible_child_name("page")
        return GLib.SOURCE_REMOVE

    @staticmethod
    def _row(title, value):
        return ui.plain(Adw.ActionRow, title=title, subtitle=value or "—", subtitle_selectable=True,
                             css_classes=["property"])

    def _launch(self, target):
        from trota_common import desktop

        try:
            desktop.launch(target)
        except (GLib.Error, OSError, LookupError) as exc:
            ui.toast(self.toasts, _("Could not start the application: {error}").format(error=exc))


class PackageHelperApp(ui.TrotaApplication):
    app_name = _("Trota Package Helper")
    app_comments = _("Search the Ubuntu package catalogue")

    def __init__(self):
        super().__init__(APP_ID)

    def do_activate(self):
        win = self.get_active_window() or PackageHelperWindow(self)
        win.present()


def main(argv=None) -> int:
    return PackageHelperApp().run(list(argv if argv is not None else sys.argv))
