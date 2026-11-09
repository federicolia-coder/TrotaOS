"""The internal edition: Trota OS as used inside TestardStudios.

Built with ``TROTA_FLAVOR=internal`` (docs/editions.md), it writes
``internal`` to /etc/trota-edition and installs the trota-internal package,
whose /etc/trota-internal.conf holds the company links shown by Trota Welcome
and Trota System Info.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .i18n import _
from .osinfo import parse_os_release

EDITION_FILE = "etc/trota-edition"
CONF_FILE = "etc/trota-internal.conf"

DEFAULT_ADMIN_URL = "https://admin-common-867827762439.europe-west8.run.app/"
DEFAULT_SUPPORT_EMAIL = "info@testardstudios.it"


@dataclass(frozen=True)
class InternalConfig:
    admin_url: str
    support_email: str

    @property
    def support_uri(self) -> str:
        return f"mailto:{self.support_email}"


def is_internal(root: Path = Path("/")) -> bool:
    try:
        return (root / EDITION_FILE).read_text().strip() == "internal"
    except OSError:
        return False


def load(root: Path = Path("/")) -> InternalConfig:
    """Read /etc/trota-internal.conf (KEY=value); missing keys keep the defaults."""
    try:
        data = parse_os_release((root / CONF_FILE).read_text())
    except OSError:
        data = {}
    return InternalConfig(
        admin_url=data.get("ADMIN_URL") or DEFAULT_ADMIN_URL,
        support_email=data.get("SUPPORT_EMAIL") or DEFAULT_SUPPORT_EMAIL,
    )


def support_title() -> str:
    return _("Contact technical support")


def support_subtitle() -> str:
    # TRANSLATORS: an in-joke for TestardStudios staff; keep the capitals.
    return _("NOT FEDERICO, PREFERABLY")


def admin_title() -> str:
    return _("Testard admin panel")


def admin_subtitle() -> str:
    return _("Company administration (staff sign-in required)")
