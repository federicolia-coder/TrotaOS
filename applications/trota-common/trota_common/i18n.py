"""gettext set-up shared by all Trota OS applications."""

import gettext
import locale
import os

DOMAIN = "trota-os"
LOCALEDIR = os.environ.get("TROTA_LOCALEDIR", "/usr/share/locale")

try:
    locale.setlocale(locale.LC_ALL, "")
except locale.Error:  # unsupported locale in the environment: keep "C"
    pass

_translation = gettext.translation(DOMAIN, LOCALEDIR, fallback=True)
_ = _translation.gettext
ngettext = _translation.ngettext


def bind_gtk_domain():
    """Make GtkBuilder / libadwaita widgets use our message catalogue too."""
    try:
        locale.bindtextdomain(DOMAIN, LOCALEDIR)
        locale.textdomain(DOMAIN)
    except AttributeError:  # not available on every platform
        pass
    gettext.bindtextdomain(DOMAIN, LOCALEDIR)
    gettext.textdomain(DOMAIN)
