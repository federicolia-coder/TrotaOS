import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PO_FILES = sorted((ROOT / "po").glob("*.po"))
PLACEHOLDER = re.compile(r"\{[a-z_]+(?::[^}]*)?\}")


def entries(path):
    text = path.read_text(encoding="utf-8")
    for block in text.split("\n\n"):
        def get(key):
            m = re.search(r"^" + re.escape(key) + r' ((?:".*"\n?)+)', block + "\n", re.M)
            return "".join(re.findall(r'"(.*)"', m.group(1))) if m else None
        mid = get("msgid")
        if not mid:
            continue
        strs = [s for s in (get("msgstr"), get("msgstr[0]"), get("msgstr[1]")) if s is not None]
        yield mid, get("msgid_plural"), strs, "fuzzy" in block


@pytest.mark.parametrize("po", PO_FILES, ids=lambda p: p.name)
def test_po_compiles(po, tmp_path):
    if not shutil.which("msgfmt"):
        pytest.skip("gettext not installed")
    p = subprocess.run(["msgfmt", "--check", "-o", str(tmp_path / "x.mo"), str(po)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr


@pytest.mark.parametrize("po", PO_FILES, ids=lambda p: p.name)
def test_complete_and_placeholders_match(po):
    for mid, plural, strs, fuzzy in entries(po):
        assert not fuzzy, mid
        assert strs and all(strs), f"untranslated: {mid}"
        expected = set(PLACEHOLDER.findall(mid)) | set(PLACEHOLDER.findall(plural or ""))
        for s in strs:
            assert set(PLACEHOLDER.findall(s)) == expected, f"{mid!r} -> {s!r}"


def test_pot_is_up_to_date(tmp_path):
    """Every translatable string in the code must be in the template."""
    if not shutil.which("xgettext"):
        pytest.skip("gettext not installed")
    files = sorted(str(p) for p in (ROOT / "applications").rglob("*.py"))
    out = tmp_path / "new.pot"
    subprocess.run(["xgettext", "--language=Python", "--keyword=_", "--keyword=ngettext:1,2",
                    "--from-code=UTF-8", "-o", str(out), *files], check=True)
    new = {m for m, *_ in entries(out)}
    old = {m for m, *_ in entries(ROOT / "po" / "trota-os.pot")}
    assert new == old, f"run scripts/build/update-translations.sh (missing: {sorted(new - old)[:5]})"
