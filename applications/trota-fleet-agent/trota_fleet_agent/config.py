"""Configuration and saved state of the agent.

/etc/trota-fleet.conf holds what the administrator sets (panel address and
the enrolment token), in the same KEY=value form as /etc/trota-kiosk.conf so
it can be written by cloud-init. /var/lib/trota-fleet/device.json holds what
the panel gave back at enrolment (device id and secret) and is readable only
by root.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

CONF = Path("/etc/trota-fleet.conf")
STATE = Path("/var/lib/trota-fleet/device.json")

_LINE = re.compile(r"^\s*([A-Z_][A-Z0-9_]*)=(.*)$")


def read_conf(path: Path = CONF) -> dict:
    """KEY=value pairs of a shell-style file; quotes around a value are removed."""
    values = {}
    try:
        text = path.read_text()
    except OSError:
        return values
    for line in text.splitlines():
        m = _LINE.match(line)
        if m and not line.lstrip().startswith("#"):
            v = m.group(2).strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                v = v[1:-1]
            values[m.group(1)] = v
    return values


def set_conf_value(path: Path, key: str, value: str) -> None:
    """Replace (or append) KEY=value, keeping comments and the other lines."""
    if "\n" in value or "\r" in value:
        raise ValueError("valore con un a capo")
    try:
        lines = path.read_text().splitlines()
    except FileNotFoundError:
        lines = []
    out, done = [], False
    for line in lines:
        m = _LINE.match(line)
        if m and m.group(1) == key and not line.lstrip().startswith("#"):
            if not done:
                out.append(f"{key}={value}")
                done = True
            continue
        out.append(line)
    if not done:
        out.append(f"{key}={value}")
    _write_atomic(path, "\n".join(out) + "\n", 0o644)


def check_url(url: str, insecure: bool = False) -> str:
    """The panel address, without a trailing slash. HTTPS is required except
    for the local machine or with TROTA_FLEET_INSECURE=yes (test networks)."""
    parts = urlsplit(url.strip())
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise ValueError(f"indirizzo non valido: {url!r}")
    local = parts.hostname in ("localhost", "127.0.0.1", "::1")
    if parts.scheme == "http" and not (local or insecure):
        raise ValueError("l'indirizzo del pannello deve iniziare con https://")
    return url.strip().rstrip("/")


@dataclass
class Settings:
    url: str = ""
    token: str = ""
    insecure: bool = False

    @classmethod
    def load(cls, path: Path = CONF) -> "Settings":
        v = read_conf(path)
        return cls(v.get("TROTA_FLEET_URL", ""), v.get("TROTA_FLEET_TOKEN", ""),
                   v.get("TROTA_FLEET_INSECURE", "no").lower() == "yes")


@dataclass
class State:
    device_id: str = ""
    secret: str = ""
    url: str = ""
    # Results of the commands already run, kept until the panel has them.
    results: list = field(default_factory=list)
    done: list = field(default_factory=list)  # ids of the commands already run

    @property
    def enrolled(self) -> bool:
        return bool(self.device_id and self.secret)

    @classmethod
    def load(cls, path: Path = STATE) -> "State":
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            return cls()
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})

    def save(self, path: Path = STATE) -> None:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.done = self.done[-200:]
        _write_atomic(path, json.dumps(self.__dict__, indent=1), 0o600)


def _write_atomic(path: Path, text: str, mode: int) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)
