"""Trota Fleet panel, end to end: a real panel on a local port, the real
agent from applications/trota-fleet-agent, a browser session with cookies.

    python3 -m pytest -q fleet/tests
"""

import http.cookiejar
import re
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from wsgiref.simple_server import make_server

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "fleet"), str(ROOT / "applications/trota-fleet-agent"), str(Path(__file__).parent)]

from fake_d1 import TOKEN, FakeD1  # noqa: E402
from trota_fleet import db  # noqa: E402
from trota_fleet.backends import D1Backend  # noqa: E402
from trota_fleet.__main__ import QuietHandler, ThreadingServer  # noqa: E402
from trota_fleet.db import Store  # noqa: E402
from trota_fleet.web import App  # noqa: E402
from trota_fleet_agent import commands  # noqa: E402
from trota_fleet_agent.agent import Agent, PanelError, post  # noqa: E402

db.PBKDF2_ITERATIONS = 1000   # fast tests; the real default is in db.py


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


class Browser:
    def __init__(self, base):
        self.base = base
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar), NoRedirect)

    def request(self, path, data=None):
        body = urllib.parse.urlencode(data, doseq=True).encode() if data is not None else None
        try:
            with self.opener.open(self.base + path, body) as r:
                return r.status, r.headers, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read().decode()

    def get(self, path):
        return self.request(path)

    def post(self, path, **data):
        return self.request(path, data)

    def csrf(self, path="/"):
        return re.search(r'name="csrf" value="([^"]+)"', self.get(path)[2]).group(1)


@pytest.fixture(params=["sqlite", "d1"])
def panel(request, tmp_path):
    if request.param == "d1":
        d1 = FakeD1(tmp_path / "d1.db")
        request.addfinalizer(d1.close)
        store = Store(backend=D1Backend("acc", "db", TOKEN, host=f"127.0.0.1:{d1.port}", https=False))
    else:
        store = Store(tmp_path / "fleet.db")
    store.set_user("federico", "una password lunga")
    app = App(store, interval=60)
    httpd = make_server("127.0.0.1", 0, app, ThreadingServer, QuietHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", store, app
    httpd.shutdown()
    httpd.server_close()


def logged_in(base):
    b = Browser(base)
    status, headers, _ = b.post("/login", name="federico", password="una password lunga", next="/")
    assert status == 303 and "HttpOnly" in headers["Set-Cookie"] and "SameSite=Strict" in headers["Set-Cookie"]
    return b


def new_code(b, customer="Bar Centrale", uses=2):
    status, _, html = b.post("/enroll", csrf=b.csrf("/enroll"), customer=customer, note="schermi", uses=uses, days=7)
    assert status == 200
    return re.search(r'<pre class="code" data-copy>(TF-[^<]+)</pre>', html).group(1)


def test_login_required(panel):
    base, _, _ = panel
    b = Browser(base)
    status, headers, _ = b.get("/")
    assert status == 303 and headers["Location"] == "/login?next=/"
    status, headers, html = b.get("/login")
    assert status == 200 and "default-src 'none'" in headers["Content-Security-Policy"]
    assert b.post("/login", name="federico", password="sbagliata")[0] == 401
    assert b.post("/login", name="nessuno", password="x")[0] == 401
    # an open redirect after login is not possible
    status, headers, _ = b.post("/login", name="federico", password="una password lunga", next="//evil.example")
    assert headers["Location"] == "/"


def test_login_throttle(panel):
    base, _, _ = panel
    b = Browser(base)
    for _ in range(10):
        b.post("/login", name="federico", password="sbagliata")
    status, _, html = b.post("/login", name="federico", password="una password lunga")
    assert status == 401 and "Troppi tentativi" in html


def test_forms_need_csrf(panel):
    base, _, _ = panel
    b = logged_in(base)
    assert b.post("/enroll", customer="x", uses=1, days=1)[0] == 403
    assert b.post("/logout")[0] == 403
    assert b.post("/logout", csrf=b.csrf())[0] == 303
    assert b.get("/")[0] == 303


def test_device_lifecycle(panel, tmp_path):
    base, store, _ = panel
    b = logged_in(base)
    assert "Nessun dispositivo ancora" in b.get("/")[2]
    code = new_code(b)
    assert code not in b.get("/enroll")[2]          # shown only once
    assert store.codes()[0]["code"] != code         # stored hashed

    ran = []

    def execute(kind, args):
        ran.append((kind, args))
        return commands.Outcome(True, f"eseguito {kind}")

    report = {"hostname": "<script>alert(1)</script>", "edition": "kiosk", "os": "Trota OS 1.0",
              "updates": 3, "addresses": ["192.168.1.20"], "memory": {"total": 4 << 30, "available": 1 << 30},
              "disk": {"total": 32 << 30, "used": 8 << 30}, "uptime": 90000,
              "kiosk": {"url": "file:///usr/share/trota-kiosk/index.html", "active": True}}
    agent = Agent(tmp_path / "device.json", collect=lambda: report, execute=execute, send=post)
    with pytest.raises(PanelError) as err:
        agent.enroll(base, "TF-sbagliato")
    assert err.value.code == 403
    agent.enroll(base, code)
    device = agent.state.device_id
    assert agent.checkin() == 60

    html = b.get("/")[2]
    assert "In linea" in html and "Bar Centrale" in html and "Kiosk" in html and "192.168.1.20" in html
    assert "1 dispositivi: 1 in linea, 0 non in linea, 1 con aggiornamenti" in html

    page = b.get(f"/devices/{device}")[2]
    assert "Cambia pagina" in page and "3 da installare" in page and "1 g 1 h" in page
    # the device report is untrusted: escaped everywhere
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    csrf = b.csrf(f"/devices/{device}")
    assert b.post(f"/devices/{device}/command", csrf=csrf, type="kiosk-url", url="javascript:alert(1)")[0] == 400
    assert b.post(f"/devices/{device}/command", csrf=csrf, type="shell", url="")[0] == 400
    assert b.post(f"/devices/{device}/command", csrf=csrf, type="kiosk-url",
                  url="https://menu.example/oggi")[0] == 303
    assert "In coda" in b.get(f"/devices/{device}")[2]

    agent.checkin()
    assert ran == [("kiosk-url", {"url": "https://menu.example/oggi"})]
    agent.checkin()                                # delivers the result
    page = b.get(f"/devices/{device}")[2]
    assert "Riuscito" in page and "eseguito kiosk-url" in page

    # bulk command to the selected devices, back to the filtered list
    status, headers, _ = b.post("/bulk", csrf=csrf, device=[device, "dffff"], type="update", url="",
                                back="/?cliente=Bar+Centrale")
    assert status == 303 and headers["Location"].startswith("/?cliente=Bar+Centrale&msg=")
    agent.checkin()
    assert ran[-1][0] == "update"

    # edit, filter by customer
    b.post(f"/devices/{device}", csrf=csrf, name="Menu cassa", customer="Bar Centrale", notes="vicino alla cassa")
    assert "Menu cassa" in b.get("/?cliente=Bar+Centrale")[2]
    assert "Nessun dispositivo corrisponde" in b.get("/?cliente=-")[2]

    # a device enrolling again keeps its id and name
    code2 = new_code(b, uses=1)
    again = Agent(tmp_path / "device2.json", collect=lambda: report, execute=execute, send=post)
    again.enroll(base, code2)
    assert again.state.device_id == device and store.device(device)["name"] == "Menu cassa"
    with pytest.raises(PanelError) as err:
        agent.checkin()                            # the old secret is no longer valid
    assert err.value.code == 401

    # removed from the panel: the agent is told so
    assert b.post(f"/devices/{device}/delete", csrf=csrf)[0] == 303
    with pytest.raises(PanelError) as err:
        again.checkin()
    assert err.value.code == 401


def test_codes_expire_and_revoke(panel, tmp_path):
    base, store, _ = panel
    b = logged_in(base)
    code = new_code(b, uses=1)
    Agent(tmp_path / "a.json", collect=dict, send=post).enroll(base, code)
    with pytest.raises(PanelError):
        Agent(tmp_path / "b.json", collect=dict, send=post).enroll(base, code)   # used up
    code = new_code(b, uses=5)
    cid = store.codes()[0]["id"]
    b.post(f"/enroll/{cid}/revoke", csrf=b.csrf("/enroll"))
    assert "Revocato" in b.get("/enroll")[2]
    with pytest.raises(PanelError):
        Agent(tmp_path / "c.json", collect=dict, send=post).enroll(base, code)


def test_api_rejects_bad_requests(panel):
    base, _, _ = panel
    for auth in ("", "Bearer x", "Bearer d123.wrong"):
        req = urllib.request.Request(base + "/api/v1/checkin", data=b"{}", method="POST",
                                     headers={"Authorization": auth} if auth else {})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 401
    req = urllib.request.Request(base + "/api/v1/enroll", data=b"[1]", method="POST")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req)
    assert e.value.code == 400
    # A body announced as too large is refused before it is read.
    import http.client
    conn = http.client.HTTPConnection(base.split("//")[1])
    conn.putrequest("POST", "/api/v1/enroll")
    conn.putheader("Content-Length", str(600 * 1024))
    conn.endheaders()
    assert conn.getresponse().status == 413
    conn.close()


