"""Business details for the footer and the legal pages of the panel.

Read from legal/company.json at the root of the Trota OS repository (the
same file the website uses), or from the file in TROTA_FLEET_COMPANY.
Fields left null are not shown.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT = {
    "name": "TestardStudios",
    "legal_name": None,
    "address": None,
    "vat": None,
    "status": None,
    "email": "info@testardstudios.it",
    "sales_email": "sales@testardstudios.it",
    "website": "https://trotaos.onrender.com",
    "updated": "18 ottobre 2026",
}


def company() -> dict:
    path = Path(os.environ.get("TROTA_FLEET_COMPANY") or Path(__file__).resolve().parents[2] / "legal" / "company.json")
    data = dict(DEFAULT)
    try:
        data.update({k: v for k, v in json.loads(path.read_text()).items() if not k.startswith("_")})
    except (OSError, ValueError):
        pass
    parts = [data["legal_name"] or data["name"], data["address"],
             f"P.IVA {data['vat']}" if data["vat"] else data.get("status")]
    data["ident"] = " · ".join(p for p in parts if p)
    return data
