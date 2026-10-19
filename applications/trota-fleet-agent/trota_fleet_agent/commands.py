"""The commands a panel can send. This list is the whole of what the panel
can do on a device: anything else is refused, and no command takes a program
or a shell line as argument.

  kiosk-url      show another page on the kiosk  {"url": "https://..."}
  kiosk-restart  restart the kiosk browser
  update         install all the available updates (apt)
  reboot         restart the device (after the result has been sent)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from trota_fleet_agent import status
from trota_fleet_agent.config import set_conf_value

KIOSK_CONF = Path("/etc/trota-kiosk.conf")
OUTPUT_LIMIT = 4000
APT_ENV = ["env", "DEBIAN_FRONTEND=noninteractive"]
APT_OPTS = ["-o", "Dpkg::Options::=--force-confdef", "-o", "Dpkg::Options::=--force-confold"]


@dataclass
class Outcome:
    ok: bool
    output: str = ""
    # Run after the result has reached the panel (a reboot would lose it).
    after: Callable[[], None] | None = None


def _tail(text: str) -> str:
    text = text.strip()
    return text if len(text) <= OUTPUT_LIMIT else "…\n" + text[-OUTPUT_LIMIT:]


def kiosk_url(args: dict, run=status.run, conf: Path = KIOSK_CONF) -> Outcome:
    url = str(args.get("url", "")).strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https", "file") or (parts.scheme != "file" and not parts.hostname):
        return Outcome(False, f"indirizzo non valido: {url!r}")
    if any(c in url for c in "\n\r\"'`$\\ "):
        return Outcome(False, "l'indirizzo contiene caratteri non ammessi")
    if not conf.exists():
        return Outcome(False, "questo dispositivo non è un kiosk")
    set_conf_value(conf, "TROTA_KIOSK_URL", url)
    code, out = run(["systemctl", "restart", "trota-kiosk.service"])
    return Outcome(code == 0, _tail(out) or f"pagina impostata: {url}")


def kiosk_restart(args: dict, run=status.run) -> Outcome:
    code, out = run(["systemctl", "restart", "trota-kiosk.service"])
    return Outcome(code == 0, _tail(out) or "kiosk riavviato")


def update(args: dict, run=status.run) -> Outcome:
    code, out = run(APT_ENV + ["apt-get", "update"], timeout=900)
    if code != 0:
        return Outcome(False, _tail(out))
    code, out2 = run(APT_ENV + ["apt-get", "-y", *APT_OPTS, "full-upgrade"], timeout=3600)
    # The panel shows the new count at the next check-in.
    status._updates_cache.clear()
    return Outcome(code == 0, _tail(out2))


def reboot(args: dict, run=status.run) -> Outcome:
    return Outcome(True, "riavvio in corso", after=lambda: run(["systemctl", "reboot"]))


HANDLERS = {
    "kiosk-url": kiosk_url,
    "kiosk-restart": kiosk_restart,
    "update": update,
    "reboot": reboot,
}


def execute(kind: str, args: dict | None, handlers: dict = HANDLERS) -> Outcome:
    handler = handlers.get(kind)
    if handler is None:
        return Outcome(False, f"comando sconosciuto: {kind!r}")
    try:
        return handler(args if isinstance(args, dict) else {})
    except Exception as exc:  # one broken command must not stop the agent
        return Outcome(False, f"errore: {exc}")
