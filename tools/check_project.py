#!/usr/bin/env python3
"""
check_project.py
================

Pre-flight checks that run before Quarto does.

Quarto is slow to fail. A missing include or a malformed callout surfaces
several minutes into a render, deep in a log, after the runner has already
installed a toolchain. Every check below runs in under a second and catches
the class of error that has actually broken this project's builds.

Run it locally, or let the CI workflow run it as its first step:

    python3 tools/check_project.py

Exits 0 if everything passes, 1 otherwise, with the offending file and line.

What it does NOT do
-------------------
It cannot tell you whether Pandoc will accept a document. Only a render can.
It catches structure, paths and configuration, which is where every failure so
far has come from.
"""

from __future__ import annotations

import collections
import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parent.parent
LANGUAGES = ["en", "id"]
SHARED_ASSETS = ["theme.scss", "theme-dark.scss", "styles.css", "references.bib"]

problems: list[str] = []


def fail(message: str) -> None:
    problems.append(message)


def section(title: str) -> None:
    print(f"\n{title}")


# ---------------------------------------------------------------------------
# 1. Repository shape
# ---------------------------------------------------------------------------
def check_repository_shape() -> None:
    section("Repository shape")

    # A _quarto.yml at the root makes Quarto treat the repository itself as a
    # book project, look for index.qmd there, and fail. This is what the web
    # uploader's folder flattening produces, and it has broken this build once.
    for stray in ["_quarto.yml", "_quarto-en.yml", "_quarto-id.yml"]:
        if (ROOT / stray).exists():
            fail(f"{stray} exists at the repository root. Delete it. "
                 f"The book configs belong at en/_quarto.yml and id/_quarto.yml.")

    stray_qmd = sorted(p.name for p in ROOT.glob("*.qmd"))
    if stray_qmd:
        fail(f"Chapter files found at the repository root: {stray_qmd[:5]}"
             f"{' and more' if len(stray_qmd) > 5 else ''}. "
             f"These belong in en/ or id/. Usually caused by the GitHub web "
             f"uploader flattening folders.")

    # Files whose names carry an upload collision suffix, such as "(3)".
    collisions = sorted(p.name for p in ROOT.rglob("*") if re.search(r"\(\d+\)\.", p.name))
    if collisions:
        fail(f"Files with upload collision suffixes: {collisions[:5]}"
             f"{' and more' if len(collisions) > 5 else ''}. Delete them.")

    for lang in LANGUAGES:
        if not (ROOT / lang / "_quarto.yml").exists():
            fail(f"{lang}/_quarto.yml is missing.")
        if not (ROOT / lang / "index.qmd").exists():
            fail(f"{lang}/index.qmd is missing. Quarto books require the home "
                 f"page to be index.qmd at the project root.")

    for asset in SHARED_ASSETS:
        if not (ROOT / asset).exists():
            fail(f"Shared asset {asset} is missing from the repository root.")

    print("  checked root layout, language projects and shared assets")


