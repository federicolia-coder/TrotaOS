"""The panel as a WSGI application: administration pages and device API.

Runs with the built-in server (python3 -m trota_fleet serve) or any WSGI
server. TLS is left to a reverse proxy in front (Caddy, nginx).
"""

from __future__ import annotations

import json
import re
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from importlib import resources
from urllib.parse import parse_qs, quote, urlsplit

from trota_fleet import views as v
from trota_fleet.backends import D1Error
from trota_fleet.db import Store

MAX_BODY = 512 * 1024
COOKIE = "trota_fleet"
# Login and enrolment attempts per address before a pause.
MAX_FAILURES = 10
LOCK_SECONDS = 900

COMMANDS = {
    "kiosk-url": "Cambia la pagina del kiosk",
    "kiosk-restart": "Riavvia il kiosk",
    "update": "Installa gli aggiornamenti",
    "reboot": "Riavvia il dispositivo",
}

CSP = ("default-src 'none'; style-src 'self'; script-src 'self'; img-src 'self' data:; "
       "form-action 'self'; frame-ancestors 'none'; base-uri 'none'")


class Request:
    def __init__(self, environ: dict, behind_proxy: bool, ip_header: str = ""):
        self.environ = environ
        self.method = environ.get("REQUEST_METHOD", "GET")
        self.path = environ.get("PATH_INFO", "/") or "/"
        self.query = {k: x[0] for k, x in parse_qs(environ.get("QUERY_STRING", "")).items()}
        cookies = SimpleCookie(environ.get("HTTP_COOKIE", ""))
        self.cookie = cookies[COOKIE].value if COOKIE in cookies else ""
        forwarded = environ.get("HTTP_X_FORWARDED_FOR", "")
        if ip_header and environ.get(ip_header):
            # Set by the proxy in front (e.g. CF-Connecting-IP behind Cloudflare).
            self.ip = environ[ip_header].strip()
        else:
            self.ip = (forwarded.split(",")[-1].strip() if behind_proxy and forwarded
                       else environ.get("REMOTE_ADDR", ""))
        proto = environ.get("HTTP_X_FORWARDED_PROTO", "") if behind_proxy else ""
        self.https = (proto or environ.get("wsgi.url_scheme", "http")) == "https"
        host = (environ.get("HTTP_X_FORWARDED_HOST", "") if behind_proxy else "") or environ.get("HTTP_HOST", "")
        self.base = f"{'https' if self.https else 'http'}://{host}"
        self._body = None

    def body(self) -> bytes:
        if self._body is None:
            try:
                n = int(self.environ.get("CONTENT_LENGTH") or 0)
            except ValueError:
                n = 0
            if n > MAX_BODY:
                raise HttpError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            self._body = self.environ["wsgi.input"].read(n) if n > 0 else b""
        return self._body

    def form(self) -> dict:
        data = parse_qs(self.body().decode("utf-8", "replace"), keep_blank_values=True)
        return {k: x[0] if len(x) == 1 else x for k, x in data.items()}

    def json(self) -> dict:
        try:
            data = json.loads(self.body() or b"{}")
        except ValueError:
            raise HttpError(HTTPStatus.BAD_REQUEST, "JSON non valido") from None
        if not isinstance(data, dict):
            raise HttpError(HTTPStatus.BAD_REQUEST, "JSON non valido")
        return data


class HttpError(Exception):
    def __init__(self, status: HTTPStatus, message: str = ""):
        super().__init__(message or status.phrase)
        self.status = status
        self.message = message or status.phrase


class Redirect(HttpError):
    """Raised by a page that needs a login first."""

    def __init__(self, location: str):
        super().__init__(HTTPStatus.SEE_OTHER)
        self.location = location


class Response:
    def __init__(self, body: str | bytes = "", status: HTTPStatus = HTTPStatus.OK,
                 content_type: str = "text/html; charset=utf-8", headers: list | None = None):
        self.body = body.encode() if isinstance(body, str) else body
        self.status = status
        self.headers = [("Content-Type", content_type), *(headers or [])]


def redirect(location: str, headers: list | None = None) -> Response:
    return Response("", HTTPStatus.SEE_OTHER, headers=[("Location", location), *(headers or [])])


def json_response(data: dict, status: HTTPStatus = HTTPStatus.OK) -> Response:
    return Response(json.dumps(data), status, "application/json")


