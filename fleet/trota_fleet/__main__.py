"""python3 -m trota_fleet serve | adduser NAME | users | backup DIR"""

from __future__ import annotations

import argparse
import getpass
import os
import sqlite3
import sys
import time
from pathlib import Path
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from trota_fleet import __version__
from trota_fleet.db import Store
from trota_fleet.web import App


class ThreadingServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class QuietHandler(WSGIRequestHandler):
    def log_request(self, code="-", size="-"):
        # The device check-ins would fill the log: only errors are written.
        if str(code)[0] in "45":
            super().log_request(code, size)


def backup(db: str, folder: Path, keep: int = 14) -> int:
    """A consistent copy of the database while the panel is running."""
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = folder / time.strftime("fleet-%Y%m%d-%H%M%S.db")
    with sqlite3.connect(db) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    target.chmod(0o600)
    for old in sorted(folder.glob("fleet-*.db"))[:-keep]:
        old.unlink()
    print(f"Copia salvata in {target}")
    return 0


def main(argv=None) -> int:
    env = os.environ.get
    ap = argparse.ArgumentParser(prog="trota-fleet", description="Pannello Trota Fleet.")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("--db", default=env("TROTA_FLEET_DB", "/var/lib/trota-fleet-panel/fleet.db"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="avvia il pannello")
    s.add_argument("--listen", default=env("TROTA_FLEET_LISTEN", "127.0.0.1:8080"), help="indirizzo:porta")
    s.add_argument("--public-url", default=env("TROTA_FLEET_PUBLIC_URL", ""),
                   help="indirizzo pubblico del pannello, mostrato nei comandi di registrazione")
    s.add_argument("--behind-proxy", action="store_true", default=env("TROTA_FLEET_BEHIND_PROXY", "") == "1",
                   help="fidarsi delle intestazioni X-Forwarded-* del proxy davanti al pannello")
    s.add_argument("--interval", type=int, default=int(env("TROTA_FLEET_INTERVAL", "60")),
                   help="secondi tra un contatto e l'altro dei dispositivi")
    u = sub.add_parser("adduser", help="crea un amministratore o ne cambia la password")
    u.add_argument("name")
    sub.add_parser("users", help="elenca gli amministratori")
    b = sub.add_parser("backup", help="copia del database in una cartella (tiene le ultime 14)")
    b.add_argument("dir")
    args = ap.parse_args(argv)

    os.makedirs(os.path.dirname(os.path.abspath(args.db)), exist_ok=True)
    store = Store(args.db)
    if args.cmd == "adduser":
        password = env("TROTA_FLEET_PASSWORD") or getpass.getpass("Password: ")
        if len(password) < 12:
            print("La password deve avere almeno 12 caratteri.", file=sys.stderr)
            return 1
        if not env("TROTA_FLEET_PASSWORD") and getpass.getpass("Ripeti la password: ") != password:
            print("Le password non coincidono.", file=sys.stderr)
            return 1
        store.set_user(args.name, password)
        print(f"Amministratore {args.name} salvato.")
        return 0
    if args.cmd == "backup":
        return backup(args.db, Path(args.dir))
    if args.cmd == "users":
        for user in store.users():
            print(user["name"])
        return 0

    if not store.users():
        print("Nessun amministratore: crearne uno con  python3 -m trota_fleet adduser NOME", file=sys.stderr)
        return 1
    host, _, port = args.listen.rpartition(":")
    app = App(store, max(15, args.interval), args.behind_proxy, args.public_url)
    with make_server(host.strip("[]") or "127.0.0.1", int(port), app, ThreadingServer, QuietHandler) as httpd:
        print(f"Trota Fleet {__version__} su http://{args.listen}", flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
