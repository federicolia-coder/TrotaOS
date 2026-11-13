"""AMBER Alerts (trota_common.amber and attiva-allerte-amber.sh), with recorded feed data.

The alert texts below are invented; the structure is that of the IPAWS EAS feed
and of the CAP 1.2 messages it links to.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from trota_common import amber

FEED = """<?xml version='1.0' encoding='UTF-8'?><feed xmlns="http://www.w3.org/2005/Atom">
<title type="text">IPAWS EAS FEED</title><updated>2026-11-12T23:45:16.663Z</updated>
<entry><title type="text">CAE</title><link href="https://ipaws.example/rest/eas/1"/><id>https://ipaws.example/rest/eas/1</id>
<category term="16" label="statefips"/><category term="41" label="statefips"/><category term="CAE" label="event"/></entry>
<entry><title type="text">TOR</title><link href="https://ipaws.example/rest/eas/2"/><id>https://ipaws.example/rest/eas/2</id>
<category term="16" label="statefips"/><category term="TOR" label="event"/></entry>
<entry><title type="text">CAE</title><link href="https://ipaws.example/rest/eas/3"/><id>https://ipaws.example/rest/eas/3</id>
<category term="12" label="statefips"/><category term="CAE" label="event"/></entry>
<entry><title type="text">CAE</title><link href="https://ipaws.example/rest/eas/4"/><id>https://ipaws.example/rest/eas/4</id>
<category term="6" label="statefips"/><category term="CAE" label="event"/></entry>
</feed>"""

CAP = """<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2"><identifier>TEST-1</identifier>
<sender>test@example.org</sender><sent>2026-11-12T02:19:39-07:00</sent><status>Actual</status><msgType>Alert</msgType>
<scope>Public</scope><info><language>en-US</language><category>Other</category><event>Child Abduction Emergency</event>
<urgency>Immediate</urgency><severity>Extreme</severity><certainty>Observed</certainty>
<eventCode><valueName>SAME</valueName><value>CAE</value></eventCode>
<senderName>000000, Example State Communications Center, </senderName><headline>AMBER Alert-Single Child</headline>
<description> This is a test of the amber alert system.
 Example details about the child.</description>