class Throttle:
    """Failed attempts per address; too many in a row pause that address."""

    def __init__(self):
        self.failures: dict[str, tuple[int, float]] = {}

    def locked(self, ip: str) -> bool:
        n, until = self.failures.get(ip, (0, 0))
        return n >= MAX_FAILURES and time.time() < until

    def fail(self, ip: str) -> None:
        n, until = self.failures.get(ip, (0, 0))
        if n >= MAX_FAILURES and time.time() >= until:
            n = 0
        self.failures[ip] = (n + 1, time.time() + LOCK_SECONDS)

    def ok(self, ip: str) -> None:
        self.failures.pop(ip, None)


class App:
    def __init__(self, store: Store, interval: int = 60, behind_proxy: bool = False, public_url: str = "",
                 ip_header: str = ""):
        self.store = store
        # "CF-Connecting-IP" -> "HTTP_CF_CONNECTING_IP", as WSGI names it.
        self.ip_header = "HTTP_" + ip_header.upper().replace("-", "_") if ip_header else ""
        self.interval = interval
        self.behind_proxy = behind_proxy
        self.public_url = public_url.rstrip("/")
        self.throttle = Throttle()
        self.routes = [
            ("GET", r"/static/(fleet\.css|fleet\.js|favicon\.svg)", self.static),
            ("GET", r"/favicon\.ico", lambda r: self.static(r, "favicon.svg")),
            ("GET", r"/healthz", lambda r: Response("ok\n", content_type="text/plain")),
            ("POST", r"/api/v1/enroll", self.api_enroll),
            ("POST", r"/api/v1/checkin", self.api_checkin),
            ("GET", r"/login", self.login_page),
            ("POST", r"/login", self.login),
            ("POST", r"/logout", self.logout),
            ("GET", r"/", self.devices),
            ("POST", r"/bulk", self.bulk),
            ("GET", r"/devices/(d[0-9a-f]+)", self.device),
            ("POST", r"/devices/(d[0-9a-f]+)", self.edit_device),
            ("POST", r"/devices/(d[0-9a-f]+)/command", self.command),
            ("POST", r"/devices/(d[0-9a-f]+)/cancel", self.cancel),
            ("POST", r"/devices/(d[0-9a-f]+)/delete", self.delete_device),
            ("GET", r"/enroll", self.enroll_page),
            ("POST", r"/enroll", self.create_code),
            ("POST", r"/enroll/(\d+)/revoke", self.revoke_code),
        ]

    # --- WSGI -----------------------------------------------------------
    def __call__(self, environ, start_response):
        req = Request(environ, self.behind_proxy, self.ip_header)
        try:
            resp = self.dispatch(req)
        except Redirect as r:
            resp = redirect(r.location)
        except D1Error:
            exc = HttpError(HTTPStatus.SERVICE_UNAVAILABLE, "archivio dati non raggiungibile, riprovare tra poco")
            resp = (json_response({"error": exc.message}, exc.status) if req.path.startswith("/api/")
                    else Response(v.error_page(exc.status.value, exc.message), exc.status))
        except HttpError as exc:
            if req.path.startswith("/api/"):
                resp = json_response({"error": exc.message}, exc.status)
            else:
                resp = Response(v.error_page(exc.status.value, exc.message), exc.status)
        headers = resp.headers + [
            ("X-Content-Type-Options", "nosniff"),
            ("Referrer-Policy", "no-referrer"),
            ("Cache-Control", "no-store"),
        ]
        if resp.headers[0][1].startswith("text/html"):
            headers += [("Content-Security-Policy", CSP), ("X-Frame-Options", "DENY")]
        if req.https:
            headers.append(("Strict-Transport-Security", "max-age=31536000"))
        start_response(f"{resp.status.value} {resp.status.phrase}", headers)
        return [resp.body]

    def dispatch(self, req: Request) -> Response:
        allowed = False
        for method, pattern, handler in self.routes:
            m = re.fullmatch(pattern, req.path)
            if m:
                allowed = True
                if method == req.method:
                    return handler(req, *m.groups())
                if method == "GET" and req.method == "HEAD":
                    # Same headers as GET (health checks), no body.
                    resp = handler(req, *m.groups())
                    resp.body = b""
                    return resp
        raise HttpError(HTTPStatus.METHOD_NOT_ALLOWED if allowed else HTTPStatus.NOT_FOUND)

    def static(self, req: Request, name: str) -> Response:
        data = resources.files("trota_fleet").joinpath("static", name).read_bytes()
        kind = {"css": "text/css; charset=utf-8", "js": "text/javascript; charset=utf-8",
                "svg": "image/svg+xml"}[name.rsplit(".", 1)[1]]
        return Response(data, content_type=kind)

    # --- device API -----------------------------------------------------
    def api_enroll(self, req: Request) -> Response:
        if self.throttle.locked(req.ip):
            raise HttpError(HTTPStatus.TOO_MANY_REQUESTS, "troppi tentativi, riprovare più tardi")
        data = req.json()
        code, machine = str(data.get("token", "")), str(data.get("machine", ""))
        if not re.fullmatch(r"[0-9a-f]{16,64}", machine):
            raise HttpError(HTTPStatus.BAD_REQUEST, "identificativo del dispositivo non valido")
        got = self.store.enroll(code, str(data.get("hostname", ""))[:200], machine, req.ip)
        if not got:
            self.throttle.fail(req.ip)
            raise HttpError(HTTPStatus.FORBIDDEN, "codice di registrazione non valido, scaduto o già usato")
        self.throttle.ok(req.ip)
        return json_response({"device": got[0], "secret": got[1], "interval": self.interval})

    def api_checkin(self, req: Request) -> Response:
        auth = req.environ.get("HTTP_AUTHORIZATION", "")
        if not auth.startswith("Bearer "):
            raise HttpError(HTTPStatus.UNAUTHORIZED, "dispositivo non riconosciuto")
        data = req.json()
        status = data.get("status") if isinstance(data.get("status"), dict) else {}
        results = data.get("results") if isinstance(data.get("results"), list) else []
        commands = self.store.checkin(auth[7:], status, results[:100], req.ip)
        if commands is None:
            raise HttpError(HTTPStatus.UNAUTHORIZED, "dispositivo non riconosciuto")
        return json_response({"commands": commands, "interval": self.interval})

    # --- sessions -------------------------------------------------------
    def user(self, req: Request):
        s = self.store.session(req.cookie)
        if not s:
            raise Redirect("/login?next=" + quote(req.path))
        return s

    def checked_form(self, req: Request) -> tuple[dict, object]:
        s = self.user(req)
        form = req.form()
        if form.get("csrf") != s["csrf"]:
            raise HttpError(HTTPStatus.FORBIDDEN, "modulo scaduto: ricaricare la pagina")
        return form, s

    def cookie(self, req: Request, value: str, max_age: int) -> tuple:
        secure = "; Secure" if req.https else ""
        return ("Set-Cookie", f"{COOKIE}={value}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Strict{secure}")

    def login_page(self, req: Request, error: str = "") -> Response:
        return Response(v.login_page(error, req.query.get("next", "/")),
                        HTTPStatus.UNAUTHORIZED if error else HTTPStatus.OK)

    def login(self, req: Request) -> Response:
        if self.throttle.locked(req.ip):
            return self.login_page(req, "Troppi tentativi sbagliati: riprovare tra 15 minuti.")
        form = req.form()
        got = self.store.login(str(form.get("name", "")), str(form.get("password", "")))
        if not got:
            self.throttle.fail(req.ip)
            return self.login_page(req, "Nome o password sbagliati.")
        self.throttle.ok(req.ip)
        target = str(form.get("next", "/"))
        if not target.startswith("/") or target.startswith("//"):
            target = "/"
        return redirect(target, [self.cookie(req, got[0], 7 * 86400)])

    def logout(self, req: Request) -> Response:
        self.checked_form(req)
        self.store.logout(req.cookie)
        return redirect("/login", [self.cookie(req, "", 0)])

    # --- pages ----------------------------------------------------------
    def online(self, device) -> bool:
        return bool(device["last_seen"]) and time.time() - device["last_seen"] < 3 * self.interval

    def devices(self, req: Request) -> Response:
        s = self.user(req)
        # No value: every customer; "-": the devices without a customer.
        customer = req.query.get("cliente") or None
        customer = "" if customer == "-" else customer
        rows = self.store.devices(customer, req.query.get("q", "").strip())
        return Response(v.devices_page(s, rows, self.store.customers(), customer, req.query.get("q", ""),
                                       self.online, COMMANDS, req.query.get("msg", "")))

    def device(self, req: Request, device_id: str) -> Response:
        s = self.user(req)
        d = self.store.device(device_id)
        if not d:
            raise HttpError(HTTPStatus.NOT_FOUND, "dispositivo non trovato")
        return Response(v.device_page(s, d, self.store.commands(device_id), self.online(d), COMMANDS,
                                      req.query.get("msg", "")))

    def edit_device(self, req: Request, device_id: str) -> Response:
        form, _ = self.checked_form(req)
        if not self.store.device(device_id):
            raise HttpError(HTTPStatus.NOT_FOUND, "dispositivo non trovato")
        self.store.update_device(device_id, str(form.get("name", "")).strip()[:100],
                                 str(form.get("customer", "")).strip()[:100], str(form.get("notes", ""))[:2000])
        return redirect(f"/devices/{device_id}?msg=" + quote("Modifiche salvate."))

    def _command_args(self, form: dict) -> tuple[str, dict]:
        kind = str(form.get("type", ""))
        if kind not in COMMANDS:
            raise HttpError(HTTPStatus.BAD_REQUEST, "comando sconosciuto")
        args = {}
        if kind == "kiosk-url":
            url = str(form.get("url", "")).strip()
            parts = urlsplit(url)
            if parts.scheme not in ("http", "https") or not parts.hostname or re.search(r"[\s\"'`$\\]", url):
                raise HttpError(HTTPStatus.BAD_REQUEST, "indirizzo della pagina non valido (deve iniziare con https://)")
            args["url"] = url
        return kind, args

    def command(self, req: Request, device_id: str) -> Response:
        form, s = self.checked_form(req)
        if not self.store.device(device_id):
            raise HttpError(HTTPStatus.NOT_FOUND, "dispositivo non trovato")
        kind, args = self._command_args(form)
        self.store.queue(device_id, kind, args, s["name"])
        return redirect(f"/devices/{device_id}?msg=" + quote(f"In coda: {COMMANDS[kind].lower()}."))

    def cancel(self, req: Request, device_id: str) -> Response:
        form, _ = self.checked_form(req)
        try:
            self.store.cancel(device_id, int(form.get("command", 0)))
        except ValueError:
            raise HttpError(HTTPStatus.BAD_REQUEST) from None
        return redirect(f"/devices/{device_id}?msg=" + quote("Comando annullato."))

    def bulk(self, req: Request) -> Response:
        form, s = self.checked_form(req)
        ids = form.get("device", [])
        ids = [ids] if isinstance(ids, str) else ids
        kind, args = self._command_args(form)
        count = 0
        for device_id in ids:
            if re.fullmatch(r"d[0-9a-f]+", device_id) and self.store.device(device_id):
                self.store.queue(device_id, kind, args, s["name"])
                count += 1
        back = str(form.get("back", "/"))
        back = back if back.startswith("/") and not back.startswith("//") else "/"
        sep = "&" if "?" in back else "?"
        return redirect(back + sep + "msg=" + quote(f"{COMMANDS[kind]}: in coda per {count} dispositivi."))

    def delete_device(self, req: Request, device_id: str) -> Response:
        self.checked_form(req)
        self.store.delete_device(device_id)
        return redirect("/?msg=" + quote("Dispositivo rimosso. Per ricollegarlo serve un nuovo codice."))

    def enroll_page(self, req: Request, created: str = "", customer: str = "") -> Response:
        s = self.user(req)
        return Response(v.enroll_page(s, self.store.codes(), self.public_url or req.base, created, customer,
                                      self.store.customers()))

    def create_code(self, req: Request) -> Response:
        form, s = self.checked_form(req)
        try:
            uses = max(1, min(int(form.get("uses") or 1), 10000))
            days = max(1, min(int(form.get("days") or 7), 365))
        except ValueError:
            raise HttpError(HTTPStatus.BAD_REQUEST, "numero non valido") from None
        customer = str(form.get("customer", "")).strip()[:100]
        code = self.store.create_code(customer, str(form.get("note", "")).strip()[:200], uses, days, s["name"])
        return self.enroll_page(req, code, customer)

    def revoke_code(self, req: Request, code_id: str) -> Response:
        self.checked_form(req)
        self.store.revoke_code(int(code_id))
        return redirect("/enroll")
