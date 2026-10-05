"""Put a "Run this chapter" box under the title of every chapter, in both languages (2026-10-05).

For each script the chapter includes: an Open in Code Editor link (the JavaScript in the public Earth Engine
repository users/rifkynauvalhsp/Fullstack-Remote-Sensing) when a JavaScript version exists, and an Open in Colab
link (the notebook built by tools/make_notebooks.py). Chapters whose data is not in Earth Engine say so instead of
offering a JavaScript link. The box sits between marker comments, so running this again replaces it in place.

    python tools/add_run_links.py

Videos: add a line `24-flood: https://youtu.be/...` to videos.yml (chapter file name without .qmd) and run this
again; the video is embedded inside the box with Quarto's video shortcode (YouTube, Vimeo or a direct .mp4 URL).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEE = "https://code.earthengine.google.com/?scriptPath=users/rifkynauvalhsp/Fullstack-Remote-Sensing:{}"
COLAB = "https://colab.research.google.com/github/rifkynhsp-byte/Fullstack-Remote-Sensing/blob/main/notebooks/{}.ipynb"
IJB_APP = "https://code.earthengine.google.com/?accept_repo=users/rifkynauvalhsp/IndrajaBuana"
ACCEPT = "https://code.earthengine.google.com/?accept_repo=users/rifkynauvalhsp/Fullstack-Remote-Sensing"
COLAB_BADGE = "https://colab.research.google.com/assets/colab-badge.svg"
GEE_BADGE = "https://img.shields.io/badge/Open%20in-Earth%20Engine%20Code%20Editor-1a73e8"
REPO_BADGE = "https://img.shields.io/badge/Add%20all%20book%20scripts-to%20your%20Code%20Editor-34a853"
START, END = "<!-- run-links -->", "<!-- /run-links -->"
TEXT = {
    "en": dict(title="Run this chapter", gee="Open in Code Editor", colab="Open in Colab",
               py_only="This chapter's data is not in Earth Engine, so it runs in Python (Colab) only.",
               app="Open the IJB app in the Code Editor", setup="First time? Appendix A shows how to sign in to Earth Engine and Colab.",
               repo="Add all book scripts to your Code Editor (once)"),
    "id": dict(title="Jalankan bab ini", gee="Buka di Code Editor", colab="Buka di Colab",
               py_only="Data bab ini tidak tersedia di Earth Engine, jadi bab ini dijalankan dengan Python (Colab) saja.",
               app="Buka aplikasi IJB di Code Editor", setup="Baru pertama kali? Lampiran A menjelaskan cara masuk ke Earth Engine dan Colab.",
               repo="Tambahkan semua skrip buku ke Code Editor Anda (sekali saja)"),
}


def scripts_of(qmd: str) -> list[str]:
    """Script stems the chapter includes, in the order they appear."""
    found = re.findall(r"_snippets/((?:ch\d\d[a-z]?)_[a-z0-9_]+?)(?:__[^./]*)?\.qmd", qmd)
    seen, out = set(), []
    for s in found:
        if s not in seen and ((ROOT / "scripts/py" / f"{s}.py").exists() or (ROOT / "scripts/en" / f"{s}.js").exists()):
            seen.add(s); out.append(s)
    return out


def videos() -> dict:
    f = ROOT / "videos.yml"
    if not f.exists():
        return {}
    out = {}
    for line in f.read_text(encoding="utf-8").splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            k, v = line.split(":", 1)
            if v.strip():
                out[k.strip()] = v.strip()
    return out


def box(lang: str, stems: list[str], ijb: bool, video: str | None = None) -> str:
    t = TEXT[lang]
    lines = [START, "::: {.callout-tip .run-links appearance=\"simple\" icon=\"false\"}", f"**{t['title']}**", ""]
    any_js = False
    for s in stems:
        links = []
        if (ROOT / "scripts/en" / f"{s}.js").exists():
            links.append(f"[![{t['gee']}]({GEE_BADGE})]({GEE.format(s)})"); any_js = True
        if (ROOT / "notebooks" / f"{s}.ipynb").exists():
            links.append(f"[![{t['colab']}]({COLAB_BADGE})]({COLAB.format(s)})")
        if links:
            lines.append(f"- `{s}` &nbsp; " + " &nbsp; ".join(links))
    if ijb:
        lines.append(f"- [{t['app']}]({IJB_APP})"); any_js = True
    if any_js:
        lines += ["", f"[![{t['repo']}]({REPO_BADGE})]({ACCEPT}) &nbsp; *{t['setup']}*"]
    else:
        lines += ["", t["py_only"], "", f"*{t['setup']}*"]
    if video:
        lines += ["", f"{{{{< video {video} >}}}}"]
    lines += [":::", END]
    return "\n".join(lines)


def main() -> int:
    n, vids = 0, videos()
    for lang in ("en", "id"):
        for qmd in sorted((ROOT / lang).glob("*.qmd")):
            s = qmd.read_text(encoding="utf-8")
            stems = scripts_of(s)
            ijb = qmd.name == "p6-ijb.qmd"
            video = vids.get(qmd.stem)
            if not stems and not ijb and not video:
                continue
            s = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n*", "", s, flags=re.S)   # replace an old box
            lines = s.split("\n")
            h1 = next(i for i, l in enumerate(lines) if l.startswith("# "))
            lines.insert(h1 + 1, "\n" + box(lang, stems, ijb, video) + "\n")
            qmd.write_text("\n".join(lines), encoding="utf-8")
            n += 1
    print(f"run-links box in {n} chapter files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
