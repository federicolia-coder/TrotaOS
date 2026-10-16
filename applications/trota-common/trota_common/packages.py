"""Read-only access to the APT package catalogue for Trota Package Helper.

APT remains the only package system: this module searches and describes
packages with ``apt-cache`` / ``dpkg-query`` and produces installation
instructions.  It never installs, removes or configures anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .i18n import _
from .runner import Runner, run

# Debian policy 5.6.1: lowercase letters, digits, + - . ; at least 2 chars,
# starting with an alphanumeric character.
PACKAGE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9+.\-]+$")
MAX_QUERY_LENGTH = 64
DEFAULT_LIMIT = 200


class PackageError(Exception):
    """Raised for invalid input or when APT cannot be queried."""


@dataclass(frozen=True)
class SearchResult:
    name: str
    summary: str


@dataclass
class PackageInfo:
    name: str
    version: str = ""
    summary: str = ""
    description: str = ""
    section: str = ""
    installed_size_kib: int | None = None
    download_size: int | None = None
    homepage: str = ""
    maintainer: str = ""
    origin_component: str = ""
    installed_version: str | None = None
    depends: list[str] = field(default_factory=list)

    @property
    def installed(self) -> bool:
        return self.installed_version is not None

    @property
    def component(self) -> str:
        """main / restricted / universe / multiverse (from the Section)."""
        return self.section.split("/")[0] if "/" in self.section else "main"

    @property
    def support_note(self) -> str:
        return {
            "main": _("Supported by Canonical with security updates."),
            "restricted": _("Proprietary driver supported by Canonical."),
            "universe": _("Maintained by the Ubuntu community."),
            "multiverse": _("Not free software; may have legal restrictions."),
        }.get(self.component, "")


def is_valid_package_name(name: str) -> bool:
    return bool(PACKAGE_NAME_RE.match(name or ""))


def normalize_query(query: str) -> str:
    query = (query or "").strip()
    if not query:
        raise PackageError("empty search")
    if len(query) > MAX_QUERY_LENGTH:
        raise PackageError("search text too long")
    if any(ord(c) < 32 for c in query):
        raise PackageError("invalid characters in search")
    return query


def search(query: str, runner: Runner = run, limit: int = DEFAULT_LIMIT, names_only: bool = False) -> list[SearchResult]:
    """Search the APT catalogue. Each word must match (AND), case-insensitive.

    Words are passed to apt-cache as escaped regular expressions so user input
    is always matched literally.
    """
    words = normalize_query(query).split()
    args = ["apt-cache", "search"]
    if names_only:
        args.append("--names-only")
    args += [re.escape(w) for w in words]
    res = runner(args, 120)
    if res.missing:
        raise PackageError(_("apt-cache is not installed"))
    if res.timed_out:
        raise PackageError(_("The search took too long. Try a more specific search."))
    if not res.ok:
        raise PackageError(res.stderr.strip() or _("apt-cache search failed"))
    results = []
    for line in res.stdout.splitlines():
        name, sep, summary = line.partition(" - ")
        if sep and is_valid_package_name(name.strip()):
            results.append(SearchResult(name.strip(), summary.strip()))
    lowered = [w.lower() for w in words]

    def rank(r: SearchResult):
        n = r.name.lower()
        return (n != lowered[0], not n.startswith(lowered[0]), not all(w in n for w in lowered), len(n), n)

    results.sort(key=rank)
    return results[:limit]


def parse_control(text: str) -> dict[str, str]:
    """Parse the first RFC 822 style stanza of apt-cache show output."""
    fields: dict[str, str] = {}
    key = None
    for line in text.splitlines():
        if not line.strip():
            if fields:
                break
            continue
        if line[0] in " \t" and key:
            fields[key] += "\n" + line[1:]
        else:
            k, _sep, v = line.partition(":")
            key = k.strip()
            fields[key] = v.strip()
    return fields


def _description(fields: dict[str, str]) -> tuple[str, str]:
    # The long text lives in Translation-en (field "Description-en") when the
    # translation indexes are downloaded, which is the case on Ubuntu desktops.
    desc = fields.get("Description-en") or fields.get("Description", "")
    summary, _sep, body = desc.partition("\n")
    paragraphs = []
    for line in body.splitlines():
        line = line.strip()
        paragraphs.append("" if line == "." else line)
    long = "\n".join(paragraphs).strip()
    long = re.sub(r"(?<!\n)\n(?!\n)", " ", long)  # unwrap lines inside paragraphs
    return summary.strip(), long


def info(name: str, runner: Runner = run) -> PackageInfo:
    if not is_valid_package_name(name):
        raise PackageError(f"invalid package name: {name!r}")
    res = runner(["apt-cache", "show", "--no-all-versions", name], 30)
    if res.missing:
        raise PackageError("apt-cache is not installed")
    if not res.ok or not res.stdout.strip():
        raise PackageError(f"package {name} was not found")
    f = parse_control(res.stdout)
    summary, long = _description(f)
    pkg = PackageInfo(
        name=f.get("Package", name),
        version=f.get("Version", ""),
        summary=summary,
        description=long,
        section=f.get("Section", ""),
        homepage=f.get("Homepage", ""),
        maintainer=f.get("Maintainer", ""),
        depends=[d.strip() for d in f.get("Depends", "").split(",") if d.strip()],
    )
    if f.get("Installed-Size", "").isdigit():
        pkg.installed_size_kib = int(f["Installed-Size"])
    if f.get("Size", "").isdigit():
        pkg.download_size = int(f["Size"])
    pkg.installed_version = installed_version(name, runner)
    return pkg


def installed_version(name: str, runner: Runner = run) -> str | None:
    if not is_valid_package_name(name):
        return None
    res = runner(["dpkg-query", "-W", "-f=${db:Status-Abbrev}\t${Version}", name], 10)
    if not res.ok:
        return None
    status, _sep, version = res.stdout.partition("\t")
    return version.strip() if status.startswith("ii") else None


def install_command(name: str) -> str:
    if not is_valid_package_name(name):
        raise PackageError(f"invalid package name: {name!r}")
    return f"sudo apt install {name}"


def remove_command(name: str) -> str:
    if not is_valid_package_name(name):
        raise PackageError(f"invalid package name: {name!r}")
    return f"sudo apt remove {name}"


def lists_available(runner: Runner = run) -> bool:
    """False on a fresh system whose package lists were never downloaded."""
    res = runner(["apt-cache", "stats"], 15)
    if not res.ok:
        return False
    m = re.search(r"Total package names:\s*(\d+)", res.stdout)
    return bool(m and int(m.group(1)) > 1000)
