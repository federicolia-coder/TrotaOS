"""Entry point of trota-welcome.

``--autostart`` is used by the login autostart entry: when the user disabled
"Show this window at login" the program exits immediately, before GTK is even
loaded, so it costs nothing at login.
"""

from __future__ import annotations

import sys

from . import settings


def main(argv=None) -> int:
    argv = list(argv if argv is not None else sys.argv)
    if "--autostart" in argv:
        argv.remove("--autostart")
        if not settings.show_at_login():
            return 0
    from .app import WelcomeApp

    return WelcomeApp().run(argv)
