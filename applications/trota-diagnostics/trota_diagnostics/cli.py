"""Command line entry point: GUI by default, --text / --json for terminals.

Exit code in text/JSON mode: 0 = no problems, 1 = warnings, 2 = errors.
"""

from __future__ import annotations

import argparse
import sys

from trota_common import __version__, diagnostics

MARK = {"ok": "[ OK ]", "info": "[INFO]", "warning": "[WARN]", "error": "[FAIL]", "skipped": "[SKIP]"}


def format_text(results) -> str:
    out = []
    for r in results:
        out.append(f"{MARK.get(r.status, r.status)} {r.title}: {r.summary}")
        out.extend(f"         {d}" for d in r.details)
        if r.suggestion:
            out.append(f"         -> {r.suggestion}")
    return "\n".join(out)


def exit_code(results) -> int:
    worst = diagnostics.overall_status(results)
    return {"error": 2, "warning": 1}.get(worst, 0)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="trota-diagnostics",
                                 description="Run safe, read-only checks on this computer.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--text", action="store_true", help="run the checks, print a report and exit")
    mode.add_argument("--json", action="store_true", help="run the checks, print JSON and exit")
    ap.add_argument("--no-dns", action="store_true", help="skip the name-resolution test")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args, rest = ap.parse_known_args(argv)
    if args.text or args.json:
        ctx = diagnostics.Context(resolve=None if args.no_dns else diagnostics.resolve_host)
        results = diagnostics.run_all(ctx)
        print(diagnostics.to_json(results) if args.json else format_text(results))
        return exit_code(results)
    from trota_diagnostics.app import DiagnosticsApp

    return DiagnosticsApp().run([sys.argv[0], *rest])
