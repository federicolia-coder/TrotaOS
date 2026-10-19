"""Per-user preferences of Trota Welcome (show at login)."""

from __future__ import annotations

import configparser
import os
from pathlib import Path


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "trota-os" / "welcome.ini"


def show_at_login(path: Path | None = None) -> bool:
    cp = configparser.ConfigParser()
    try:
        cp.read(path or config_path(), encoding="utf-8")
    except (configparser.Error, OSError):
        return True
    return cp.getboolean("welcome", "show_at_login", fallback=True)


def set_show_at_login(value: bool, path: Path | None = None) -> None:
    path = path or config_path()
    cp = configparser.ConfigParser()
    try:
        cp.read(path, encoding="utf-8")
    except configparser.Error:
        cp = configparser.ConfigParser()
    if not cp.has_section("welcome"):
        cp.add_section("welcome")
    cp.set("welcome", "show_at_login", "true" if value else "false")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        cp.write(fh)
    os.replace(tmp, path)