# ---------------------------------------------------------------------------
# 2. Book configuration
# ---------------------------------------------------------------------------
def check_configs() -> None:
    section("Book configuration")

    for lang in LANGUAGES:
        path = ROOT / lang / "_quarto.yml"
        if not path.exists():
            continue
        try:
            cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            fail(f"{lang}/_quarto.yml is not valid YAML: {exc}")
            continue

        chapters: list[str] = []
        for entry in cfg.get("book", {}).get("chapters", []):
            chapters += entry["chapters"] if isinstance(entry, dict) else [entry]
        chapters += cfg.get("book", {}).get("appendices", [])

        if not chapters:
            fail(f"{lang}/_quarto.yml lists no chapters.")
            continue

        if chapters[0] != "index.qmd":
            fail(f"{lang}/_quarto.yml lists '{chapters[0]}' first. A Quarto book "
                 f"requires index.qmd to be the first chapter.")

        missing = [c for c in chapters if not (ROOT / lang / c).exists()]
        if missing:
            fail(f"{lang}: listed but missing on disk: {missing}")

        on_disk = {p.name for p in (ROOT / lang).glob("*.qmd")}
        orphans = sorted(on_disk - set(chapters))
        if orphans:
            fail(f"{lang}: present on disk but not listed in _quarto.yml: {orphans}. "
                 f"They will not appear in the book.")

        # Anything fetched over the network at render time is a build that can
        # fail for reasons outside the repository. This has broken a build once.
        raw = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(raw.split("\n"), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.search(r"^\s*(csl|bibliography|theme|css):.*https?://", line):
                fail(f"{lang}/_quarto.yml:{line_no} fetches a build time resource "
                     f"over the network. Vendor the file instead.")

        print(f"  {lang}: {len(chapters)} pages, formats {list(cfg.get('format', {}))}")


# ---------------------------------------------------------------------------
# 3. Chapter structure
# ---------------------------------------------------------------------------
def check_chapters() -> None:
    section("Chapter structure")

    total = 0
    for lang in LANGUAGES:
        for path in sorted((ROOT / lang).glob("*.qmd")):
            total += 1
            text = path.read_text(encoding="utf-8")
            lines = text.split("\n")
            rel = f"{lang}/{path.name}"

            # Balanced code fences.
            if sum(1 for l in lines if l.strip().startswith("```")) % 2:
                fail(f"{rel}: odd number of code fences, one is unclosed.")

            # Balanced and well formed callout divs.
            depth = 0
            in_fence = False
            for line_no, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("```"):
                    in_fence = not in_fence
                if in_fence:
                    continue
                if re.match(r"^:::+\s*\{", stripped):
                    depth += 1
                elif re.match(r"^:::+\s*$", stripped):
                    depth -= 1
                elif re.match(r"^:::+\s+\S", stripped) and "{" not in stripped:
                    fail(f"{rel}:{line_no}: malformed div, text after ::: without "
                         f"a class in braces.")
                if depth < 0:
                    fail(f"{rel}:{line_no}: closing ::: with nothing open.")
                    depth = 0
            if depth != 0:
                fail(f"{rel}: {depth} unclosed callout block(s).")

            # Front matter parses.
            if text.startswith("---"):
                end = text.find("\n---", 3)
                try:
                    yaml.safe_load(text[3:end])
                except yaml.YAMLError as exc:
                    fail(f"{rel}: front matter is not valid YAML: {exc}")

            # Includes resolve, relative to the including file.
            for match in re.finditer(r"\{\{<\s*include\s+([^\s>]+)\s*>\}\}", text):
                target = (ROOT / lang / match.group(1)).resolve()
                if not target.exists():
                    fail(f"{rel}: include not found: {match.group(1)}. "
                         f"Run tools/build_snippets.py first.")

            # Embedded quizzes are valid JSON with in range answers.
            for match in re.finditer(
                    r'class="lms-quiz">(.*?)</script>', text, re.S):
                import json
                try:
                    spec = json.loads(match.group(1))
                except json.JSONDecodeError as exc:
                    fail(f"{rel}: quiz JSON is malformed: {exc}")
                    continue
                if not spec.get("id"):
                    fail(f"{rel}: quiz is missing an id.")
                for q in spec.get("questions", []):
                    if not 0 <= q.get("answer", -1) < len(q.get("options", [])):
                        fail(f"{rel}: quiz '{spec.get('id')}' has an answer index "
                             f"outside its options.")

    print(f"  checked {total} chapter files")


# ---------------------------------------------------------------------------
# 4. Cross references
# ---------------------------------------------------------------------------
def check_cross_references() -> None:
    section("Cross references")

    for lang in LANGUAGES:
        defined: set[str] = set()
        used: dict[str, set[str]] = collections.defaultdict(set)
        counts: collections.Counter = collections.Counter()

        for path in (ROOT / lang).glob("*.qmd"):
            text = path.read_text(encoding="utf-8")
            for anchor in re.findall(r"\{#((?:sec|fig|tbl|eq)-[\w-]+)", text):
                defined.add(anchor)
                counts[anchor] += 1
            for ref in re.findall(r"@((?:sec|fig|tbl|eq)-[\w-]+)", text):
                used[ref].add(path.name)

        for anchor, n in counts.items():
            if n > 1:
                fail(f"{lang}: anchor #{anchor} is defined {n} times.")

        dangling = {k: v for k, v in used.items() if k not in defined}
        for ref, files in dangling.items():
            fail(f"{lang}: @{ref} referenced in {sorted(files)} but never defined.")

        print(f"  {lang}: {len(defined)} anchors, {len(used)} references")


# ---------------------------------------------------------------------------
# 5. Code listings
# ---------------------------------------------------------------------------
def check_scripts() -> None:
    section("Code listings")

    scripts_en = ROOT / "scripts" / "en"
    if not scripts_en.is_dir():
        fail("scripts/en/ is missing.")
        return

    referenced: set[str] = set()
    for lang in LANGUAGES:
        for path in (ROOT / lang).glob("*.qmd"):
            for match in re.finditer(r"\{\{<\s*include\s+_snippets/([\w.]+)\.qmd", 
                                     path.read_text(encoding="utf-8")):
                referenced.add(match.group(1))

    for stem in sorted(referenced):
        found = list(scripts_en.glob(stem + ".*")) + \
                list((ROOT / "scripts" / "id").glob(stem + ".*"))
        if not found:
            fail(f"No source script for snippet '{stem}' in scripts/en or scripts/id.")

    print(f"  {len(referenced)} listing(s) referenced, all have a source script")


# ---------------------------------------------------------------------------
# 6. Interactive widgets
# ---------------------------------------------------------------------------
def check_widgets() -> None:
    """Every widget a chapter includes has to exist, in both languages.

    A missing include is the cheapest possible build failure to prevent and
    one of the slowest to diagnose: Quarto reports it as a Pandoc error
    several minutes in, naming a path that has already been rewritten by the
    build script.
    """
    section("Interactive widgets")

    widget_dir = ROOT / "interactive"
    if not widget_dir.is_dir():
        fail("interactive/ is missing. tools/build_site.sh copies it into "
             "each language project and the chapters include from it.")
        return

    available = {p.name for p in widget_dir.glob("*.qmd")}
    referenced: dict[str, set[str]] = {lang: set() for lang in LANGUAGES}

    for lang in LANGUAGES:
        for path in sorted((ROOT / lang).glob("*.qmd")):
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r"\{\{<\s*include\s+\.\./interactive/([\w.-]+\.qmd)", text):
                name = match.group(1)
                referenced[lang].add(name)
                if name not in available:
                    fail(f"{path.name} includes interactive/{name}, which does not exist.")

    # A widget included in one edition and not the other is not an error, but
    # it is almost always an oversight, so it is reported rather than failed.
    only_en = referenced["en"] - referenced["id"]
    only_id = referenced["id"] - referenced["en"]
    for name in sorted(only_en):
        print(f"  . {name} is included in en/ but not id/")
    for name in sorted(only_id):
        print(f"  . {name} is included in id/ but not en/")

    unused = sorted(available - referenced["en"] - referenced["id"])
    for name in unused:
        print(f"  . {name} exists but no chapter includes it")

    print(f"  {len(available)} widget(s) available, "
          f"{len(referenced['en'] | referenced['id'])} referenced")


