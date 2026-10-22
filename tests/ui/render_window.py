#!/usr/bin/env python3
"""Open one Trota OS application window, let it run, and save a screenshot.

Used by tests/test_ui_smoke.py (under Xvfb) and to produce the screenshots in
docs/.  Usage: render_window.py APP OUTPUT.png [--seconds N] [--action NAME]
APP is one of: welcome, system-info, diagnostics, package-helper, vr.
"""

import argparse
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk  # noqa: E402

APPS = {
    "welcome": ("trota_welcome.app", "WelcomeApp"),
    "system-info": ("trota_system_info.app", "SystemInfoApp"),
    "diagnostics": ("trota_diagnostics.app", "DiagnosticsApp"),
    "package-helper": ("trota_package_helper.app", "PackageHelperApp"),
    "vr": ("trota_vr.app", "VRApp"),
}


def snapshot(window, path):
    paintable = Gtk.WidgetPaintable.new(window)
    w, h = window.get_width(), window.get_height()
    snap = Gtk.Snapshot()
    paintable.snapshot(snap, w, h)
    node = snap.to_node()
    if node is None:
        raise RuntimeError("empty render")
    texture = window.get_native().get_renderer().render_texture(node, None)
    texture.save_to_png(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("app", choices=APPS)
    ap.add_argument("output")
    ap.add_argument("--seconds", type=float, default=3)
    ap.add_argument("--action", help="optional scripted action: run-checks, search:<text>, page:<n>")
    args = ap.parse_args()

    module, cls = APPS[args.app]
    app = getattr(__import__(module, fromlist=[cls]), cls)()
    errors = []

    def act(win):
        if not args.action:
            return
        if args.action == "run-checks":
            win.run_checks()
        elif args.action.startswith("search:"):
            win.entry.set_text(args.action.split(":", 1)[1])
        elif args.action.startswith("page:"):
            lb = win.split.get_sidebar().get_child().get_content().get_child().get_child()
            lb.select_row(lb.get_row_at_index(int(args.action.split(":", 1)[1])))

    def on_activate(application):
        win = application.get_active_window()
        GLib.timeout_add(500, lambda: (act(win), False)[1])

        def finish():
            try:
                snapshot(win, args.output)
            except Exception as exc:  # report, do not hang
                errors.append(exc)
            application.quit()
            return False

        GLib.timeout_add(int(args.seconds * 1000), finish)

    app.connect_after("activate", on_activate)
    status = app.run([sys.argv[0]])
    if errors:
        print(f"screenshot failed: {errors[0]}", file=sys.stderr)
        return 1
    return status


if __name__ == "__main__":
    sys.exit(main())
