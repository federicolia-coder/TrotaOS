"""Trota Welcome main window."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from trota_common import DOCS_URL, ISSUES_URL, SECURITY_URL, desktop, osinfo, sysinfo, ui  # noqa: E402
from trota_common.i18n import _  # noqa: E402

from . import APP_ID, settings  # noqa: E402

# Curated list of preinstalled applications: (target or desktop id, title, description, icon)
APPLICATIONS = (
    (_("Internet"), (
        ("browser", _("Firefox"), _("Web browser"), "firefox"),
    )),
    (_("Office and study"), (
        ("org.gnome.TextEditor.desktop", _("Text Editor"), _("Notes and plain text files"), "org.gnome.TextEditor"),
        ("libreoffice-writer.desktop", _("LibreOffice Writer"), _("Word processor"), "libreoffice-writer"),
        ("libreoffice-calc.desktop", _("LibreOffice Calc"), _("Spreadsheets"), "libreoffice-calc"),
        ("libreoffice-impress.desktop", _("LibreOffice Impress"), _("Presentations"), "libreoffice-impress"),
        ("org.gnome.Evince.desktop", _("Document Viewer"), _("PDF and other documents"), "org.gnome.Evince"),
        ("org.gnome.Calculator.desktop", _("Calculator"), _("Basic, scientific and programming modes"), "org.gnome.Calculator"),
    )),
    (_("Files and media"), (
        ("files", _("Files"), _("File manager"), "org.gnome.Nautilus"),
        ("org.gnome.FileRoller.desktop", _("Archive Manager"), _("Create and extract archives"), "org.gnome.FileRoller"),
        ("org.gnome.eog.desktop", _("Image Viewer"), _("View pictures"), "org.gnome.eog"),
        ("org.gnome.Totem.desktop", _("Videos"), _("Video player"), "org.gnome.Totem"),
    )),
    (_("System"), (
        ("terminal", _("Terminal"), _("Command line"), "org.gnome.Terminal"),
        ("system_monitor", _("System Monitor"), _("Processes and resource usage"), "org.gnome.SystemMonitor"),
        ("disks", _("Disks"), _("Disk management and S.M.A.R.T. data"), "org.gnome.DiskUtility"),
        ("disk_usage", _("Disk Usage Analyzer"), _("Find what uses disk space"), "org.gnome.baobab"),
        ("logs", _("Logs"), _("System log viewer"), "org.gnome.Logs"),
    )),
)


def _target(key: str) -> str:
    """Accept either a key of desktop.TARGETS or a desktop file id."""
    if key not in desktop.TARGETS:
        desktop.TARGETS[key] = desktop.Target((key,))
    return key


class WelcomeWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=_("Welcome to Trota OS"), default_width=900, default_height=660,
                         width_request=360, height_request=420)
        self.release = osinfo.release_info()
        self.toasts = Adw.ToastOverlay()

        self.split = Adw.NavigationSplitView(min_sidebar_width=200, max_sidebar_width=260)
        self.pages = {}
        sidebar_list = Gtk.ListBox(css_classes=["navigation-sidebar"])
        sidebar_list.connect("row-selected", self._on_row_selected)
        for key, title, icon, builder in (
            ("welcome", _("Welcome"), "go-home-symbolic", self._page_welcome),
            ("start", _("Get started"), "preferences-system-symbolic", self._page_start),
            ("tools", _("Trota tools"), "applications-utilities-symbolic", self._page_tools),
            ("apps", _("Applications"), "view-app-grid-symbolic", self._page_apps),
            ("help", _("Help and support"), "help-browser-symbolic", self._page_help),
        ):
            row = Gtk.ListBoxRow()
            box = Gtk.Box(spacing=12, margin_top=8, margin_bottom=8, margin_start=6, margin_end=6)
            box.append(Gtk.Image(icon_name=icon))
            box.append(Gtk.Label(label=title, xalign=0))
            row.set_child(box)
            row.page_key = key
            sidebar_list.append(row)
            self.pages[key] = (title, builder)

        sidebar_view = Adw.ToolbarView()
        sidebar_view.add_top_bar(Adw.HeaderBar(show_title=True))
        sidebar_view.set_content(Gtk.ScrolledWindow(child=sidebar_list, vexpand=True))
        self.split.set_sidebar(Adw.NavigationPage(title="Trota OS", child=sidebar_view))
        self.content_page = Adw.NavigationPage(title=_("Welcome"))
        self.split.set_content(self.content_page)

        self.toasts.set_child(self.split)
        self.set_content(self.toasts)

        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 640sp"))
        bp.add_setter(self.split, "collapsed", True)
        self.add_breakpoint(bp)

        sidebar_list.select_row(sidebar_list.get_row_at_index(0))

    # --- navigation ------------------------------------------------------
    def _on_row_selected(self, _listbox, row):
        if row is None:
            return
        title, builder = self.pages[row.page_key]
        view = Adw.ToolbarView()
        view.add_top_bar(ui.header_bar())
        view.set_content(builder())
        self.content_page.set_title(title)
        self.content_page.set_child(view)
        self.split.set_show_content(True)

    @staticmethod
    def _scrolled(*children) -> Gtk.Widget:
        clamp = Adw.Clamp(maximum_size=720, margin_top=24, margin_bottom=24, margin_start=18, margin_end=18)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        for c in children:
            box.append(c)
        clamp.set_child(box)
        return Gtk.ScrolledWindow(child=clamp, hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)

    # --- pages -------------------------------------------------------------
    def _hero(self) -> Gtk.Widget:
        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["trota-hero"])
        logo = ui.data_file("logo/trota-logo-dark.svg")
        if logo:
            pic = Gtk.Picture.new_for_filename(logo)
            pic.set_size_request(-1, 72)
            pic.set_can_shrink(True)
            pic.set_content_fit(Gtk.ContentFit.CONTAIN)
            pic.set_halign(Gtk.Align.START)
            pic.set_alternative_text("Trota OS")
            hero.append(pic)
        else:
            hero.append(Gtk.Label(label="TROTA OS", xalign=0, css_classes=["trota-hero-title"]))
        hero.append(Gtk.Box(css_classes=["trota-hero-rule"], halign=Gtk.Align.START))
        rel = self.release
        version = rel.pretty_name
        if rel.is_trota and rel.codename:
            version = f"{rel.name} {rel.version} “{rel.codename}”"
        hero.append(Gtk.Label(label=version, xalign=0, css_classes=["title-3"], selectable=True))
        if rel.base_description:
            hero.append(Gtk.Label(label=_("Based on {base}").format(base=rel.base_description), xalign=0,
                                  css_classes=["dim-label"], selectable=True))
        hero.append(Gtk.Label(label=_("Developed and published by TestardStudios"), xalign=0, css_classes=["dim-label"]))
        return hero

    def _page_welcome(self) -> Gtk.Widget:
        intro = Gtk.Label(
            wrap=True, xalign=0,
            label=_("Trota OS is a desktop operating system for development, system administration, "
                    "gaming, study and everyday use. It is built on Ubuntu LTS, so it uses the same "
                    "packages, drivers and security updates. There is no mandatory account and "
                    "no telemetry."),
        )
        buttons = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=3,
                              column_spacing=12, row_spacing=12, homogeneous=True)
        for target, label, primary in (
            ("updates", _("Check for updates"), True),
            ("settings", _("Open Settings"), False),
            ("trota_system_info", _("System information"), False),
        ):
            b = ui.launch_button(target, label, self.toasts)
            if primary:
                b.add_css_class("trota-orange")
            buttons.append(b)

        prefs = Adw.PreferencesGroup()
        switch = Adw.SwitchRow(title=_("Show this window at login"),
                               subtitle=_("You can always open it from the applications menu"))
        switch.set_active(settings.show_at_login())
        switch.connect("notify::active", self._on_autostart_toggled)
        prefs.add(switch)
        return self._scrolled(self._hero(), intro, buttons, prefs)

    def _on_autostart_toggled(self, row, _pspec):
        try:
            settings.set_show_at_login(row.get_active())
        except OSError as exc:
            ui.toast(row, _("Could not save the preference: {error}").format(error=exc.strerror or exc))

    def _page_start(self) -> Gtk.Widget:
        look = Adw.PreferencesGroup(title=_("Personalize"))
        look.add(ui.launch_row("appearance", _("Appearance"), _("Light or dark style, accent color, dock"), "preferences-desktop-appearance-symbolic"))
        look.add(ui.launch_row("background", _("Wallpaper"), _("Choose one of the Trota OS wallpapers or your own pictures"), "preferences-desktop-wallpaper-symbolic"))
        look.add(ui.launch_row("display", _("Displays"), _("Resolution, scaling and night light"), "video-display-symbolic"))
        look.add(ui.launch_row("accessibility", _("Accessibility"), _("Screen reader, large text, high contrast, zoom"), "preferences-desktop-accessibility-symbolic"))

        connect = Adw.PreferencesGroup(title=_("Connect"))
        connect.add(ui.launch_row("wifi", _("Wi-Fi"), _("Connect to a wireless network"), "network-wireless-symbolic"))
        connect.add(ui.launch_row("network", _("Network"), _("Wired connections, VPN and proxy"), "network-wired-symbolic"))
        connect.add(ui.launch_row("users", _("Users"), _("Accounts, passwords and fingerprint login"), "system-users-symbolic"))
        connect.add(ui.launch_row("privacy", _("Privacy and security"), _("Screen lock, location services, file history"), "preferences-system-privacy-symbolic"))

        software = Adw.PreferencesGroup(title=_("Software and updates"))
        software.add(ui.launch_row("updates", _("Software Updater"), _("Install updates now"), "software-update-available-symbolic"))
        software.add(ui.launch_row("app_center", _("Software"), _("Find and install applications"), "system-software-install-symbolic"))
        software.add(ui.launch_row("software_sources", _("Software & Updates"), _("Repositories and automatic update policy"), "preferences-other-symbolic"))
        software.add(ui.launch_row("drivers", _("Additional Drivers"), _("Proprietary graphics and Wi-Fi drivers (e.g. NVIDIA)"), "application-x-firmware-symbolic"))
        return self._scrolled(look, connect, software)

    def _page_tools(self) -> Gtk.Widget:
        group = Adw.PreferencesGroup(
            title=_("Trota OS tools"),
            description=_("Original utilities of Trota OS. They work offline and never send data anywhere."),
        )
        group.add(ui.launch_row("trota_system_info", _("Trota System Info"),
                                _("Version, kernel, CPU, memory, disks, network and graphics"),
                                "it.testardstudios.TrotaSystemInfo"))
        group.add(ui.launch_row("trota_diagnostics", _("Trota Diagnostics"),
                                _("Safe, read-only checks with clear suggestions"),
                                "it.testardstudios.TrotaDiagnostics"))
        group.add(ui.launch_row("trota_package_helper", _("Trota Package Helper"),
                                _("Search the package catalogue and learn how to install software"),
                                "it.testardstudios.TrotaPackageHelper"))
        return self._scrolled(group)

    def _page_apps(self) -> Gtk.Widget:
        groups = []
        for category, items in APPLICATIONS:
            g = Adw.PreferencesGroup(title=category)
            for key, title, subtitle, icon in items:
                g.add(ui.launch_row(_target(key), title, subtitle, icon))
            groups.append(g)
        more = Adw.PreferencesGroup(title=_("More software"))
        more.add(ui.launch_row("app_center", _("Software"), _("Thousands of applications from Flathub, including Steam and VS Code"), "system-software-install-symbolic"))
        more.add(ui.launch_row("trota_package_helper", _("Trota Package Helper"), _("Search the APT catalogue"), "it.testardstudios.TrotaPackageHelper"))
        groups.append(more)
        return self._scrolled(*groups)

    def _page_help(self) -> Gtk.Widget:
        docs = Adw.PreferencesGroup(title=_("Documentation"))
        local = desktop.local_docs_uri()
        if local:
            docs.add(ui.uri_row(local, _("Trota OS documentation"), _("Offline guide installed on this computer"), "help-contents-symbolic"))
        docs.add(ui.uri_row(DOCS_URL, _("Online documentation"), _("Latest version of the guides"), "web-browser-symbolic"))
        docs.add(ui.launch_row("help", _("Desktop guide"), _("How to use the GNOME desktop"), "help-browser-symbolic"))

        support = Adw.PreferencesGroup(
            title=_("Support"),
            description=_("Trota OS is a community project by TestardStudios, provided without commercial support. "
                          "Security updates for the Ubuntu base come from the Ubuntu archive for the whole LTS "
                          "lifetime (standard support until April 2029)."),
        )
        support.add(ui.uri_row(ISSUES_URL, _("Report a problem"), _("Open an issue on the project tracker"), "dialog-warning-symbolic"))
        support.add(ui.uri_row(SECURITY_URL, _("Report a security vulnerability"), _("Read the security policy first"), "security-high-symbolic"))
        copy_row = ui.plain(Adw.ActionRow, title=_("Copy system information"),
                                 subtitle=_("Paste it in your report: it contains no personal files"),
                                 activatable=True)
        copy_row.add_prefix(Gtk.Image(icon_name="edit-copy-symbolic"))
        copy_row.connect("activated", lambda r: ui.copy_to_clipboard(r, sysinfo.report_text(sysinfo.collect())))
        support.add(copy_row)
        return self._scrolled(docs, support)


class WelcomeApp(ui.TrotaApplication):
    app_name = _("Trota Welcome")
    app_comments = _("Getting started with Trota OS")

    def __init__(self):
        super().__init__(APP_ID)

    def do_activate(self):
        win = self.get_active_window() or WelcomeWindow(self)
        win.present()