# ---------------------------------------------------------------------------
# 7. Quizzes
# ---------------------------------------------------------------------------
def check_quizzes() -> None:
    """Validate every knowledge check.

    A quiz is raw JSON in a script tag, which means a trailing comma or an
    answer index one past the end of the options list renders perfectly and
    then fails silently in the reader's browser. Nobody reports that; they
    just stop trusting the quizzes. So it is checked here instead.
    """
    section("Knowledge checks")

    total = 0
    questions = 0

    for lang in LANGUAGES:
        for path in sorted((ROOT / lang).glob("*.qmd")):
            text = path.read_text(encoding="utf-8")
            blocks = re.findall(
                r'<script type="application/json" class="lms-quiz">\s*(.*?)\s*</script>',
                text, re.DOTALL)

            seen_ids: set[str] = set()
            for raw in blocks:
                total += 1
                try:
                    quiz = json.loads(raw)
                except json.JSONDecodeError as exc:
                    fail(f"{lang}/{path.name}: quiz JSON is invalid ({exc}).")
                    continue

                qid = quiz.get("id")
                if not qid:
                    fail(f"{lang}/{path.name}: a quiz has no id. The storage key "
                         f"is chapter plus id, so an id is required.")
                elif qid in seen_ids:
                    fail(f"{lang}/{path.name}: duplicate quiz id '{qid}'. "
                         f"Two quizzes sharing an id share a score.")
                else:
                    seen_ids.add(qid)

                items = quiz.get("questions")
                if not isinstance(items, list) or not items:
                    fail(f"{lang}/{path.name}: quiz '{qid}' has no questions.")
                    continue

                for i, q in enumerate(items, 1):
                    questions += 1
                    where = f"{lang}/{path.name}: quiz '{qid}' question {i}"
                    options = q.get("options")

                    if not q.get("q"):
                        fail(f"{where} has no question text.")
                    if not isinstance(options, list) or len(options) < 2:
                        fail(f"{where} needs at least two options.")
                        continue
                    answer = q.get("answer")
                    if not isinstance(answer, int) or not 0 <= answer < len(options):
                        fail(f"{where} has answer {answer!r}, which is not a valid "
                             f"index into its {len(options)} options. The index is "
                             f"zero based.")
                    if not q.get("why"):
                        fail(f"{where} has no 'why'. The explanation is shown "
                             f"whether the reader was right or wrong, and it is "
                             f"the part that teaches.")

    print(f"  {total} quiz block(s), {questions} question(s), all well formed")


