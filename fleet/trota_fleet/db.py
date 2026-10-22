"""Storage of the panel: a local SQLite file or Cloudflare D1 (backends.py).

Every operation is one request with one or more statements; nothing relies
on a transaction across requests (D1 has none): the steps that must not race,
such as using an enrolment code, are single statements.

Secrets are never stored in clear: passwords as PBKDF2, device secrets,
session tokens and enrolment codes as SHA-256 (they are long random values,
so a plain hash is enough).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path

from trota_fleet.backends import D1Backend, SQLiteBackend

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    created INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,           -- sha256 of the cookie value
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf TEXT NOT NULL,
    expires INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS enrol_codes (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,        -- sha256 of the code
    customer TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    uses_left INTEGER NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    expires INTEGER NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    created INTEGER NOT NULL,
    created_by TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    secret TEXT NOT NULL,             -- sha256 of the device secret
    machine TEXT NOT NULL UNIQUE,
    hostname TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    customer TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    enrolled INTEGER NOT NULL,
    last_seen INTEGER,
    last_ip TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY,
    device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    args TEXT NOT NULL DEFAULT '{}',
    created INTEGER NOT NULL,
    created_by TEXT NOT NULL,
    sent INTEGER,
    done INTEGER,
    ok INTEGER,
    output TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS commands_device ON commands(device_id, id);
"""

PBKDF2_ITERATIONS = 600_000
SESSION_DAYS = 7
# Command history and spent enrolment codes are deleted after this many days
# (data minimisation, GDPR art. 5.1.e). Devices stay until they are removed.
RETENTION_DAYS = 90


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password: str, iterations: int | None = None) -> str:
    iterations = iterations or PBKDF2_ITERATIONS
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def check_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, digest = stored.split("$")
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    test = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations)).hex()
    return hmac.compare_digest(test, digest)


_dummy = []


def _dummy_password() -> str:
    if not _dummy:
        _dummy.append(hash_password(secrets.token_hex(8)))
    return _dummy[0]


