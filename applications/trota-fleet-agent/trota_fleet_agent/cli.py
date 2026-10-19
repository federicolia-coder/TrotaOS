"""trota-fleet-agent command line (run as root; the service runs "run")."""

from __future__ import annotations

import argparse
import json
import sys

from trota_fleet_agent import __version__, status
from trota_fleet_agent.agent import Agent, PanelError
from trota_fleet_agent.config import CONF, STATE, Settings, check_url, set_conf_value


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="trota-fleet-agent",
                                 description="Collega questo dispositivo a un pannello Trota Fleet.")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("enroll", help="registra il dispositivo nel pannello")
    e.add_argument("url", nargs="?", help="indirizzo del pannello (https://...)")
    e.add_argument("token", nargs="?", help="codice di registrazione creato nel pannello")
    sub.add_parser("run", help="resta collegato al pannello (usato dal servizio)")
    sub.add_parser("once", help="un solo contatto con il pannello")
    sub.add_parser("status", help="mostra il rapporto che viene inviato al pannello")
    sub.add_parser("configured", help="esce con 0 se il pannello è configurato")
    sub.add_parser("leave", help="dimentica la registrazione (il pannello va pulito a parte)")
    args = ap.parse_args(argv)

    settings = Settings.load()
    agent = Agent()
    try:
        if args.cmd == "status":
            print(json.dumps(status.collect(), indent=2, ensure_ascii=False))
            return 0
        if args.cmd == "configured":
            return 0 if settings.url and (agent.state.enrolled or settings.token) else 1
        if args.cmd == "leave":
            STATE.unlink(missing_ok=True)
            print("Registrazione rimossa.")
            return 0
        if args.cmd == "enroll":
            url = args.url or settings.url
            token = args.token or settings.token
            if not url or not token:
                ap.error(f"servono l'indirizzo del pannello e il codice di registrazione (o {CONF})")
            url = check_url(url, settings.insecure)
            agent.enroll(url, token, settings.insecure)
            # The service reads the address from here; the token is used once.
            set_conf_value(CONF, "TROTA_FLEET_URL", url)
            set_conf_value(CONF, "TROTA_FLEET_TOKEN", "")
            print(f"Dispositivo registrato in {url} (id {agent.state.device_id}).")
            print("Avviare il collegamento con: sudo systemctl enable --now trota-fleet-agent")
            return 0
        if not agent.state.enrolled:
            if not (settings.url and settings.token):
                print(f"trota-fleet-agent: non registrato e nessun codice in {CONF}", file=sys.stderr)
                return 2
            agent.enroll(settings.url, settings.token, settings.insecure)
            set_conf_value(CONF, "TROTA_FLEET_TOKEN", "")
            print(f"trota-fleet-agent: registrato in {agent.state.url} (id {agent.state.device_id})")
        if args.cmd == "once":
            agent.checkin()
            return 0
        return agent.run_forever()
    except (PanelError, ValueError) as exc:
        print(f"trota-fleet-agent: {exc}", file=sys.stderr)
        return 1
    except PermissionError:
        print("trota-fleet-agent: serve root (sudo)", file=sys.stderr)
        return 1