# ---------------------------------------------------------------------------
# 8. Executed Python
# ---------------------------------------------------------------------------
def check_python_chunks() -> None:
    """Chapters that execute Python need the engine declared and the library.

    The chunks import booklib, which lives at the repository root and is
    copied into each language project by the build script. If that copy step
    is ever dropped, the render fails on an import error inside a kernel,
    which is a long way from the line that caused it.
    """
    section("Executed Python")

    if not (ROOT / "booklib.py").is_file():
        fail("booklib.py is missing from the repository root. The executed "
             "chunks in the chapters import it.")

    if not (ROOT / "requirements.txt").is_file():
        fail("requirements.txt is missing. CI installs the render's Python "
             "dependencies from it.")

    build = (ROOT / "tools" / "build_site.sh").read_text(encoding="utf-8")
    if "booklib.py" not in build:
        fail("tools/build_site.sh does not copy booklib.py into the language "
             "projects, so the executed chunks will not be able to import it.")

    counts = {}
    for lang in LANGUAGES:
        config = yaml.safe_load((ROOT / lang / "_quarto.yml").read_text(encoding="utf-8"))
        chapters_with_python = []

        for path in sorted((ROOT / lang).glob("*.qmd")):
            text = path.read_text(encoding="utf-8")
            if re.search(r"^```\{python", text, re.MULTILINE):
                chapters_with_python.append(path.name)

        counts[lang] = chapters_with_python

        if chapters_with_python and not config.get("jupyter"):
            fail(f"{lang}/_quarto.yml has no 'jupyter:' key, but "
                 f"{len(chapters_with_python)} chapter(s) contain executable "
                 f"Python chunks. Without it Quarto treats them as plain code "
                 f"blocks and prints nothing.")

    if counts["en"] and set(counts["en"]) != set(counts["id"]):
        only_en = sorted(set(counts["en"]) - set(counts["id"]))
        only_id = sorted(set(counts["id"]) - set(counts["en"]))
        for name in only_en:
            print(f"  . {name} executes Python in en/ but not in id/")
        for name in only_id:
            print(f"  . {name} executes Python in id/ but not in en/")

    # A .py-live block with no code block in it renders as an empty box.
    live = 0
    for lang in LANGUAGES:
        for path in sorted((ROOT / lang).glob("*.qmd")):
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r"::: \{\.py-live\}(.*?):::", text, re.DOTALL):
                live += 1
                if "```" not in match.group(1):
                    fail(f"{lang}/{path.name}: a .py-live block contains no code "
                         f"block, so it would render as an empty frame.")

    print(f"  en: {len(counts['en'])} chapter(s) execute Python, "
          f"id: {len(counts['id'])}; {live} runnable cell(s)")


