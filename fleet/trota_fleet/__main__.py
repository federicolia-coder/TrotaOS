"""python3 -m trota_fleet serve | adduser NAME | users | backup DIR"""

from __future__ import annotations

import argparse
import getpass
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from trota_fleet import __version__
from trota_fleet.backends import D1Error
from trota_fleet.db import RETENTION_DAYS, Store
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


def cleanup_loop(store: Store, days: int, every: int = 6 * 3600) -> None:
    """Deletes old data at start and then every few hours (see Store.cleanup)."""
    while True:
        try:
            done = store.cleanup(days)
            if any(done.values()):
                print(f"Pulizia dati vecchi: {done}", flush=True)
        except Exception as exc:  # never stop the panel for this; retry later
            print(f"Pulizia dati vecchi non riuscita: {exc}", file=sys.stderr, flush=True)
        time.sleep(every)


def main(argv=None) -> int:
    env = os.environ.get
    ap = argparse.ArgumentParser(prog="trota-fleet", description="Pannello Trota Fleet.")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("--db", default=env("TROTA_FLEET_DB", "/var/lib/trota-fleet-panel/fleet.db"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="avvia il pannello")
    # Render (and similar hosts) give the port in $PORT.
    listen = env("TROTA_FLEET_LISTEN") or (f"0.0.0.0:{env('PORT')}" if env("PORT") else "127.0.0.1:8080")
    s.add_argument("--listen", default=listen, help="indirizzo:porta")
    s.add_argument("--public-url", default=env("TROTA_FLEET_PUBLIC_URL", ""),
                   help="indirizzo pubblico del pannello, mostrato nei comandi di registrazione")
    s.add_argument("--behind-proxy", action="store_true", default=env("TROTA_FLEET_BEHIND_PROXY", "") == "1",
                   help="fidarsi delle intestazioni X-Forwarded-* del proxy davanti al pannello")
    s.add_argument("--ip-header", default=env("TROTA_FLEET_IP_HEADER", ""),
                   help="intestazione con l'indirizzo del visitatore messa dal proxy, es. CF-Connecting-IP")
    s.add_argument("--retention-days", type=int, default=int(env("TROTA_FLEET_RETENTION_DAYS", RETENTION_DAYS)),
                   help="giorni dopo cui si cancellano storico dei comandi e codici scaduti")
    s.add_argument("--interval", type=int, default=int(env("TROTA_FLEET_INTERVAL", "60")),
                   help="secondi tra un contatto e l'altro dei dispositivi")
    u = sub.add_parser("adduser", help="crea un amministratore o ne cambia la password")
    u.add_argument("name")
    sub.add_parser("users", help="elenca gli amministratori")
    b = sub.add_parser("backup", help="copia del database in una cartella (tiene le ultime 14)")
    b.add_argument("dir")
    args = ap.parse_args(argv)

    d1 = [env("TROTA_FLEET_D1_ACCOUNT", ""), env("TROTA_FLEET_D1_DATABASE", ""), env("TROTA_FLEET_D1_TOKEN", "")]
    if any(d1):
        if not all(d1):
            print("Per Cloudflare D1 servono TROTA_FLEET_D1_ACCOUNT, TROTA_FLEET_D1_DATABASE e TROTA_FLEET_D1_TOKEN.",
                  file=sys.stderr)
            return 1
        if args.cmd == "backup":
            print("Con D1 le copie le fa Cloudflare (Time Travel): dashboard → D1 → database → Time Travel.",
                  file=sys.stderr)
            return 1
        try:
            store = Store.d1(*[x.strip() for x in d1])
        except D1Error as exc:
            print(f"{exc}\nControllare che il token abbia il permesso \"Account → D1 → Edit\" sull'account "
                  "TROTA_FLEET_D1_ACCOUNT e che il database TROTA_FLEET_D1_DATABASE sia in quello stesso account.",
                  file=sys.stderr)
            return 1
    else:
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
        # Hosts without a shell (Render free): the first administrator comes
        # from the environment, once; the variables can be removed afterwards.
        name, password = env("TROTA_FLEET_ADMIN", ""), env("TROTA_FLEET_ADMIN_PASSWORD", "")
        if not (name and len(password) >= 12):
            print("Nessun amministratore: crearne uno con  python3 -m trota_fleet adduser NOME  oppure con "
                  "TROTA_FLEET_ADMIN e TROTA_FLEET_ADMIN_PASSWORD (almeno 12 caratteri).", file=sys.stderr)
            return 1
        store.set_user(name, password)
        print(f"Primo amministratore creato: {name}", flush=True)
    host, _, port = args.listen.rpartition(":")
    days = max(1, args.retention_days)
    app = App(store, max(15, args.interval), args.behind_proxy, args.public_url, args.ip_header, days)
    threading.Thread(target=cleanup_loop, args=(store, days), daemon=True).start()
    with make_server(host.strip("[]") or "127.0.0.1", int(port), app, ThreadingServer, QuietHandler) as httpd:
        print(f"Trota Fleet {__version__} su http://{args.listen}", flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
