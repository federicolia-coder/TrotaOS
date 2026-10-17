"""SQLite storage of the panel.

Secrets are never stored in clear: passwords as PBKDF2, device secrets,
session tokens and enrolment codes as SHA-256 (they are long random values,
so a plain hash is enough).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from pathlib import Path

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
    def __init__(self, path: str | Path):
        self.path = str(path)
        with self.connect() as c:
            c.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        c.execute("PRAGMA journal_mode = WAL")
        return c

    # --- users and sessions ---------------------------------------------
    def set_user(self, name: str, password: str) -> None:
        with self.connect() as c:
            c.execute("INSERT INTO users (name, password, created) VALUES (?, ?, ?) "
                      "ON CONFLICT(name) DO UPDATE SET password = excluded.password",
                      (name, hash_password(password), int(time.time())))
            # A new password ends the open sessions of that user.
            c.execute("DELETE FROM sessions WHERE user_id = (SELECT id FROM users WHERE name = ?)", (name,))

    def users(self) -> list:
        with self.connect() as c:
            return c.execute("SELECT id, name, created FROM users ORDER BY name").fetchall()

    def login(self, name: str, password: str) -> tuple[str, str] | None:
        with self.connect() as c:
            row = c.execute("SELECT id, password FROM users WHERE name = ?", (name,)).fetchone()
            # Same work whether the user exists or not.
            stored = row["password"] if row else _dummy_password()
            if not check_password(password, stored) or not row:
                return None
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
            now = int(time.time())
            c.execute("DELETE FROM sessions WHERE expires < ?", (now,))
            c.execute("INSERT INTO sessions VALUES (?, ?, ?, ?)",
                      (sha256(token), row["id"], csrf, now + SESSION_DAYS * 86400))
            return token, csrf

    def session(self, token: str):
        if not token:
            return None
        with self.connect() as c:
            return c.execute("SELECT s.csrf, u.name FROM sessions s JOIN users u ON u.id = s.user_id "
                             "WHERE s.token = ? AND s.expires > ?", (sha256(token), int(time.time()))).fetchone()

    def logout(self, token: str) -> None:
        with self.connect() as c:
            c.execute("DELETE FROM sessions WHERE token = ?", (sha256(token),))

    # --- enrolment codes ------------------------------------------------
    def create_code(self, customer: str, note: str, uses: int, days: int, by: str) -> str:
        code = "TF-" + secrets.token_urlsafe(18)
        now = int(time.time())
        with self.connect() as c:
            c.execute("INSERT INTO enrol_codes (code, customer, note, uses_left, expires, created, created_by) "
                      "VALUES (?, ?, ?, ?, ?, ?, ?)", (sha256(code), customer, note, uses, now + days * 86400, now, by))
        return code

    def codes(self) -> list:
        with self.connect() as c:
            return c.execute("SELECT * FROM enrol_codes ORDER BY created DESC, id DESC").fetchall()

    def revoke_code(self, code_id: int) -> None:
        with self.connect() as c:
            c.execute("UPDATE enrol_codes SET revoked = 1 WHERE id = ?", (code_id,))

    def enroll(self, code: str, hostname: str, machine: str, ip: str) -> tuple[str, str] | None:
        """A valid code gives the device an id and a secret. A device that
        enrols again (same machine) keeps its id, name and history."""
        now = int(time.time())
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT * FROM enrol_codes WHERE code = ? AND revoked = 0 AND uses_left > 0 "
                            "AND expires > ?", (sha256(code), now)).fetchone()
            if not row:
                c.execute("ROLLBACK")
                return None
            c.execute("UPDATE enrol_codes SET uses_left = uses_left - 1, used = used + 1 WHERE id = ?", (row["id"],))
            secret = secrets.token_urlsafe(32)
            old = c.execute("SELECT id FROM devices WHERE machine = ?", (machine,)).fetchone()
            if old:
                device = old["id"]
                c.execute("UPDATE devices SET secret = ?, hostname = ?, last_ip = ? WHERE id = ?",
                          (sha256(secret), hostname, ip, device))
            else:
                device = "d" + secrets.token_hex(6)
                c.execute("INSERT INTO devices (id, secret, machine, hostname, name, customer, enrolled, last_ip) "
                          "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                          (device, sha256(secret), machine, hostname, hostname, row["customer"], now, ip))
            c.execute("COMMIT")
            return device, secret

    # --- devices --------------------------------------------------------
    def authenticate(self, bearer: str) -> str | None:
        device, _, secret = bearer.partition(".")
        if not device or not secret:
            return None
        with self.connect() as c:
            row = c.execute("SELECT secret FROM devices WHERE id = ?", (device,)).fetchone()
        if row and hmac.compare_digest(row["secret"], sha256(secret)):
            return device
        return None

    def checkin(self, device: str, status: dict, results: list, ip: str) -> list:
        """Stores the report and the results; returns the commands to run."""
        now = int(time.time())
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("UPDATE devices SET last_seen = ?, last_ip = ?, status = ?, hostname = ? WHERE id = ?",
                      (now, ip, json.dumps(status), str(status.get("hostname", ""))[:200], device))
            for r in results:
                if not isinstance(r, dict) or not isinstance(r.get("id"), int):
                    continue
                c.execute("UPDATE commands SET done = ?, ok = ?, output = ? WHERE id = ? AND device_id = ? "
                          "AND done IS NULL", (now, 1 if r.get("ok") else 0, str(r.get("output", ""))[:8000],
                                               r["id"], device))
            rows = c.execute("SELECT id, type, args FROM commands WHERE device_id = ? AND done IS NULL ORDER BY id",
                             (device,)).fetchall()
            c.execute("UPDATE commands SET sent = ? WHERE device_id = ? AND done IS NULL AND sent IS NULL",
                      (now, device))
            c.execute("COMMIT")
        return [{"id": r["id"], "type": r["type"], "args": json.loads(r["args"])} for r in rows]

    def devices(self, customer: str | None = None, query: str = "") -> list:
        sql, args = "SELECT * FROM devices WHERE 1", []
        if customer is not None:
            sql += " AND customer = ?"
            args.append(customer)
        if query:
            sql += " AND (name LIKE ? OR hostname LIKE ? OR last_ip LIKE ? OR notes LIKE ?)"
            args += [f"%{query}%"] * 4
        with self.connect() as c:
            return c.execute(sql + " ORDER BY customer, name", args).fetchall()

    def customers(self) -> list[str]:
        with self.connect() as c:
            return [r[0] for r in c.execute("SELECT DISTINCT customer FROM devices ORDER BY customer")]

    def device(self, device: str):
        with self.connect() as c:
            return c.execute("SELECT * FROM devices WHERE id = ?", (device,)).fetchone()

    def update_device(self, device: str, name: str, customer: str, notes: str) -> None:
        with self.connect() as c:
            c.execute("UPDATE devices SET name = ?, customer = ?, notes = ? WHERE id = ?",
                      (name, customer, notes, device))

    def delete_device(self, device: str) -> None:
        with self.connect() as c:
            c.execute("DELETE FROM devices WHERE id = ?", (device,))

    def queue(self, device: str, kind: str, args: dict, by: str) -> int:
        with self.connect() as c:
            cur = c.execute("INSERT INTO commands (device_id, type, args, created, created_by) VALUES (?, ?, ?, ?, ?)",
                            (device, kind, json.dumps(args), int(time.time()), by))
            return cur.lastrowid

    def cancel(self, device: str, command: int) -> None:
        with self.connect() as c:
            c.execute("DELETE FROM commands WHERE id = ? AND device_id = ? AND sent IS NULL", (command, device))

    def commands(self, device: str, limit: int = 50) -> list:
        with self.connect() as c:
            return c.execute("SELECT * FROM commands WHERE device_id = ? ORDER BY id DESC LIMIT ?",
                             (device, limit)).fetchall()