# ---------------------------------------------------------------------------
# 9. Learning platform assets
# ---------------------------------------------------------------------------
def check_lms_assets() -> None:
    """Every script the books load has to be copied into the published site."""
    section("Learning platform")

    build = (ROOT / "tools" / "build_site.sh").read_text(encoding="utf-8")

    for lang in LANGUAGES:
        config_text = (ROOT / lang / "_quarto.yml").read_text(encoding="utf-8")
        for name in re.findall(r'src="\.\./lms/([\w.-]+)"', config_text):
            if not (ROOT / "lms" / name).is_file():
                fail(f"{lang}/_quarto.yml loads lms/{name}, which does not exist.")
            elif name not in build:
                fail(f"{lang}/_quarto.yml loads lms/{name}, but "
                     f"tools/build_site.sh does not copy it into docs/lms/, "
                     f"so it would 404 on the published site.")

    # The landing page is plain HTML outside both Quarto projects, so nothing
    # else checks its references.
    landing = (ROOT / "landing" / "index.html").read_text(encoding="utf-8")
    for name in re.findall(r'src="lms/([\w.-]+)"', landing):
        if not (ROOT / "lms" / name).is_file():
            fail(f"landing/index.html loads lms/{name}, which does not exist.")
        elif name not in build:
            fail(f"landing/index.html loads lms/{name}, but "
                 f"tools/build_site.sh does not copy it into docs/lms/.")

    config = (ROOT / "lms" / "config.js").read_text(encoding="utf-8")
    email = re.search(r"instructorEmail:\s*'([^']+)'", config)
    if not email:
        fail("lms/config.js has no instructorEmail. Questions in local mode "
             "have nowhere to go without it.")
    elif "@" not in email.group(1):
        fail(f"lms/config.js instructorEmail '{email.group(1)}' is not an "
             f"email address.")
    else:
        print(f"  questions in local mode reach {email.group(1)}")

    # Comments are stripped first: the file's own warning about service_role
    # keys is the reason this check exists, not a violation of it.
    code_only = re.sub(r"/\*.*?\*/", "", config, flags=re.DOTALL)
    code_only = re.sub(r"//.*$", "", code_only, flags=re.MULTILINE)
    # The landing page is hand written HTML with the address in a mailto,
    # so nothing else keeps it in step with config.js. An address that is
    # right in the book and stale on the front page is the worst version of
    # this bug, because the front page is where most readers start.
    if email and "@" in email.group(1):
        address = email.group(1)
        mailtos = set(re.findall(r'mailto:([^"?\'>\s]+)', landing))
        stale = {m for m in mailtos if m != address}
        if stale:
            fail(f"landing/index.html links to {', '.join(sorted(stale))}, but "
                 f"lms/config.js says questions go to {address}. One of them "
                 f"is out of date.")
        elif mailtos:
            print(f"  landing page agrees: {address}")

    if "service_role" in code_only:
        fail("lms/config.js assigns a service_role key. That key must never "
             "be in client code; the anon key is the one that belongs here.")


# ---------------------------------------------------------------------------
def main() -> int:
    print("Pre-flight checks")
    print("=" * 60)

    check_repository_shape()
    check_configs()
    check_chapters()
    check_cross_references()
    check_scripts()
    check_widgets()
    check_quizzes()
    check_python_chunks()
    check_lms_assets()

    print("\n" + "=" * 60)
    if problems:
        print(f"FAILED: {len(problems)} problem(s)\n")
        for i, message in enumerate(problems, 1):
            print(f"  {i}. {message}")
        print("\nFix these before rendering. Quarto would take several minutes "
              "to report the same thing, less clearly.")
        return 1

    print("PASSED. Nothing structurally wrong; safe to render.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
