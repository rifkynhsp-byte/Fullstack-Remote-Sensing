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

# booklib.py is imported by the executed Python chunks in the chapters. It
# travels with the other shared assets for the same reason they do: one copy
# at the root is the source of truth, and both editions compute from it.
SHARED=(theme.scss theme-dark.scss styles.css references.bib booklib.py)

# ---------------------------------------------------------------------------
# Freeze invalidation
# ---------------------------------------------------------------------------
# Chapters that execute Python are cached in _freeze/, and Quarto decides
# whether a cache entry is stale by looking at the chapter file alone.
#
# That is not enough here. A chapter's frozen result contains its includes
# already resolved, so editing a widget in interactive/, or booklib.py which
# the chunks import, changes what the page should say without changing any
# file Quarto is watching. The build then succeeds and publishes the old
# widget, which is the worst kind of failure: silent, and invisible until a
# reader reports that a control does not do what the text says it does.
#
# So anything newer than a frozen result invalidates it explicitly.
echo "==> Checking the freeze cache"
python3 - <<'PYEOF'
import pathlib, shutil

root = pathlib.Path(".")
watched = list(root.glob("interactive/*.qmd")) + [root / "booklib.py"]
newest = max((p.stat().st_mtime for p in watched if p.exists()), default=0)

dropped = []
for lang in ("en", "id"):
    freeze = root / lang / "_freeze"
    if not freeze.is_dir():
        continue
    for entry in freeze.iterdir():
        if not entry.is_dir() or entry.name == "site_libs":
            continue
        results = list(entry.rglob("execute-results/*.json"))
        if not results:
            continue
        if max(r.stat().st_mtime for r in results) < newest:
            shutil.rmtree(entry)
            dropped.append(f"{lang}/{entry.name}")

if dropped:
    print("  re-executing, a shared dependency is newer: " + ", ".join(dropped))
else:
    print("  up to date")
PYEOF

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

  # Images are shared between editions. Copying rather than referencing with
  # ../ keeps every path inside the Quarto project, which is the arrangement
  # Quarto handles reliably.
  rm -rf "$LANG/images"
  cp -r images "$LANG/images"

  # Interactive widgets, shared between editions. Each one detects the page
  # language at runtime and labels itself accordingly.
  rm -rf "$LANG/interactive"
  cp -r interactive "$LANG/interactive"

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
cp lms/lms.js lms/lms.css lms/config.js lms/visitors.js lms/pyodide-cell.js \
   lms/app.js docs/lms/

# The app layer. All three of these must sit at the root of the site: a
# service worker can only control the directory it is served from and below,
# and both books live one level down, so a copy inside en/ could not cover
# id/ and neither could cover the landing page.
cp landing/manifest.webmanifest docs/manifest.webmanifest
cp landing/sw.js docs/sw.js
cp landing/offline.html docs/offline.html

# GitHub Pages runs Jekyll by default, which ignores any directory whose name
# begins with an underscore. Quarto emits several. This file disables Jekyll.
touch docs/.nojekyll

# Uncomment and set your domain if you use one.
# echo "gee.example.com" > docs/CNAME

echo
echo "Done. Preview locally with:"
echo "    python3 -m http.server -d docs 8080"
