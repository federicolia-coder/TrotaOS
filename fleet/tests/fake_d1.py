"""A local stand-in for the Cloudflare D1 query API, close enough to test the
panel against: same URL, Bearer token, {"batch": [...]} body, parameters
bound as strings, same response shape. Statements are not atomic together,
like the real API gives no guarantee about it."""

import json
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = "test-token"
PATH = "/client/v4/accounts/acc/d1/database/db/query"


class FakeD1:
    def __init__(self, path):
        self.path = str(path)
        self.lock = threading.Lock()
        self.requests = 0
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if self.path != PATH or self.headers.get("Authorization") != f"Bearer {TOKEN}":
                    return self.reply(403, {"success": False, "errors": [{"code": 10000, "message": "Authentication error"}]})
                fake.requests += 1
                try:
                    reply = fake.execute(json.loads(body))
                except sqlite3.Error as exc:
                    return self.reply(400, {"success": False, "errors": [{"code": 7500, "message": str(exc)}]})
                self.reply(200, {"success": True, "errors": [], "messages": [], "result": reply})

            def reply(self, code, payload):
                data = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_port
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def execute(self, body):
        with self.lock, sqlite3.connect(self.path, isolation_level=None) as c:
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys = ON")   # always on in D1
            if "sql" in body and "batch" not in body:
                c.executescript(body["sql"])
                return [{"results": [], "success": True, "meta": {"changes": 0}}]
            out = []
            for stmt in body["batch"]:
                params = stmt.get("params", [])
                assert all(isinstance(p, str) for p in params), "D1 takes string parameters only"
                cur = c.execute(stmt["sql"], params)
                rows = [dict(r) for r in cur.fetchall()]
                out.append({"results": rows, "success": True, "meta": {"changes": max(cur.rowcount, 0)}})
            return out

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