class Store:
    def __init__(self, path: str | Path | None = None, backend=None):
        self.db = backend or SQLiteBackend(str(path))
        self.db.script(SCHEMA)

    @classmethod
    def d1(cls, account: str, database: str, token: str) -> "Store":
        return cls(backend=D1Backend(account, database, token))

    def query(self, sql: str, *params) -> list:
        return self.db.batch([(sql, params)])[0].rows

    def one(self, sql: str, *params):
        rows = self.query(sql, *params)
        return rows[0] if rows else None

    def run(self, *statements) -> list:
        return self.db.batch(statements)

    # --- users and sessions ---------------------------------------------
    def set_user(self, name: str, password: str) -> None:
        self.run(("INSERT INTO users (name, password, created) VALUES (?, ?, ?) "
                  "ON CONFLICT(name) DO UPDATE SET password = excluded.password",
                  (name, hash_password(password), int(time.time()))),
                 # A new password ends the open sessions of that user.
                 ("DELETE FROM sessions WHERE user_id = (SELECT id FROM users WHERE name = ?)", (name,)))

    def users(self) -> list:
        return self.query("SELECT id, name, created FROM users ORDER BY name")

    def login(self, name: str, password: str) -> tuple[str, str] | None:
        row = self.one("SELECT id, password FROM users WHERE name = ?", name)
        # Same work whether the user exists or not.
        stored = row["password"] if row else _dummy_password()
        if not check_password(password, stored) or not row:
            return None
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        now = int(time.time())
        self.run(("DELETE FROM sessions WHERE expires < ?", (now,)),
                 ("INSERT INTO sessions VALUES (?, ?, ?, ?)", (sha256(token), row["id"], csrf, now + SESSION_DAYS * 86400)))
        return token, csrf

    def session(self, token: str):
        if not token:
            return None
        return self.one("SELECT s.csrf, u.name FROM sessions s JOIN users u ON u.id = s.user_id "
                        "WHERE s.token = ? AND s.expires > ?", sha256(token), int(time.time()))

    def logout(self, token: str) -> None:
        self.query("DELETE FROM sessions WHERE token = ?", sha256(token))

    # --- enrolment codes ------------------------------------------------
    def create_code(self, customer: str, note: str, uses: int, days: int, by: str) -> str:
        code = "TF-" + secrets.token_urlsafe(18)
        now = int(time.time())
        self.query("INSERT INTO enrol_codes (code, customer, note, uses_left, expires, created, created_by) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?)", sha256(code), customer, note, uses, now + days * 86400, now, by)
        return code

    def codes(self) -> list:
        return self.query("SELECT * FROM enrol_codes ORDER BY created DESC, id DESC")

    def revoke_code(self, code_id: int) -> None:
        self.query("UPDATE enrol_codes SET revoked = 1 WHERE id = ?", code_id)

    def enroll(self, code: str, hostname: str, machine: str, ip: str) -> tuple[str, str] | None:
        """A valid code gives the device an id and a secret. A device that
        enrols again (same machine) keeps its id, name and history."""
        now = int(time.time())
        # One statement: two devices cannot both take the last use of a code.
        used = self.one("UPDATE enrol_codes SET uses_left = uses_left - 1, used = used + 1 "
                        "WHERE code = ? AND revoked = 0 AND uses_left > 0 AND expires > ? RETURNING customer",
                        sha256(code), now)
        if not used:
            return None
        secret = secrets.token_urlsafe(32)
        row = self.one("INSERT INTO devices (id, secret, machine, hostname, name, customer, enrolled, last_ip) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(machine) DO UPDATE SET "
                       "secret = excluded.secret, hostname = excluded.hostname, last_ip = excluded.last_ip "
                       "RETURNING id", "d" + secrets.token_hex(6), sha256(secret), machine, hostname, hostname,
                       used["customer"], now, ip)
        return row["id"], secret

    # --- devices --------------------------------------------------------
    def checkin(self, bearer: str, status: dict, results: list, ip: str) -> list | None:
        """Stores the report and the results and returns the commands to run,
        or None if the credentials are wrong. One request: every statement
        checks the device secret itself."""
        device, _, secret = bearer.partition(".")
        if not device or not secret:
            return None
        auth = "(SELECT id FROM devices WHERE id = ? AND secret = ?)"
        key = (device, sha256(secret))
        now = int(time.time())
        stmts = [("UPDATE devices SET last_seen = ?, last_ip = ?, status = ?, hostname = ? WHERE id = ? AND secret = ?",
                  (now, ip, json.dumps(status), str(status.get("hostname", ""))[:200], *key))]
        for r in results:
            if isinstance(r, dict) and isinstance(r.get("id"), int) and not isinstance(r.get("id"), bool):
                stmts.append((f"UPDATE commands SET done = ?, ok = ?, output = ? WHERE id = ? AND done IS NULL "
                              f"AND device_id = {auth}",
                              (now, 1 if r.get("ok") else 0, str(r.get("output", ""))[:8000], r["id"], *key)))
        stmts.append((f"SELECT id, type, args FROM commands WHERE device_id = {auth} AND done IS NULL ORDER BY id", key))
        stmts.append((f"UPDATE commands SET sent = ? WHERE device_id = {auth} AND done IS NULL AND sent IS NULL",
                      (now, *key)))
        out = self.run(*stmts)
        if out[0].changes == 0:
            return None
        return [{"id": r["id"], "type": r["type"], "args": json.loads(r["args"])} for r in out[-2].rows]

    def devices(self, customer: str | None = None, query: str = "") -> list:
        sql, args = "SELECT * FROM devices WHERE 1", []
        if customer is not None:
            sql += " AND customer = ?"
            args.append(customer)
        if query:
            sql += " AND (name LIKE ? OR hostname LIKE ? OR last_ip LIKE ? OR notes LIKE ?)"
            args += [f"%{query}%"] * 4
        return self.query(sql + " ORDER BY customer, name", *args)

    def customers(self) -> list[str]:
        return [r["customer"] for r in self.query("SELECT DISTINCT customer FROM devices ORDER BY customer")]

    def device(self, device: str):
        return self.one("SELECT * FROM devices WHERE id = ?", device)

    def update_device(self, device: str, name: str, customer: str, notes: str) -> None:
        self.query("UPDATE devices SET name = ?, customer = ?, notes = ? WHERE id = ?", name, customer, notes, device)

    def delete_device(self, device: str) -> None:
        self.run(("DELETE FROM commands WHERE device_id = ?", (device,)),
                 ("DELETE FROM devices WHERE id = ?", (device,)))

    def queue(self, device: str, kind: str, args: dict, by: str) -> int:
        row = self.one("INSERT INTO commands (device_id, type, args, created, created_by) VALUES (?, ?, ?, ?, ?) "
                       "RETURNING id", device, kind, json.dumps(args), int(time.time()), by)
        return row["id"]

    def cancel(self, device: str, command: int) -> None:
        self.query("DELETE FROM commands WHERE id = ? AND device_id = ? AND sent IS NULL", command, device)

    def commands(self, device: str, limit: int = 50) -> list:
        return self.query(f"SELECT * FROM commands WHERE device_id = ? ORDER BY id DESC LIMIT {int(limit)}", device)

    # --- retention --------------------------------------------------------
    def cleanup(self, days: int = RETENTION_DAYS) -> dict:
        """Deletes what is no longer needed: expired sessions, commands older
        than *days* (finished or never delivered), enrolment codes expired,
        revoked or used up more than *days* ago."""
        now = int(time.time())
        limit = now - days * 86400
        out = self.run(("DELETE FROM sessions WHERE expires < ?", (now,)),
                       ("DELETE FROM commands WHERE created < ?", (limit,)),
                       ("DELETE FROM enrol_codes WHERE (expires < ? OR revoked = 1 OR uses_left <= 0) AND created < ?",
                        (now, limit)))
        return dict(zip(("sessions", "commands", "codes"), (r.changes for r in out)))
