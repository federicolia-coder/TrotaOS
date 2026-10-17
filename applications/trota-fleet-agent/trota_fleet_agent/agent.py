"""Enrolment and check-in with the panel.

  POST /api/v1/enroll   {"token", "hostname", "machine"}  -> {"device", "secret"}
  POST /api/v1/checkin  Authorization: Bearer <device>.<secret>
                        {"status", "results"}  -> {"commands", "interval"}

A command is run once: its id is recorded before it starts, so a crash or a
reboot in the middle never repeats it, and its result is kept on disk until
the panel has confirmed it.
"""

from __future__ import annotations

import hashlib
import json
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from trota_fleet_agent import __version__, commands, status
from trota_fleet_agent.config import STATE, State, check_url

DEFAULT_INTERVAL = 60
MAX_BACKOFF = 900


class PanelError(Exception):
    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


def machine_hash(path: Path = Path("/etc/machine-id")) -> str:
    """Identifies the device to the panel without revealing its machine-id."""
    try:
        mid = path.read_text().strip()
    except OSError:
        mid = socket.gethostname()
    return hashlib.sha256(f"trota-fleet:{mid}".encode()).hexdigest()[:32]


def post(url: str, payload: dict, auth: str = "", timeout: float = 30) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST", headers={
        "Content-Type": "application/json",
        "User-Agent": f"trota-fleet-agent/{__version__}",
        **({"Authorization": f"Bearer {auth}"} if auth else {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read()).get("error", "")
        except ValueError:
            detail = ""
        raise PanelError(detail or f"HTTP {exc.code}", exc.code) from None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise PanelError(str(getattr(exc, "reason", exc))) from None


class Agent:
    def __init__(self, state_path: Path = STATE, collect=status.collect, execute=commands.execute, send=post):
        self.state_path = state_path
        self.state = State.load(state_path)
        self.collect = collect
        self.execute = execute
        self.send = send

    def enroll(self, url: str, token: str, insecure: bool = False) -> State:
        url = check_url(url, insecure)
        reply = self.send(f"{url}/api/v1/enroll", {
            "token": token, "hostname": socket.gethostname(), "machine": machine_hash(),
        })
        if not reply.get("device") or not reply.get("secret"):
            raise PanelError("risposta del pannello non valida")
        self.state = State(device_id=reply["device"], secret=reply["secret"], url=url)
        self.state.save(self.state_path)
        return self.state

    def checkin(self) -> int:
        """One round trip: report, run the new commands. Returns the interval."""
        st = self.state
        reply = self.send(f"{st.url}/api/v1/checkin", {"status": self.collect(), "results": st.results},
                          auth=f"{st.device_id}.{st.secret}")
        st.results = []
        st.save(self.state_path)
        later = []
        for cmd in reply.get("commands", []):
            cid = cmd.get("id")
            if cid is None or cid in st.done:
                continue
            st.done.append(cid)
            st.save(self.state_path)
            out = self.execute(cmd.get("type", ""), cmd.get("args"))
            st.results.append({"id": cid, "ok": out.ok, "output": out.output, "at": int(time.time())})
            st.save(self.state_path)
            if out.after:
                later.append(out.after)
        if later:
            # Deliver the results first: a reboot would otherwise keep them
            # waiting until the device is back.
            try:
                self.send(f"{st.url}/api/v1/checkin", {"status": self.collect(), "results": st.results},
                          auth=f"{st.device_id}.{st.secret}")
                st.results = []
                st.save(self.state_path)
            except PanelError:
                pass
            for action in later:
                action()
        return int(reply.get("interval") or DEFAULT_INTERVAL)

    def run_forever(self, sleep=time.sleep) -> int:
        failures = 0
        while True:
            try:
                interval = self.checkin()
                failures = 0
            except PanelError as exc:
                if exc.code == 401:
                    print("trota-fleet-agent: il pannello non riconosce più questo dispositivo "
                          "(rimosso?). Registrarlo di nuovo con: trota-fleet-agent enroll", file=sys.stderr)
                    return 3
                failures += 1
                interval = min(DEFAULT_INTERVAL * 2 ** min(failures, 4), MAX_BACKOFF)
                print(f"trota-fleet-agent: pannello non raggiungibile ({exc}), nuovo tentativo tra {interval}s",
                      file=sys.stderr)
            sleep(max(10, min(interval, MAX_BACKOFF)))
