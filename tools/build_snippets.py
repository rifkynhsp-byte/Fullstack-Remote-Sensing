#!/usr/bin/env python3
"""
build_snippets.py
=================

Single source of truth for every code listing in this book.

Teaching scripts live under `scripts/<lang>/` as real, runnable files. A
reader copies one into the Earth Engine Code Editor, or into a Colab cell
for the Python chapters, and presses Run. This script wraps each one in a
fenced Quarto code block and writes it to `_snippets/<lang>/`, so chapters
pull the listing in with an include shortcode:

    {{< include ../_snippets/en/ch09_annual_composite.qmd >}}

Because snippets are regenerated before every render, the printed listing
can never fall out of sync with the file the reader downloads.

Language fallback
-----------------
A script only needs an Indonesian variant when the comments are genuinely
translated. If `scripts/id/ch09_annual_composite.js` does not exist, this
builder uses the English source for the Indonesian book instead, so that
book never has a hole where a listing should be. Each fallback is reported
on stdout during the build, which doubles as a translation to do list.

Optional per file directives
----------------------------
The first lines of a script may carry directives inside comments. They are
read, then stripped from the printed listing:

    //| title: A cloud free annual composite
    //| lines: 12-48          print only this line range
    //| hide: true            skip printing entirely, download only

Python scripts use the same syntax with a `#|` prefix.

Usage
-----
    python3 tools/build_snippets.py

Quarto calls this automatically through the `pre-render` key in _quarto.yml.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = ROOT / "scripts"
SNIPPET_DIR = ROOT / "_snippets"

LANGUAGES = ["en", "id"]
FALLBACK_FROM = "en"

DIRECTIVE = re.compile(r"^(?://\||#\|)\s*(\w+)\s*:\s*(.+?)\s*$")

HIGHLIGHT = {".js": "javascript", ".py": "python", ".sh": "bash", ".json": "json"}


def parse_directives(lines: list[str]) -> tuple[dict[str, str], list[str]]:
    """Pull `//| key: value` or `#| key: value` lines off the top of a script."""
    meta: dict[str, str] = {}
    body_start = 0
    for i, line in enumerate(lines):
        match = DIRECTIVE.match(line)
        if match:
            meta[match.group(1).lower()] = match.group(2)
            body_start = i + 1
        elif line.strip() == "" and meta:
            body_start = i + 1
        else:
            break
    return meta, lines[body_start:]


def slice_lines(lines: list[str], spec: str | None) -> list[str]:
    """Apply a `lines: 12-48` directive, if present."""
    if not spec:
        return lines
    try:
        first, last = (int(part) for part in spec.split("-", 1))
    except ValueError:
        print(f"  ! ignoring malformed lines directive: {spec}", file=sys.stderr)
        return lines
    return lines[first - 1 : last]


def build(path: Path, display_path: str) -> str | None:
    raw = path.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    meta, body = parse_directives(raw)

    if meta.get("hide", "").lower() == "true":
        return None

    body = slice_lines(body, meta.get("lines"))

    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()

    lang = HIGHLIGHT.get(path.suffix, "text")
    fence = "```{." + lang + f' filename="{display_path}"' + "}"

    return "\n".join([fence, *body, "```", ""])


def main() -> int:
    if not SCRIPT_DIR.is_dir():
        print(f"No scripts/ directory at {SCRIPT_DIR}; nothing to do.")
        return 0

    written = 0
    fell_back = 0

    for lang in LANGUAGES:
        source_dir = SCRIPT_DIR / lang
        fallback_dir = SCRIPT_DIR / FALLBACK_FROM
        target_dir = SNIPPET_DIR / lang
        target_dir.mkdir(parents=True, exist_ok=True)

        names = set()
        for directory in (source_dir, fallback_dir):
            if directory.is_dir():
                names.update(p.name for p in directory.iterdir() if p.is_file())

        for name in sorted(names):
            localised = source_dir / name
            if localised.exists():
                chosen, display = localised, f"scripts/{lang}/{name}"
            else:
                chosen, display = fallback_dir / name, f"scripts/{FALLBACK_FROM}/{name}"
                fell_back += 1
                print(f"  . {lang}/{name}: no translation yet, using {FALLBACK_FROM}")

            if not chosen.exists():
                continue

            snippet = build(chosen, display)
            if snippet is None:
                continue

            (target_dir / f"{Path(name).stem}.qmd").write_text(snippet, encoding="utf-8")
            written += 1

    print(f"build_snippets: wrote {written} snippet(s), {fell_back} using fallback")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
