"""Where the panel keeps its data: a local SQLite file, or a Cloudflare D1
database reached through the Cloudflare API (for hosts without a permanent
disk, such as Render).

Both take a batch of (sql, params) statements and return, for each one, its
rows (as dicts) and the number of rows changed. The statements of a batch
run in order in one request. Parameters are sent as strings, as the D1 API
requires: the INTEGER columns convert them back.
"""

from __future__ import annotations

import http.client
import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field


@dataclass
class Result:
    rows: list = field(default_factory=list)
    changes: int = 0


def _param(value) -> str:
    if value is None or isinstance(value, bool):
        raise TypeError("parametri NULL o booleani non ammessi")
    return str(value)


class SQLiteBackend:
    def __init__(self, path: str):
        self.path = str(path)

    def batch(self, statements) -> list[Result]:
        c = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        c.row_factory = sqlite3.Row
        try:
            c.execute("PRAGMA foreign_keys = ON")
            c.execute("PRAGMA journal_mode = WAL")
            c.execute("BEGIN IMMEDIATE")
            out = []
            for sql, params in statements:
                cur = c.execute(sql, [_param(p) for p in params])
                rows = [dict(r) for r in cur.fetchall()]
                out.append(Result(rows, cur.rowcount if cur.rowcount > 0 else 0))
            c.execute("COMMIT")
            return out
        except BaseException:
            if c.in_transaction:
                c.execute("ROLLBACK")
            raise
        finally:
            c.close()

    def script(self, sql: str) -> None:
        with sqlite3.connect(self.path) as c:
            c.executescript(sql)


class D1Error(RuntimeError):
    pass


class D1Backend:
    """Cloudflare D1 through POST /accounts/{account}/d1/database/{db}/query.
    The token needs the "D1 Edit" permission on the account."""

    HOST = "api.cloudflare.com"

    def __init__(self, account: str, database: str, token: str, host: str = HOST, https: bool = True):
        self.path = f"/client/v4/accounts/{account}/d1/database/{database}/query"
        self.token = token
        self.host = host
        self.https = https
        self.local = threading.local()   # one kept-alive connection per thread

    def _conn(self):
        conn = getattr(self.local, "conn", None)
        if conn is None:
            cls = http.client.HTTPSConnection if self.https else http.client.HTTPConnection
            conn = self.local.conn = cls(self.host, timeout=30)
        return conn

    def _post(self, body: dict) -> list:
        data = json.dumps(body).encode()
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        for attempt in range(3):
            conn = self._conn()
            try:
                conn.request("POST", self.path, data, headers)
                resp = conn.getresponse()
                raw = resp.read()
            except (OSError, http.client.HTTPException):
                # A kept-alive connection closed by the other side: open a new one.
                conn.close()
                self.local.conn = None
                if attempt == 2:
                    raise D1Error("Cloudflare D1 non raggiungibile") from None
                continue
            if resp.status == 429 and attempt < 2:
                time.sleep(1 + attempt)
                continue
            try:
                payload = json.loads(raw)
            except ValueError:
                raise D1Error(f"risposta non valida da Cloudflare D1 (HTTP {resp.status})") from None
            if not payload.get("success"):
                msg = "; ".join(e.get("message", "") for e in payload.get("errors") or []) or f"HTTP {resp.status}"
                raise D1Error(f"Cloudflare D1: {msg}")
            return payload.get("result") or []
        raise D1Error("Cloudflare D1: troppe richieste")

    def batch(self, statements) -> list[Result]:
        body = {"batch": [{"sql": sql, "params": [_param(p) for p in params]} for sql, params in statements]}
        return [Result(r.get("results") or [], (r.get("meta") or {}).get("changes") or 0) for r in self._post(body)]

    def script(self, sql: str) -> None:
        self._post({"sql": sql})
