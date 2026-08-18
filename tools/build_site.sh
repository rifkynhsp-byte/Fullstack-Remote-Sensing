#!/usr/bin/env bash
# Build both language editions and assemble the publishable site in docs/.
#
#   bash tools/build_site.sh
#
# Result:
#   docs/index.html   language chooser
#   docs/en/          English book
#   docs/id/          Indonesian book
#   docs/lms/         learning platform assets, shared by both editions
#   docs/assets/      favicon and shared static files
#   docs/.nojekyll    stops GitHub Pages stripping directories starting with _
#
# Structure note
#   en/ and id/ are two independent Quarto book projects, each with its own
#   _quarto.yml. Quarto requires a book's home page to be index.qmd at the
#   project root, and a project has only one root, so a single project cannot
#   serve two languages. This script renders each in turn and assembles the
#   results.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SHARED=(theme.scss theme-dark.scss styles.css references.bib)

echo "==> Generating code listings"
# Must run before Quarto starts. Book projects resolve include directives
# while scanning chapters, which happens before the pre-render hook fires.
python3 tools/build_snippets.py

for LANG in en id; do
  echo "==> Preparing $LANG"
  # One source of truth at the repository root, copied into each project.
  # The copies are gitignored; never edit them.
  for FILE in "${SHARED[@]}"; do
    cp "$FILE" "$LANG/$FILE"
  done
  cp landing/assets/favicon.svg "$LANG/favicon.svg"

  echo "==> Rendering $LANG"
  quarto render "$LANG"
done

echo "==> Assembling docs/"
rm -rf docs
mkdir -p docs docs/lms

cp -r en/_book docs/en
cp -r id/_book docs/id

cp landing/index.html docs/index.html
cp -r landing/assets docs/assets

# Both books reference "../lms/", so one shared copy serves both editions.
cp lms/lms.js lms/lms.css lms/config.js docs/lms/

# GitHub Pages runs Jekyll by default, which ignores any directory whose name
# begins with an underscore. Quarto emits several. This file disables Jekyll.
touch docs/.nojekyll

# Uncomment and set your domain if you use one.
# echo "gee.example.com" > docs/CNAME

echo
echo "Done. Preview locally with:"
echo "    python3 -m http.server -d docs 8080"
