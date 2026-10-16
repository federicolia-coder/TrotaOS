"""Release information: Trota OS version and the Ubuntu base it is built on.

Trota OS replaces /usr/lib/os-release through a dpkg diversion (package
trota-release); the original Ubuntu file is kept by dpkg as
/usr/lib/os-release.ubuntu and stays up to date with base-files upgrades.

The machine-readable identifiers (ID=ubuntu, VERSION_ID, VERSION_CODENAME)
are kept for compatibility with APT tooling and third-party installers (see
docs/architecture.md, ADR-005); the Trota OS version is in TROTA_VERSION.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path

OS_RELEASE_PATHS = ("/etc/os-release", "/usr/lib/os-release")
UBUNTU_RELEASE_PATHS = ("/usr/lib/os-release.ubuntu", "/etc/os-release", "/usr/lib/os-release")


def parse_os_release(text: str) -> dict[str, str]:
    """Parse the os-release(5) format: KEY=value with shell-like quoting."""
    data: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key.replace("_", "").isalnum():
            continue
        try:
            parts = shlex.split(value, posix=True)
        except ValueError:  # unbalanced quotes: keep the raw value
            parts = [value.strip().strip("\"'")]
        data[key] = " ".join(parts)
    return data


def read_first(paths, root: str = "/") -> dict[str, str]:
    for p in paths:
        path = Path(root) / p.lstrip("/")
        try:
            return parse_os_release(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return {}


@dataclass(frozen=True)
class ReleaseInfo:
    name: str
    version: str
    codename: str
    pretty_name: str
    base_name: str
    base_version: str
    base_codename: str
    is_trota: bool
    home_url: str = ""
    support_url: str = ""
    bug_report_url: str = ""

    @property
    def base_description(self) -> str:
        return f"{self.base_name} {self.base_version}".strip()


def release_info(root: str = "/") -> ReleaseInfo:
    osr = read_first(OS_RELEASE_PATHS, root)
    is_trota = "TROTA_VERSION" in osr
    base = read_first(UBUNTU_RELEASE_PATHS[:1], root) if is_trota else {}
    if not base and not is_trota:
        base = osr if osr.get("ID") == "ubuntu" else {}
    base_name = base.get("NAME") or ("Ubuntu" if osr.get("UBUNTU_CODENAME") else osr.get("ID_LIKE", "").split(" ")[0].title())
    base_version = base.get("VERSION") or osr.get("TROTA_BASE_VERSION", "")
    return ReleaseInfo(
        name=osr.get("NAME", "Linux"),
        version=osr.get("TROTA_VERSION") or osr.get("VERSION_ID", ""),
        # VERSION_CODENAME stays "noble" for compatibility with third-party
        # repositories; the Trota OS codename has its own vendor field.
        codename=osr.get("TROTA_CODENAME") or osr.get("VERSION_CODENAME", ""),
        pretty_name=osr.get("PRETTY_NAME", osr.get("NAME", "Linux")),
        base_name=base_name or "",
        base_version=base_version,
        base_codename=base.get("VERSION_CODENAME") or osr.get("UBUNTU_CODENAME", ""),
        is_trota=is_trota,
        home_url=osr.get("HOME_URL", ""),
        support_url=osr.get("SUPPORT_URL", ""),
        bug_report_url=osr.get("BUG_REPORT_URL", ""),
    )
