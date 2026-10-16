"""Shared code for the Trota OS applications (Welcome, System Info,
Diagnostics, Package Helper).

The modules in this package are split in two layers:

* back-end modules (``runner``, ``osinfo``, ``sysinfo``, ``diagnostics``,
  ``packages``) depend only on the Python standard library and read
  everything locally.  They are unit tested without a display.
* front-end helpers (``desktop``, ``ui``) need PyGObject, GTK 4 and libadwaita.

Copyright (C) 2026 TestardStudios.  SPDX-License-Identifier: GPL-3.0-or-later
"""

__version__ = "1.0.0"

PROJECT_URL = "https://github.com/federicolia-coder/TrotaOS"
ISSUES_URL = PROJECT_URL + "/issues"
DOCS_URL = PROJECT_URL + "/tree/main/docs"
SECURITY_URL = PROJECT_URL + "/blob/main/SECURITY.md"
PUBLISHER = "TestardStudios"
PRODUCT = "Trota OS"
