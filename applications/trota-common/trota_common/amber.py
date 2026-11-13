"""AMBER Alerts as desktop notifications, when the computer is in the United States.

AMBER Alerts are broadcast in the US as "Child Abduction Emergency" (event
code CAE) through FEMA's Integrated Public Alert & Warning System. Its public
EAS feed (FEED_URL, Atom) lists the alerts currently on air with the FIPS codes
of the states they cover; each entry links to the full CAP 1.2 message.

Whether the computer is in the US, and in which states, is worked out from the
system time zone only (GNOME sets it from the location when "Automatic time
zone" is on): no location is looked up or sent. Outside the US nothing is
downloaded.

The alerts are off unless the user turns them on with the script
attiva-allerte-amber.sh from the website (docs/amber-alert.md), which installs
the checker and its user timer in the home folder. ~/.config/trota-amber-alert.conf
(or /etc/trota-amber-alert.conf for every user) can stop them (AMBER_ALERTS=off)
or name the states to follow (AMBER_STATES=ID,OR or FIPS codes).
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from .i18n import _
from .osinfo import parse_os_release

FEED_URL = "https://apps.fema.gov/IPAWSOPEN_EAS_SERVICE/rest/feed"
EVENT_CODE = "CAE"            # SAME code of the Child Abduction Emergency (AMBER Alert)
USER_AGENT = "Trota-OS-amber-alert/1.0"
ATOM = "{http://www.w3.org/2005/Atom}"
CAP = "{urn:oasis:names:tc:emergency:cap:1.2}"
CONF_FILE = "etc/trota-amber-alert.conf"

# State FIPS codes by USPS abbreviation (50 states, DC and Puerto Rico).
STATE_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08", "CT": "09", "DE": "10",
    "DC": "11", "FL": "12", "GA": "13", "HI": "15", "ID": "16", "IL": "17", "IN": "18", "IA": "19",
    "KS": "20", "KY": "21", "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27",
    "MS": "28", "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33", "NJ": "34", "NM": "35",
    "NY": "36", "NC": "37", "ND": "38", "OH": "39", "OK": "40", "OR": "41", "PA": "42", "RI": "44",
    "SC": "45", "SD": "46", "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53",
    "WV": "54", "WI": "55", "WY": "56", "PR": "72",
}


def _fips(*states: str) -> frozenset[str]:
    return frozenset(STATE_FIPS[s] for s in states)


# The states a US time zone covers, at least in part. A zone shared by many
# states (New York, Chicago, Denver, Los Angeles) follows all of them.
ZONE_STATES = {
    "America/New_York": _fips("CT", "DE", "DC", "FL", "GA", "IN", "KY", "ME", "MD", "MA", "MI", "NH", "NJ",
                              "NY", "NC", "OH", "PA", "RI", "SC", "TN", "VT", "VA", "WV"),
    "America/Detroit": _fips("MI"),
    "America/Chicago": _fips("AL", "AR", "FL", "IL", "IN", "IA", "KS", "KY", "LA", "MI", "MN", "MS", "MO",
                             "NE", "ND", "OK", "SD", "TN", "TX", "WI"),
    "America/Menominee": _fips("MI"),
    "America/Denver": _fips("CO", "ID", "KS", "MT", "NE", "NM", "ND", "OR", "SD", "TX", "UT", "WY"),
    "America/Boise": _fips("ID", "OR"),
    "America/Phoenix": _fips("AZ"),
    "America/Los_Angeles": _fips("CA", "ID", "NV", "OR", "WA"),
    "Pacific/Honolulu": _fips("HI"),
    "America/Puerto_Rico": _fips("PR"),
}
ZONE_PREFIX_STATES = {
    "America/Indiana/": _fips("IN"),
    "America/Kentucky/": _fips("KY"),
    "America/North_Dakota/": _fips("ND"),
}
ALASKA_ZONES = ("America/Anchorage", "America/Juneau", "America/Sitka", "America/Yakutat", "America/Nome",
                "America/Metlakatla", "America/Adak")
LEGACY_ZONES = {
    "US/Eastern": "America/New_York", "US/Central": "America/Chicago", "US/Mountain": "America/Denver",
    "US/Pacific": "America/Los_Angeles", "US/Arizona": "America/Phoenix", "US/Hawaii": "Pacific/Honolulu",
    "US/Alaska": "America/Anchorage", "US/Michigan": "America/Detroit", "US/East-Indiana": "America/Indiana/Indianapolis",
}


def states_for_timezone(zone: str) -> frozenset[str]:
    """FIPS codes of the states in a time zone; empty outside the United States."""
    zone = LEGACY_ZONES.get(zone, zone)
    if zone in ZONE_STATES:
        return ZONE_STATES[zone]
    if zone in ALASKA_ZONES:
        return _fips("AK")
    for prefix, states in ZONE_PREFIX_STATES.items():
        if zone.startswith(prefix):
            return states
    return frozenset()


def local_timezone(root: Path = Path("/")) -> str:
    """The system time zone, from the /etc/localtime link (or /etc/timezone)."""
    link = root / "etc/localtime"
    try:
        target = os.readlink(link)
        marker = "zoneinfo/"
        if marker in target:
            return target.split(marker, 1)[1]
    except OSError:
        pass
    try:
        return (root / "etc/timezone").read_text().strip()
    except OSError:
        return ""


def parse_states(value: str) -> frozenset[str]:
    """AMBER_STATES: USPS abbreviations or FIPS codes, comma or space separated."""
    out = set()
    for item in value.replace(",", " ").split():
        item = item.strip().upper()
        if item in STATE_FIPS:
            out.add(STATE_FIPS[item])
        elif item.isdigit() and len(item) <= 2:
            out.add(item.zfill(2))
    return frozenset(out)


def user_config_file() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "trota-amber-alert.conf"


def followed_states(root: Path = Path("/"), user_conf: Path | None = None) -> frozenset[str]:
    """States whose AMBER Alerts to show; empty = alerts off or not in the US.

    The user's ~/.config/trota-amber-alert.conf wins over /etc/trota-amber-alert.conf.
    """
    conf: dict[str, str] = {}
    for path in (root / CONF_FILE, user_conf):
        try:
            conf.update(parse_os_release(path.read_text()) if path else {})
        except OSError:
            pass
    if conf.get("AMBER_ALERTS", "auto").lower() in ("off", "no", "false", "0"):
        return frozenset()
    if conf.get("AMBER_STATES"):
        return parse_states(conf["AMBER_STATES"])
    return states_for_timezone(local_timezone(root))


@dataclass(frozen=True)
class FeedEntry:
    url: str
    event: str
    states: frozenset[str]


def parse_feed(text: str) -> list[FeedEntry]:
    entries = []
    for e in ET.fromstring(text).iter(f"{ATOM}entry"):
        link = e.find(f"{ATOM}link")
        url = link.get("href", "") if link is not None else (e.findtext(f"{ATOM}id") or "")
        event = next((c.get("term", "") for c in e.iter(f"{ATOM}category") if c.get("label") == "event"),
                     e.findtext(f"{ATOM}title") or "")
        states = frozenset(c.get("term", "").zfill(2) for c in e.iter(f"{ATOM}category")
                           if c.get("label") == "statefips")
        if url:
            entries.append(FeedEntry(url, event.strip(), states))
    return entries


@dataclass(frozen=True)
class Alert:
    identifier: str
    headline: str
    description: str
    area: str
    sender: str
    instruction: str = ""
    events: tuple[str, ...] = field(default_factory=tuple)


def parse_cap(text: str) -> Alert:
    root = ET.fromstring(text)
    info = root.find(f"{CAP}info")
    if info is None:
        raise ValueError("CAP message without <info>")

    def get(el, tag):
        return " ".join((el.findtext(f"{CAP}{tag}") or "").split())

    areas = []
    for a in info.iter(f"{CAP}area"):
        desc = get(a, "areaDesc")
        if desc and desc not in areas:
            areas.append(desc)
    events = tuple(get(c, "value") for c in info.iter(f"{CAP}eventCode"))
    return Alert(
        identifier=get(root, "identifier"),
        headline=get(info, "headline") or get(info, "event"),
        description=get(info, "description"),
        area=", ".join(areas),
        sender=get(info, "senderName").strip(" ,"),
        instruction=get(info, "instruction"),
        events=events,
    )


class Expired(Exception):
    """The alert is no longer on air (the feed keeps it listed for a while)."""


def fetch(url: str, timeout: float = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/xml"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 404, 410):    # IPAWS answers 403 "has already expired"
            raise Expired(url) from exc
        raise


class SeenStore:
    """Feed entries already handled, so each alert is shown once. Kept for a week."""

    KEEP_SECONDS = 7 * 24 * 3600

    def __init__(self, path: Path):
        self.path = path
        try:
            self.seen: dict[str, float] = json.loads(path.read_text())
        except (OSError, ValueError):
            self.seen = {}

    def __contains__(self, key: str) -> bool:
        return key in self.seen

    def add(self, key: str, now: float) -> None:
        self.seen[key] = now

    def save(self, now: float) -> None:
        self.seen = {k: t for k, t in self.seen.items() if now - t < self.KEEP_SECONDS}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.seen))
        tmp.replace(self.path)


def notification_text(alert: Alert) -> tuple[str, str]:
    title = _("AMBER Alert") + (f": {alert.area}" if alert.area else "")
    body = alert.headline
    if alert.description:
        desc = alert.description if len(alert.description) <= 400 else alert.description[:397].rstrip() + "…"
        body = f"{body}\n{desc}"
    if alert.instruction:
        body = f"{body}\n{alert.instruction}"
    return title, body


def check(states: Iterable[str], seen: SeenStore, notify: Callable[[Alert], None],
          get: Callable[[str], str] = fetch, now: float | None = None) -> list[Alert]:
    """Show the AMBER Alerts on air in *states* that were not shown yet."""
    states = frozenset(states)
    if not states:
        return []        # not in the US (or turned off): no network access at all
    now = time.time() if now is None else now
    shown = []
    for entry in parse_feed(get(FEED_URL)):
        if entry.event != EVENT_CODE or not (entry.states & states) or entry.url in seen:
            continue
        try:
            alert = parse_cap(get(entry.url))
        except Expired:
            seen.add(entry.url, now)
            continue
        if alert.events and EVENT_CODE not in alert.events:
            seen.add(entry.url, now)
            continue
        notify(alert)
        seen.add(entry.url, now)
        shown.append(alert)
    seen.save(now)
    return shown
