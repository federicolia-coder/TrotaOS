#!/usr/bin/env python3
"""Convert the Markdown documentation in docs/ to a small offline HTML site.

Usage: build-docs.py SRC_DIR OUT_DIR
Requires python3-markdown.  Links between .md files are rewritten to .html.
Used by debian/rules for the trota-docs package.
"""

import html
import re
import shutil
import sys
from pathlib import Path

import markdown

CSS = """
:root { color-scheme: light dark; --orange: #FF6A2A; --carbon: #101214; --graphite: #191D21;
        --steel: #737B84; --frost: #E8ECEF; }
body { margin: 0; font-family: Inter, "Ubuntu Sans", system-ui, sans-serif; line-height: 1.6;
       background: #fff; color: var(--carbon); }
header { background: var(--carbon); color: var(--frost); padding: 18px 24px; border-bottom: 3px solid var(--orange); }
header a { color: var(--frost); text-decoration: none; font-weight: 800; letter-spacing: .08em; }
header span { color: var(--orange); }
nav { padding: 12px 24px; background: #f3f5f6; font-size: .95em; }
nav a { margin-right: 14px; color: inherit; }
main { max-width: 860px; margin: 0 auto; padding: 16px 24px 48px; }
a { color: #c94a12; }
code, pre { font-family: "Ubuntu Sans Mono", "DejaVu Sans Mono", monospace; font-size: .92em; }
pre { background: var(--graphite); color: var(--frost); padding: 12px; overflow-x: auto; border-radius: 6px; }
table { border-collapse: collapse; width: 100%; } th, td { border: 1px solid #ccd2d7; padding: 6px 8px; text-align: left; }
th { background: #eef1f3; }
@media (prefers-color-scheme: dark) {
  body { background: var(--carbon); color: var(--frost); } nav { background: var(--graphite); }
  a { color: var(--orange); } th { background: var(--graphite); } th, td { border-color: #343a41; }
}
"""

TEMPLATE = """<!DOCTYPE html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Trota OS</title><link rel="stylesheet" href="style.css"></head>
<body><header><a href="index.html">TROTA <span>OS</span></a></header>
<nav>{nav}</nav><main>{body}</main></body></html>
"""


def title_of(text: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return m.group(1).strip() if m else fallback


def main(src: str, out: str) -> int:
    src_dir, out_dir = Path(src), Path(out)
    pages = sorted(p for p in src_dir.glob("*.md"))
    if not pages:
        print(f"no Markdown files in {src_dir}", file=sys.stderr)
        return 1
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    (out_dir / "style.css").write_text(CSS)
    if (src_dir / "images").is_dir():
        shutil.copytree(src_dir / "images", out_dir / "images")
    titles = {p: title_of(p.read_text(encoding="utf-8"), p.stem) for p in pages}
    order = [p for p in pages if p.stem == "README"] + [p for p in pages if p.stem != "README"]
    nav = " ".join(
        f'<a href="{"index" if p.stem == "README" else p.stem}.html">{html.escape(titles[p])}</a>' for p in order
    )
    for p in pages:
        text = p.read_text(encoding="utf-8")
        text = re.sub(r"\]\((?!https?://)([\w\-./]+)\.md(#[\w\-]*)?\)",
                      lambda m: f"]({'index' if Path(m.group(1)).name == 'README' else Path(m.group(1)).name}.html{m.group(2) or ''})",
                      text)
        body = markdown.markdown(text, extensions=["tables", "fenced_code", "toc", "sane_lists"])
        name = "index.html" if p.stem == "README" else f"{p.stem}.html"
        (out_dir / name).write_text(TEMPLATE.format(title=html.escape(titles[p]), nav=nav, body=body), encoding="utf-8")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
