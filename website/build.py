#!/usr/bin/env python3
"""Assemble the Trota OS website: logos and the desktop screenshot are inlined
(the page is a single file).

Output:
  build/site/index.html     complete HTML document (static hosting, e.g. Render)
  build/site-fragment.html  page without the document skeleton (claude.ai artifact)
"""
import base64
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "website" / "index.src.html"
OUT = ROOT / "build" / "site" / "index.html"
FRAGMENT = ROOT / "build" / "site-fragment.html"
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
    FRAGMENT.write_text(page)
    # Complete document: everything up to the stylesheet goes in <head>.
    head, body = page.split("</style>", 1)
    OUT.write_text(
        '<!doctype html>\n<html lang="it">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        '<link rel="icon" type="image/svg+xml" href="favicon.svg">\n'
        + head + "</style>\n</head>\n<body>\n" + body.strip() + "\n</body>\n</html>\n")
    (OUT.parent / "favicon.svg").write_text(svg("trota-symbol.svg"))
    for f in (OUT, FRAGMENT):
        print(f"{f} ({f.stat().st_size // 1024} KiB)")


if __name__ == "__main__":
    main()
