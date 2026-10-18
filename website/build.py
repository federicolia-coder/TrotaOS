#!/usr/bin/env python3
"""Assemble the Trota OS website: logos and the desktop screenshot are inlined
(the page is a single file).

Output:
  build/site/index.html     complete HTML document (static hosting, e.g. Render)
  build/site/privacy.html, cookie.html, note-legali.html   legal pages
  build/site/menu-digitali.html   landing page for bars and restaurants
  build/site/fonts/         IBM Plex, served by the site itself
  build/site-fragment.html  page without the document skeleton (claude.ai artifact)

Business details (name, address, VAT number) come from legal/company.json.
"""
import base64
import html
import json
import re
import shutil
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "website" / "index.src.html"
OUT = ROOT / "build" / "site" / "index.html"
FRAGMENT = ROOT / "build" / "site-fragment.html"
REPO = "https://github.com/federicolia-coder/TrotaOS"
# Public downloads: Cloudflare R2 bucket "trotaos-downloads" (.github/workflows/mirror-r2.yml).
DOWNLOADS = "https://pub-d6b49f9479c04789b2d7198ad306e374.r2.dev/1.0"


def svg(name: str) -> str:
    text = (ROOT / "branding" / "logo" / name).read_text()
    text = re.sub(r"<\?xml[^>]*>\s*", "", text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return re.sub(r"<title>.*?</title>", "", text).replace("<svg ", '<svg aria-hidden="true" ', 1).strip()


def company() -> dict:
    c = json.loads((ROOT / "legal" / "company.json").read_text())
    # Fields left null are not shown: the site never displays a placeholder.
    ident = [c["legal_name"] or c["name"], c["address"], f"P.IVA {c['vat']}" if c["vat"] else c.get("status")]
    c["ident"] = html.escape(" · ".join(x for x in ident if x))
    return c


def legal_pages(c: dict, logos: dict) -> None:
    template = (ROOT / "website" / "legal.src.html").read_text()
    for src in sorted((ROOT / "website" / "legal").glob("*.html")):
        text = src.read_text()
        title = re.match(r"<!-- title: (.*?) -->\n", text)
        assert title, f"{src}: no title comment"
        page = template.replace("{{CONTENT}}", text[title.end():].strip())
        for key, value in {
            "{{TITLE}}": title.group(1), "{{UPDATED}}": c["updated"],
            "{{COMPANY_LINE}}": c["ident"], "{{COMPANY_IDENT}}": c["ident"],
            "{{COMPANY_NAME}}": html.escape(c["name"]), "{{EMAIL}}": c["email"], "{{SALES_EMAIL}}": c["sales_email"],
            "{{REPO_URL}}": REPO, **logos,
        }.items():
            page = page.replace(key, value)
        left = re.findall(r"\{\{[A-Z_]+\}\}", page)
        assert not left, (src, left)
        (OUT.parent / src.name).write_text(page)


def menu_page(c: dict, logos: dict) -> None:
    """Landing page for bars and restaurants (digital menu boards)."""
    body = ("Ciao, vorrei un preventivo per il menu digitale.\n\n"
            "Nome del locale:\nZona:\nQuanti schermi:\nCosa vorrei mostrare:\n")
    mailto = f"mailto:{c['sales_email']}?subject={quote('Menu digitale')}&body={quote(body)}"
    page = (ROOT / "website" / "menu-digitali.src.html").read_text()
    for key, value in {"{{MAILTO}}": html.escape(mailto), "{{SALES_EMAIL}}": c["sales_email"],
                       "{{COMPANY_NAME}}": html.escape(c["name"]), "{{COMPANY_LINE}}": c["ident"], **logos}.items():
        page = page.replace(key, value)
    left = re.findall(r"\{\{[A-Z_]+\}\}", page)
    assert not left, left
    (OUT.parent / "menu-digitali.html").write_text(page)


def main() -> None:
    shot = base64.b64encode((ROOT / "website" / "desktop.webp").read_bytes()).decode()
    page = SRC.read_text()
    for key, value in {
        "{{LOGO_LIGHT}}": svg("trota-logo-light.svg"),
        "{{LOGO_DARK}}": svg("trota-logo-dark.svg"),
        "{{SHOT}}": "data:image/webp;base64," + shot,
        "{{DL}}": DOWNLOADS,
        "{{DOCS_URL}}": REPO + "/blob/claude/trota-os-linux-distro-410sep/docs/installation.md",
        "{{REPO_URL}}": REPO,
        "{{COMPANY_LINE}}": company()["ident"],
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
    shutil.copytree(ROOT / "website" / "fonts", OUT.parent / "fonts", dirs_exist_ok=True)
    logos = {"{{LOGO_LIGHT}}": svg("trota-logo-light.svg"), "{{LOGO_DARK}}": svg("trota-logo-dark.svg")}
    legal_pages(company(), logos)
    menu_page(company(), logos)
    for f in (OUT, FRAGMENT):
        print(f"{f} ({f.stat().st_size // 1024} KiB)")


if __name__ == "__main__":
    main()
