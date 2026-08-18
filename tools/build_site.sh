#!/usr/bin/env bash
# Build both language editions and assemble the publishable site in docs/.
#
#   bash tools/build_site.sh
#
# Result:
#   docs/index.html   language chooser
#   docs/en/          English book
#   docs/id/          Indonesian book
#   docs/.nojekyll    stops GitHub Pages stripping directories starting with _
#
# Point GitHub Pages at the docs/ folder on the main branch, or let the
# workflow in .github/workflows/publish.yml do it on every push.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Generate code listings first. Quarto's pre-render hook runs too late for
# book projects, whose include directives are resolved during chapter scanning.
echo "==> Generating code snippets"
python3 tools/build_snippets.py

echo "==> English"
quarto render --profile en

echo "==> Bahasa Indonesia"
quarto render --profile id

echo "==> Landing page, assets and learning platform"
mkdir -p docs
cp landing/index.html docs/index.html
rm -rf docs/assets docs/lms
cp -r landing/assets docs/assets

# The two books live in docs/en and docs/id and both reference "../lms/",
# so one shared copy at docs/lms serves both editions.
mkdir -p docs/lms
cp lms/lms.js lms/lms.css lms/config.js docs/lms/

# GitHub Pages runs Jekyll by default, which ignores any directory whose name
# begins with an underscore. Quarto emits several. This file disables Jekyll.
touch docs/.nojekyll

# Uncomment and set your domain if you use one.
# echo "gee.example.com" > docs/CNAME

echo
echo "Done. Preview locally with:"
echo "    python3 -m http.server -d docs 8080"