def test_d1_one_request_per_checkin(tmp_path):
    d1 = FakeD1(tmp_path / "d1.db")
    try:
        store = Store(backend=D1Backend("acc", "db", TOKEN, host=f"127.0.0.1:{d1.port}", https=False))
        code = store.create_code("", "", 1, 1, "t")
        device, secret = store.enroll(code, "h", "a" * 32, "1.2.3.4")
        store.queue(device, "update", {}, "t")
        before = d1.requests
        cmds = store.checkin(f"{device}.{secret}", {"hostname": "h"}, [], "1.2.3.4")
        assert d1.requests - before == 1 and [c["type"] for c in cmds] == ["update"]
        assert store.checkin(f"{device}.wrong", {}, [], "x") is None
        assert store.device(device)["last_seen"] > 0 and isinstance(store.device(device)["last_seen"], int)
    finally:
        d1.close()


def test_d1_errors_are_reported(tmp_path):
    d1 = FakeD1(tmp_path / "d1.db")
    try:
        from trota_fleet.backends import D1Error
        with pytest.raises(D1Error, match="Authentication error"):
            Store(backend=D1Backend("acc", "db", "wrong", host=f"127.0.0.1:{d1.port}", https=False))
        store = Store(backend=D1Backend("acc", "db", TOKEN, host=f"127.0.0.1:{d1.port}", https=False))
        store.set_user("federico", "una password lunga")
        app = App(store)
        store.db.token = "revoked"
        status = []
        body = app({"REQUEST_METHOD": "GET", "PATH_INFO": "/", "HTTP_COOKIE": "trota_fleet=x",
                    "wsgi.input": None}, lambda s, h: status.append(s))
        assert status[0].startswith("503") and "archivio dati" in b"".join(body).decode()
    finally:
        d1.close()
