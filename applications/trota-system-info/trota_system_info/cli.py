"""Command line entry point: GUI by default, --text / --json for terminals.

The text and JSON modes do not import GTK, so they work over SSH and on
systems without a display.
"""

from __future__ import annotations

import argparse
import sys

from trota_common import __version__, sysinfo


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="trota-system-info",
                                 description="Show information about this computer (collected locally).")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--text", action="store_true", help="print a plain-text report and exit")
    mode.add_argument("--json", action="store_true", help="print a JSON report and exit")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args, rest = ap.parse_known_args(argv)
    if args.text or args.json:
        report = sysinfo.collect()
        print(report.to_json() if args.json else sysinfo.report_text(report))
        return 0
    from trota_system_info.app import SystemInfoApp

    return SystemInfoApp().run([sys.argv[0], *rest])
