"""Trota Fleet agent: configuration, commands and the check-in loop, with a
fake panel (no network, no root)."""

import json

import pytest

from trota_fleet_agent import commands, status
from trota_fleet_agent.agent import Agent, PanelError
from trota_fleet_agent.config import Settings, State, check_url, read_conf, set_conf_value


def test_conf_read_and_set(tmp_path):
    conf = tmp_path / "trota-kiosk.conf"
    conf.write_text("# page\nTROTA_KIOSK_URL=\"file:///a.html\"\n\nTROTA_KIOSK_VT_SWITCH=no\n")
    assert read_conf(conf) == {"TROTA_KIOSK_URL": "file:///a.html", "TROTA_KIOSK_VT_SWITCH": "no"}
    set_conf_value(conf, "TROTA_KIOSK_URL", "https://menu.example/")
    text = conf.read_text()
    assert text.startswith("# page\nTROTA_KIOSK_URL=https://menu.example/\n")
    assert "TROTA_KIOSK_VT_SWITCH=no" in text
    set_conf_value(conf, "NEW", "1")
    assert read_conf(conf)["NEW"] == "1"
    with pytest.raises(ValueError):
        set_conf_value(conf, "X", "a\nTROTA_KIOSK_VT_SWITCH=yes")


def test_settings_defaults(tmp_path):
    shipped = (__import__("pathlib").Path(__file__).parent.parent / "packaging/files/fleet/trota-fleet.conf")
    s = Settings.load(shipped)
    assert s.url == "" and s.token == "" and s.insecure is False


def test_check_url():
    assert check_url("https://fleet.example.com/ ") == "https://fleet.example.com"
    assert check_url("http://127.0.0.1:8080") == "http://127.0.0.1:8080"
    assert check_url("http://10.0.0.5", insecure=True) == "http://10.0.0.5"
    for bad in ("http://10.0.0.5", "ftp://x", "fleet.example.com", "https://"):
        with pytest.raises(ValueError):
            check_url(bad)


def test_state_is_private(tmp_path):
    path = tmp_path / "state" / "device.json"
    State(device_id="d1", secret="s", url="https://x").save(path)
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert State.load(path).enrolled
    assert not State.load(tmp_path / "missing.json").enrolled


def test_kiosk_url_command(tmp_path):
    conf = tmp_path / "trota-kiosk.conf"
    conf.write_text("TROTA_KIOSK_URL=file:///usr/share/trota-kiosk/index.html\nTROTA_KIOSK_VT_SWITCH=no\n")
    calls = []

    def run(args, timeout=60):
        calls.append(args)
        return 0, ""

    out = commands.kiosk_url({"url": "https://menu.example/oggi"}, run=run, conf=conf)
    assert out.ok and read_conf(conf)["TROTA_KIOSK_URL"] == "https://menu.example/oggi"
    assert calls == [["systemctl", "restart", "trota-kiosk.service"]]
    for bad in ("javascript:alert(1)", "https://x/a b", "https://x/$(reboot)", "https://x/\"", ""):
        assert not commands.kiosk_url({"url": bad}, run=run, conf=conf).ok, bad
    assert not commands.kiosk_url({"url": "https://x"}, run=run, conf=tmp_path / "none.conf").ok
    assert len(calls) == 1


def test_only_known_commands():
    out = commands.execute("shell", {"cmd": "rm -rf /"})
    assert not out.ok and "sconosciuto" in out.output
    assert set(commands.HANDLERS) == {"kiosk-url", "kiosk-restart", "update", "reboot"}
    boom = commands.execute("x", {}, handlers={"x": lambda a: 1 / 0})
    assert not boom.ok


def test_update_and_reboot_commands():
    calls = []

    def run(args, timeout=60):
        calls.append(args)
        return 0, "ok"

    assert commands.update({}, run=run).ok
    assert calls[0][-2:] == ["apt-get", "update"] and calls[1][-1] == "full-upgrade"
    assert "DEBIAN_FRONTEND=noninteractive" in calls[1]
    out = commands.reboot({}, run=run)
    assert out.ok and len(calls) == 2   # nothing until the result is delivered
    out.after()
    assert calls[-1] == ["systemctl", "reboot"]


class FakePanel:
    def __init__(self):
        self.queue = [{"id": 1, "type": "kiosk-restart", "args": {}}, {"id": 2, "type": "reboot", "args": {}}]
        self.requests = []

    def __call__(self, url, payload, auth="", timeout=30):
        self.requests.append((url.rsplit("/", 1)[1], payload, auth))
        if url.endswith("/enroll"):
            if payload["token"] != "good":
                raise PanelError("codice non valido", 403)
            return {"device": "dabc", "secret": "s3cret"}
        done = {r["id"] for r in payload["results"]}
        self.queue = [c for c in self.queue if c["id"] not in done]
        return {"commands": list(self.queue), "interval": 30}


