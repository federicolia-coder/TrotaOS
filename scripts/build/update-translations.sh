#!/bin/sh
# Regenerate po/trota-os.pot from the Python sources and merge it into every
# po/*.po file.  Requires gettext.  Run after changing user-visible strings.
set -eu
cd "$(dirname "$0")/../.."
find applications -name '*.py' ! -path '*/tests/*' | sort > po/POTFILES
xgettext --language=Python --keyword=_ --keyword=ngettext:1,2 --from-code=UTF-8 \
    --package-name="Trota OS" --package-version=1.0 --copyright-holder="TestardStudios" \
    --msgid-bugs-address="https://github.com/federicolia-coder/TrotaOS/issues" \
    --add-comments=TRANSLATORS --sort-by-file \
    -f po/POTFILES -o po/trota-os.pot
for po in po/*.po; do
    [ -e "$po" ] || continue
    msgmerge --quiet --update --backup=none --no-fuzzy-matching "$po" po/trota-os.pot
done
