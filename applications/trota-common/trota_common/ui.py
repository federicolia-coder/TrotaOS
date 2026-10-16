"""GTK 4 / libadwaita helpers shared by the Trota OS applications."""

from __future__ import annotations

import os
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import PROJECT_URL, ISSUES_URL, PUBLISHER, __version__, desktop  # noqa: E402
from .i18n import _, bind_gtk_domain  # noqa: E402

DATA_DIRS = (
    os.environ.get("TROTA_DATA_DIR", ""),
    "/usr/share/trota-os",
    str(Path(__file__).resolve().parent.parent / "data"),  # running from the source tree
)

STATUS_ICONS = {
    "ok": "emblem-ok-symbolic",
    "info": "dialog-information-symbolic",
    "warning": "dialog-warning-symbolic",
    "error": "dialog-error-symbolic",
    "skipped": "action-unavailable-symbolic",
}


def data_file(name: str) -> str | None:
    for d in DATA_DIRS:
        if d and os.path.exists(os.path.join(d, name)):
            return os.path.join(d, name)
    return None


def load_css() -> None:
    path = data_file("trota.css")
    display = Gdk.Display.get_default()
    if not path or display is None:
        return
    provider = Gtk.CssProvider()
    provider.load_from_path(path)
    Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


class TrotaApplication(Adw.Application):
    """Base class: single instance, About and Quit actions, shared styling."""

    app_name = "Trota OS"
    app_comments = ""

    def __init__(self, application_id: str, **kwargs):
        super().__init__(application_id=application_id, flags=Gio.ApplicationFlags.DEFAULT_FLAGS, **kwargs)
        bind_gtk_domain()
        GLib.set_application_name(self.app_name)
        self._add_action("about", self.on_about)
        self._add_action("quit", lambda *_a: self.quit(), ["<primary>q"])
        self.set_accels_for_action("window.close", ["<primary>w"])

    def _add_action(self, name, callback, accels=None):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        if accels:
            self.set_accels_for_action(f"app.{name}", accels)

    def do_startup(self):
        Adw.Application.do_startup(self)
        load_css()

    def on_about(self, *_args):
        about = Adw.AboutDialog(
            application_name=self.app_name,
            application_icon=self.get_application_id(),
            developer_name=PUBLISHER,
            version=__version__,
            comments=self.app_comments,
            website=PROJECT_URL,
            issue_url=ISSUES_URL,
            copyright=f"© 2026 {PUBLISHER}",
            license_type=Gtk.License.GPL_3_0,
        )
        about.add_legal_section(
            _("Trademarks"),
            None,
            Gtk.License.CUSTOM,
            _("Trota OS is developed and published by TestardStudios. It is based on Ubuntu, "
              "but it is not affiliated with or endorsed by Canonical Ltd. "
              "Ubuntu is a registered trademark of Canonical Ltd."),
        )
        about.present(self.get_active_window())


def plain(row_cls, title: str = "", subtitle: str = "", **kwargs):
    """Create an Adw row whose texts are plain text, never Pango markup.

    use-markup must be disabled *before* the texts are set, which the
    keyword-argument constructor does not guarantee.
    """
    row = row_cls(**kwargs)
    row.set_use_markup(False)
    row.set_title(title)
    if subtitle and hasattr(row, "set_subtitle"):
        row.set_subtitle(subtitle)
    return row


def toast(widget: Gtk.Widget, message: str) -> None:
    """Show a toast in the nearest Adw.ToastOverlay ancestor (if any)."""
    w = widget
    while w is not None and not isinstance(w, Adw.ToastOverlay):
        w = w.get_parent()
    if w is not None:
        w.add_toast(Adw.Toast(title=message, timeout=4))


def launch_button(target: str, label: str, widget_for_toast: Gtk.Widget | None = None,
                  suggested: bool = False) -> Gtk.Button:
    """A button that launches a desktop target, disabled when unavailable."""
    button = Gtk.Button(label=label, valign=Gtk.Align.CENTER)
    if suggested:
        button.add_css_class("suggested-action")
    if not desktop.available(target):
        button.set_sensitive(False)
        button.set_tooltip_text(_("Not installed on this system"))
        return button

    def on_clicked(btn):
        try:
            desktop.launch(target)
        except (GLib.Error, OSError, LookupError) as exc:
            toast(widget_for_toast or btn, _("Could not start the application: {error}").format(error=exc))

    button.connect("clicked", on_clicked)
    return button


def launch_row(target: str, title: str, subtitle: str, icon: str | None = None) -> Adw.ActionRow:
    """An activatable row that launches a target (insensitive if missing)."""
    row = plain(Adw.ActionRow, title, subtitle, activatable=True)
    if icon:
        row.add_prefix(Gtk.Image(icon_name=icon, pixel_size=32))
    row.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
    if not desktop.available(target):
        row.set_sensitive(False)
        row.set_subtitle(subtitle + " — " + _("not installed"))
        return row

    def on_activated(r):
        try:
            desktop.launch(target)
        except (GLib.Error, OSError, LookupError) as exc:
            toast(r, _("Could not start the application: {error}").format(error=exc))

    row.connect("activated", on_activated)
    return row


def uri_row(uri: str, title: str, subtitle: str, icon: str = "web-browser-symbolic") -> Adw.ActionRow:
    row = plain(Adw.ActionRow, title, subtitle, activatable=True)
    row.add_prefix(Gtk.Image(icon_name=icon))
    row.add_suffix(Gtk.Image(icon_name="adw-external-link-symbolic"))

    def on_activated(r):
        try:
            desktop.open_uri(uri)
        except GLib.Error as exc:
            toast(r, _("Could not open the link: {error}").format(error=exc.message))

    row.connect("activated", on_activated)
    return row


def copy_to_clipboard(widget: Gtk.Widget, text: str) -> None:
    widget.get_clipboard().set(text)
    toast(widget, _("Copied to the clipboard"))


def main_menu() -> Gio.Menu:
    menu = Gio.Menu()
    menu.append(_("About"), "app.about")
    menu.append(_("Quit"), "app.quit")
    return menu


def header_bar(title_widget: Gtk.Widget | None = None) -> Adw.HeaderBar:
    bar = Adw.HeaderBar()
    if title_widget is not None:
        bar.set_title_widget(title_widget)
    bar.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=main_menu(),
                                tooltip_text=_("Main menu"), primary=True))
    return bar