def test_enroll_and_checkin(tmp_path):
    panel, ran, rebooted = FakePanel(), [], []

    def execute(kind, args):
        ran.append(kind)
        if kind == "reboot":
            return commands.Outcome(True, "riavvio", after=lambda: rebooted.append(True))
        return commands.Outcome(True, "fatto")

    state = tmp_path / "device.json"
    agent = Agent(state, collect=lambda: {"hostname": "k1"}, execute=execute, send=panel)
    with pytest.raises(PanelError):
        agent.enroll("https://fleet.example", "bad")
    agent.enroll("https://fleet.example/", "good")
    assert agent.state.url == "https://fleet.example" and json.loads(state.read_text())["secret"] == "s3cret"
    assert len(panel.requests[-1][1]["machine"]) == 32

    assert agent.checkin() == 30
    assert ran == ["kiosk-restart", "reboot"] and rebooted == [True]
    # the results went out before the reboot, with the device credentials
    last = panel.requests[-1]
    assert last[2] == "dabc.s3cret" and [r["id"] for r in last[1]["results"]] == [1, 2]
    assert panel.queue == [] and agent.state.results == []

    # a command already run is never repeated, even if the panel sends it again
    panel.queue = [{"id": 1, "type": "kiosk-restart", "args": {}}]
    agent.checkin()
    assert ran == ["kiosk-restart", "reboot"]


def test_results_survive_an_unreachable_panel(tmp_path):
    panel = FakePanel()
    panel.queue = [{"id": 7, "type": "update", "args": {}}]
    state = tmp_path / "device.json"
    agent = Agent(state, collect=dict, execute=lambda k, a: commands.Outcome(True, "ok"), send=panel)
    agent.enroll("https://fleet.example", "good")
    agent.checkin()
    assert [r["id"] for r in State.load(state).results] == [7]

    def down(*a, **k):
        raise PanelError("rete assente")
    agent.send = down
    with pytest.raises(PanelError):
        agent.checkin()
    agent2 = Agent(state, collect=dict, execute=lambda k, a: commands.Outcome(True, "ok"), send=panel)
    agent2.checkin()
    assert panel.requests[-1][1]["results"][0]["id"] == 7


def test_run_forever_stops_when_removed(tmp_path):
    def gone(*a, **k):
        raise PanelError("dispositivo non riconosciuto", 401)
    agent = Agent(tmp_path / "d.json", collect=dict, send=gone)
    agent.state = State("d1", "s", "https://x")
    assert agent.run_forever(sleep=lambda s: None) == 3


def test_status_report(tmp_path):
    (tmp_path / "proc").mkdir()
    (tmp_path / "proc/uptime").write_text("3725.4 100.0\n")
    (tmp_path / "proc/loadavg").write_text("0.42 0.3 0.2 1/100 1\n")
    (tmp_path / "proc/meminfo").write_text("MemTotal: 2048 kB\nMemFree: 10 kB\nMemAvailable: 1024 kB\n")
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc/os-release").write_text('PRETTY_NAME="Trota OS 1.0"\n')
    (tmp_path / "etc/trota-edition").write_text("cloud\n")
    assert status.uptime(tmp_path) == 3725 and status.load(tmp_path) == 0.42
    assert status.memory(tmp_path) == {"total": 2097152, "available": 1048576}
    assert status.os_name(tmp_path) == "Trota OS 1.0" and status.edition(tmp_path) == "cloud"
    assert status.kiosk(tmp_path) is None
    (tmp_path / "etc/trota-edition").unlink()
    (tmp_path / "usr/lib/trota-kiosk").mkdir(parents=True)
    assert status.edition(tmp_path) == "kiosk"


def test_packaging():
    from pathlib import Path
    root = Path(__file__).parent.parent
    control = (root / "packaging/debian/control").read_text()
    pkg = control.split("Package: trota-fleet-agent\n", 1)[1].split("\n\n", 1)[0]
    assert "python3" in pkg and "gtk" not in pkg.lower()   # headless: no desktop libraries
    rules = (root / "packaging/debian/rules").read_text()
    assert "trota-fleet-agent" in rules.split("APPS :=", 1)[1].split("\n", 1)[0]
    assert "--name=trota-fleet-agent --no-start" in rules
    unit = (root / "packaging/debian/trota-fleet-agent.trota-fleet-agent.service").read_text()
    assert "ExecCondition=/usr/bin/trota-fleet-agent configured" in unit
    assert "RestartPreventExitStatus=2 3" in unit
    image = (root / "scripts/build/build-image.sh").read_text()
    assert "trota-fleet-agent_*.deb" in image and "/etc/trota-edition" in image
