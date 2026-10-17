#!/usr/bin/env python3
"""Assemble the Trota OS website: logos and the desktop screenshot are inlined
(the page is a single file). Output: build/site/index.html."""
import base64
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "website" / "index.src.html"
OUT = ROOT / "build" / "site" / "index.html"
REPO = "https://github.com/federicolia-coder/TrotaOS"


def svg(name: str) -> str:
    text = (ROOT / "branding" / "logo" / name).read_text()
    text = re.sub(r"<\?xml[^>]*>\s*", "", text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return re.sub(r"<title>.*?</title>", "", text).replace("<svg ", '<svg aria-hidden="true" ', 1).strip()


def main() -> None:
    shot = base64.b64encode((ROOT / "website" / "desktop.webp").read_bytes()).decode()
    page = SRC.read_text()
    for key, value in {
        "{{LOGO_LIGHT}}": svg("trota-logo-light.svg"),
        "{{LOGO_DARK}}": svg("trota-logo-dark.svg"),
        "{{SHOT}}": "data:image/webp;base64," + shot,
        "{{RELEASE_URL}}": REPO + "/releases/tag/v1.0.0",
        "{{DOCS_URL}}": REPO + "/blob/claude/trota-os-linux-distro-410sep/docs/installation.md",
        "{{REPO_URL}}": REPO,
    }.items():
        page = page.replace(key, value)
    left = re.findall(r"\{\{[A-Z_]+\}\}", page)
    assert not left, left
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page)
    print(f"{OUT} ({OUT.stat().st_size // 1024} KiB)")


if __name__ == "__main__":
    main()