<area><areaDesc>Example State and surrounding areas</areaDesc><geocode><valueName>SAME</valueName><value>016000</value></geocode></area>
<area><areaDesc>Example State and surrounding areas</areaDesc><geocode><valueName>SAME</valueName><value>041045</value></geocode></area>
</info></alert>"""


class FakeFeed:
    def __init__(self, expired=()):
        self.calls, self.expired = [], set(expired)

    def __call__(self, url):
        self.calls.append(url)
        if url == amber.FEED_URL:
            return FEED
        if url in self.expired:
            raise amber.Expired(url)
        return CAP


@pytest.mark.parametrize("zone,state", [
    ("America/Boise", "16"), ("America/Los_Angeles", "06"), ("America/Indiana/Indianapolis", "18"),
    ("America/Anchorage", "02"), ("Pacific/Honolulu", "15"), ("US/Eastern", "36"), ("America/Puerto_Rico", "72"),
])
def test_us_time_zones(zone, state):
    assert state in amber.states_for_timezone(zone)


@pytest.mark.parametrize("zone", ["Europe/Rome", "America/Toronto", "America/Mexico_City", "Etc/UTC", ""])
def test_outside_the_us(zone):
    assert amber.states_for_timezone(zone) == frozenset()


def test_local_timezone_from_link_and_file(tmp_path):
    (tmp_path / "etc").mkdir()
    os.symlink("/usr/share/zoneinfo/America/Boise", tmp_path / "etc/localtime")
    assert amber.local_timezone(tmp_path) == "America/Boise"
    (tmp_path / "etc/localtime").unlink()
    (tmp_path / "etc/timezone").write_text("Europe/Rome\n")
    assert amber.local_timezone(tmp_path) == "Europe/Rome"


def test_configuration(tmp_path):
    (tmp_path / "etc").mkdir()
    os.symlink("/usr/share/zoneinfo/America/Phoenix", tmp_path / "etc/localtime")
    conf = tmp_path / amber.CONF_FILE
    assert amber.followed_states(tmp_path) == {"04"}                       # no config: time zone
    conf.write_text("AMBER_ALERTS=auto\nAMBER_STATES=\n")
    assert amber.followed_states(tmp_path) == {"04"}
    conf.write_text("AMBER_STATES=ID, or 6\n")
    assert amber.followed_states(tmp_path) == {"16", "41", "06"}
    conf.write_text("AMBER_ALERTS=off\nAMBER_STATES=ID\n")
    assert amber.followed_states(tmp_path) == frozenset()


def test_parse_feed_and_cap():
    entries = amber.parse_feed(FEED)
    assert [(e.event, sorted(e.states)) for e in entries][:2] == [("CAE", ["16", "41"]), ("TOR", ["16"])]
    assert entries[3].states == {"06"}                                    # FIPS padded to two digits
    alert = amber.parse_cap(CAP)
    assert alert.identifier == "TEST-1" and alert.events == ("CAE",)
    assert alert.area == "Example State and surrounding areas"            # repeated areas merged
    assert alert.description.startswith("This is a test") and "\n" not in alert.description
    title, body = amber.notification_text(alert)
    assert "Example State" in title and body.startswith("AMBER Alert-Single Child")


def test_alerts_for_followed_states_shown_once(tmp_path):
    seen = amber.SeenStore(tmp_path / "seen.json")
    shown, feed = [], FakeFeed()
    alerts = amber.check({"16"}, seen, shown.append, get=feed, now=1000)
    # Only the CAE entry covering Idaho: not the tornado warning, not Florida.
    assert [a.identifier for a in alerts] == ["TEST-1"] and len(shown) == 1
    assert feed.calls == [amber.FEED_URL, "https://ipaws.example/rest/eas/1"]
    again = amber.check({"16"}, amber.SeenStore(tmp_path / "seen.json"), shown.append, get=FakeFeed(), now=1100)
    assert again == [] and len(shown) == 1


def test_expired_alerts_are_skipped(tmp_path):
    seen = amber.SeenStore(tmp_path / "seen.json")
    feed = FakeFeed(expired={"https://ipaws.example/rest/eas/1"})
    assert amber.check({"16"}, seen, lambda a: None, get=feed, now=1000) == []
    assert "https://ipaws.example/rest/eas/1" in seen


def test_no_network_outside_the_us(tmp_path):
    feed = FakeFeed()
    assert amber.check(frozenset(), amber.SeenStore(tmp_path / "seen.json"), lambda a: None, get=feed) == []
    assert feed.calls == []


def test_seen_entries_expire_after_a_week(tmp_path):
    seen = amber.SeenStore(tmp_path / "seen.json")
    seen.add("old", 0)
    seen.add("new", amber.SeenStore.KEEP_SECONDS)
    seen.save(amber.SeenStore.KEEP_SECONDS + 10)
    reloaded = amber.SeenStore(tmp_path / "seen.json")
    assert "new" in reloaded and "old" not in reloaded



def test_user_config_wins_over_the_system_one(tmp_path):
    (tmp_path / "etc").mkdir()
    os.symlink("/usr/share/zoneinfo/America/Boise", tmp_path / "etc/localtime")
    (tmp_path / amber.CONF_FILE).write_text("AMBER_ALERTS=auto\n")
    user = tmp_path / "user.conf"
    user.write_text("AMBER_STATES=TX\n")
    assert amber.followed_states(tmp_path, user_conf=user) == {"48"}
    user.write_text("AMBER_ALERTS=off\n")
    assert amber.followed_states(tmp_path, user_conf=user) == frozenset()
    assert amber.followed_states(tmp_path, user_conf=tmp_path / "missing.conf") == {"16", "41"}


def test_default_config_follows_the_time_zone(tmp_path):
    root = Path(__file__).resolve().parents[1]
    (tmp_path / "etc").mkdir()
    os.symlink("/usr/share/zoneinfo/America/Boise", tmp_path / "etc/localtime")
    user = tmp_path / "user.conf"
    user.write_text((root / "packaging/files/amber/trota-amber-alert.conf").read_text())
    assert amber.followed_states(tmp_path, user_conf=user) == {"16", "41"}


# --- attiva-allerte-amber.sh (opt-in, downloaded from the website) ----------------
ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "website/root/attiva-allerte-amber.sh"


def test_installer_is_up_to_date():
    p = subprocess.run([sys.executable, str(ROOT / "scripts/build/make-amber-installer.py"), "--check"],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr


def test_installer_shell():
    assert subprocess.run(["bash", "-n", str(INSTALLER)]).returncode == 0
    if shutil.which("shellcheck"):
        p = subprocess.run(["shellcheck", str(INSTALLER)], capture_output=True, text=True)
        assert p.returncode == 0, p.stdout


def test_not_in_the_images():
    control = (ROOT / "packaging/debian/control").read_text()
    assert "trota-amber-alert" not in control and "trota-amber-alert" not in (ROOT / "packaging/debian/rules").read_text()


def _python_with_gi() -> str:
    """The installer checks for python3-gi, as on Trota OS: use a Python that has it."""
    for py in (sys.executable, shutil.which("python3"), "/usr/bin/python3.12"):
        if py and subprocess.run([py, "-c", "import gi; gi.require_version('Gio', '2.0'); from gi.repository import Gio"],
                                 capture_output=True).returncode == 0:
            return py
    pytest.skip("no Python with GObject introspection")


def _fake_env(tmp_path):
    shim = tmp_path / "shim"
    shim.mkdir()
    (shim / "systemctl").write_text('#!/bin/sh\necho "systemctl $*" >> "$HOME/systemctl.log"\n')
    (shim / "id").write_text("#!/bin/sh\necho 1000\n")         # run as a normal user even under root
    for f in shim.iterdir():
        f.chmod(0o755)
    (shim / "python3").symlink_to(_python_with_gi())
    home = tmp_path / "home"
    home.mkdir()
    return {"HOME": str(home), "PATH": f"{shim}:/usr/bin:/bin",
            "PYTHONPATH": str(ROOT / "applications/trota-common")}, home


def test_installer_turns_on_and_off(tmp_path):
    env, home = _fake_env(tmp_path)
    p = subprocess.run(["bash", str(INSTALLER)], capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stderr
    for rel in (".local/bin/trota-amber-alert", ".local/share/trota-amber-alert/trota_amber.py",
                ".config/systemd/user/trota-amber-alert.timer", ".config/trota-amber-alert.conf"):
        assert (home / rel).exists(), rel
    assert "enable --now trota-amber-alert.timer" in (home / "systemctl.log").read_text()
    assert "%h/.local/bin/trota-amber-alert" in (home / ".config/systemd/user/trota-amber-alert.service").read_text()
    # The installed command finds its module and the user configuration.
    (home / ".config/trota-amber-alert.conf").write_text("AMBER_STATES=ID OR\n")
    st = subprocess.run([sys.executable, str(home / ".local/bin/trota-amber-alert"), "--status"],
                        capture_output=True, text=True, env=env)
    assert st.stdout.split() == ["ID", "OR"], st.stderr
    # Turning off removes everything but the configuration.
    p = subprocess.run(["bash", str(INSTALLER), "--disattiva"], capture_output=True, text=True, env=env)
    assert p.returncode == 0
    assert not (home / ".local/bin/trota-amber-alert").exists()
    assert not (home / ".config/systemd/user/trota-amber-alert.timer").exists()
    assert (home / ".config/trota-amber-alert.conf").exists()


def test_installer_refuses_root_and_unknown_options(tmp_path):
    env, _ = _fake_env(tmp_path)
    (Path(env["PATH"].split(":")[0]) / "id").write_text("#!/bin/sh\necho 0\n")
    assert subprocess.run(["bash", str(INSTALLER)], capture_output=True, env=env).returncode != 0
    (Path(env["PATH"].split(":")[0]) / "id").write_text("#!/bin/sh\necho 1000\n")
    assert subprocess.run(["bash", str(INSTALLER), "--boh"], capture_output=True, env=env).returncode != 0
