"""Command line entry point: GUI by default, --text / --json and install for terminals.

Exit code of the checks in text/JSON mode: 0 = ready, 1 = warnings, 2 = errors.
"""

from __future__ import annotations

import argparse
import sys

from trota_common import __version__, diagnostics

from . import checks

MARK = {"ok": "[ OK ]", "info": "[INFO]", "warning": "[WARN]", "error": "[FAIL]", "skipped": "[SKIP]"}


def format_text(results) -> str:
    out = []
    for r in results:
        out.append(f"{MARK.get(r.status, r.status)} {r.title}: {r.summary}")
        out.extend(f"         {d}" for d in r.details)
        if r.suggestion:
            out.append(f"         -> {r.suggestion}")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="trota-vr", description="Check this PC for virtual reality.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--text", action="store_true", help="run the checks, print a report and exit")
    mode.add_argument("--json", action="store_true", help="run the checks, print JSON and exit")
    mode.add_argument("--install", choices=[a.key for a in checks.APPS],
                      help="install WiVRn or Steam from Flathub")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args, rest = ap.parse_known_args(argv)
    if args.install:
        app = checks.find_app(args.install)
        print(" ".join(checks.install_command(app)))
        r = checks.install(app)
        if not r.ok:
            print(r.stderr.strip() or "installation failed", file=sys.stderr)
        return 0 if r.ok else 1
    if args.text or args.json:
        results = checks.run_all()
        print(diagnostics.to_json(results) if args.json else format_text(results))
        worst = diagnostics.overall_status(results)
        return {"error": 2, "warning": 1}.get(worst, 0)
    from trota_vr.app import VRApp

    return VRApp().run([sys.argv[0], *rest])
