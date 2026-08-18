# Planetary-Scale Cloud GIS &middot; GIS Awan Skala Planet

Source for the bilingual book *Planetary-Scale Cloud GIS: Earth Engine and GeoAI, taught the way it is actually practised*, by Rifky Nauval Hendrawan.

Built with [Quarto](https://quarto.org). One source tree renders an English site, an Indonesian site and a PDF of each, published to GitHub Pages.

**Live at:** `https://<username>.github.io/<repo>/`

---

## Publishing checklist

Everything below is already configured. This is what you do once.

1. Create the repository and push this directory to `main`.
2. In **Settings → Pages**, set *Source* to **GitHub Actions**.
3. Push. The workflow in `.github/workflows/publish.yml` renders both languages and deploys.
4. Optional: set a custom domain in Settings → Pages, then uncomment the `CNAME` line in `tools/build_site.sh`.
5. Optional: uncomment `repo-url` and `repo-actions` in `en/_quarto.yml` and `id/_quarto.yml` so readers get an "edit this page" link. This is the cheapest source of typo fixes you will ever find.

Build locally before pushing:

```bash
bash tools/build_site.sh
python3 -m http.server -d docs 8080
```

To work on one language with live reload, prepare it once then preview:

```bash
python3 tools/build_snippets.py
cp theme.scss theme-dark.scss styles.css references.bib en/
cp landing/assets/favicon.svg en/favicon.svg
quarto preview en
```

Both preparation steps are necessary on a fresh clone, because `_snippets/` and the copied assets are generated output and therefore gitignored. Quarto resolves `{{< include >}}` directives while scanning chapters, which happens before its own pre-render hook fires, so the snippets must exist before Quarto starts.

---

## How the bilingual setup works

`en/` and `id/` are two **independent Quarto book projects**, each with its own `_quarto.yml`.

This is not the arrangement you would guess. Quarto profiles look like the obvious tool, and they do not work here: a book requires its home page to be `index.qmd` at the project root, and a project has exactly one root, so a single project cannot host two home pages. Two projects is the only structure Quarto supports for this.

```
quarto render en    ->  en/_book/   ->  docs/en/
quarto render id    ->  id/_book/   ->  docs/id/
landing/index.html               ->  docs/index.html   (language chooser)
```

`tools/build_site.sh` does all of that in one command, and the CI workflow calls the same script, so the local build and the deployed build cannot drift apart.

Chapter filenames are identical in `en/` and `id/`, which keeps the two editions aligned and makes the sidebar language switcher trivial. A reader on `en/09-cloud-masking.html` can be sent straight to `id/09-cloud-masking.html`.

### Shared files, and why they get copied

Four files live once at the repository root and are copied into each language project at build time: `theme.scss`, `theme-dark.scss`, `styles.css` and `references.bib`, plus the favicon.

Quarto resolves theme and bibliography paths relative to the project, so referencing them with `../` is fragile. Copying is boring and it always works. The copies are gitignored. **Edit the originals at the root, never the copies.**

The format block in `en/_quarto.yml` is duplicated in `id/_quarto.yml`. That is deliberate. Sharing it through a parent metadata file works until it does not, and a broken build costs more than forty lines of repeated YAML.

Chapter filenames are identical in `en/` and `id/`, which keeps the two editions aligned and makes a language switcher in the sidebar trivial. A reader on `en/09-cloud-masking.html` can be sent straight to `id/09-cloud-masking.html`.

---

## The one rule about code

**Edit `scripts/<lang>/`. Never edit `_snippets/`.**

`_snippets/` is generated output. It is gitignored and must be built before the first render on any new machine, with `python3 tools/build_snippets.py`.

Every listing in the book is generated from a real, runnable file. Quarto runs `tools/build_snippets.py` before each render, which wraps each script in a fenced block and writes it to `_snippets/<lang>/`. Chapters pull it in with a project relative path:

```markdown
{{< include _snippets/ch09_annual_composite.qmd >}}
```

A reader can copy `scripts/en/ch09_annual_composite.js` straight into the Code Editor and it will run. The printed version cannot drift away from it.

### Translating a script

Scripts fall back to English automatically. To provide an Indonesian version of `scripts/en/ch10_multisensor_stack.js`, create `scripts/id/ch10_multisensor_stack.js` with translated comments. The build picks it up with no other change. The build log prints every script still using the fallback, which doubles as a translation to do list:

```
. id/ch10_multisensor_stack.js: no translation yet, using en
```

### Optional directives

```javascript
//| title: A cloud free annual composite
//| lines: 12-48      print only this range
//| hide: true        do not print; download only
```

Python scripts use `#|` instead of `//|`.

---

## Layout

```
.
├── en/_quarto.yml            English book project config
├── en/index.qmd              English home page, required at project root
├── en/*.qmd                  English chapters
├── en/_snippets/             generated listings, gitignored
├── id/_quarto.yml            Indonesian book project config
├── id/index.qmd              Indonesian home page
├── id/*.qmd                  Indonesian chapters
├── id/_snippets/             generated listings, gitignored
├── scripts/en/               runnable code, source of truth
├── scripts/id/               translated variants, optional
├── landing/index.html        root language chooser
├── landing/assets/           favicon and shared static assets
├── tools/build_snippets.py   script to snippet generator (pre-render)
├── tools/build_site.sh       render both languages and assemble docs/
├── theme.scss                light theme, copied into each project at build
├── theme-dark.scss           dark theme, copied into each project at build
├── styles.css                structural helpers, copied in at build
├── references.bib            shared bibliography, copied in at build
└── docs/                     build output, served by GitHub Pages
```

---

## Adding or finishing a chapter

1. Write the script in `scripts/en/chNN_short_name.js`, commented in the style of Appendix C.
2. Open the chapter with a `.chapter-goal` block stating what the reader will be able to do, phrased as a capability rather than a topic.
3. Pull the listing in with an include shortcode.
4. Add prose before and after: concept first, then the code, then close analysis of the two or three decisions in it that could have gone another way.
5. End with exercises. One that changes a parameter, one that breaks the script deliberately, one applied to the reader's own study area.
6. Mirror the file in `id/`.
7. Add it to the `chapters:` list in **both** `en/_quarto.yml` and `id/_quarto.yml`.

### Callout conventions

| Callout | English title | Judul Indonesia | Used for |
|---|---|---|---|
| `.callout-note` | Concept | Konsep | Background theory, skippable first pass |
| `.callout-warning` | Common failure | Kesalahan umum | Easy to make, hard to diagnose |
| `.callout-important` | Scientific integrity | Integritas ilmiah | Valid code, indefensible result |
| `.callout-tip` | From the field | Dari lapangan | Only shows up in operational work |

---

## Status

| Part | Chapters | English | Indonesian |
|---|---|---|---|
| Front matter | Preface, How this book differs | Written | Written |
| I. Foundations, purpose and physics | 1 to 4 | Written | Written |
| II. The platform | 5 to 7 | Written | Outlined, code included |
| III. Analysis ready data | 8 to 11 | 8, 9 written; 10, 11 outlined with code | Outlined, code included |
| IV. Feature engineering | 12 to 15 | 15 written; 12 to 14 outlined | Outlined, ch15 code included |
| V. Machine learning | 16 to 18 | **Written** | Outlined, code included |
| VI. GeoAI and impact | 19 to 23 | 22 written; 19 code complete | Outlined, code included |
| Appendices | A to D | Written | Written |
| Platform | dashboard, instructor inbox, quizzes | Live | Live |

Outlined chapters carry a settled section plan and, where a script exists, the complete runnable listing. Nothing is a placeholder with no content.

---

## Learning platform layer

The site is more than a book. Readers get progress tracking, inline knowledge checks, private per chapter notes, and a direct question channel to you.

It runs in two modes and switches automatically based on `lms/config.js`.

| | Local mode (default) | Account mode |
|---|---|---|
| Setup | None | About twenty minutes |
| Sign in | A name, stored in the browser | Magic link to the reader's email |
| Progress and notes | That browser only | Follows them across devices |
| Questions reach you | Pre filled email to rifkynauvalhsp@gmail.com, or a Formspree endpoint | A table you read at `/en/instructor.html` |
| Cost | Nothing | Nothing, Supabase free tier |

Full setup is in **`lms/README-lms.md`**. The short version: create a Supabase project, run `lms/supabase-schema.sql`, paste the project URL and anon key into `lms/config.js`. The anon key is meant to be public; row level security is what protects the data.

### Files

```
lms/config.js            the only file you edit
lms/lms.js               engine: storage adapter, quizzes, progress, notes, questions
lms/lms.css              styling, light and dark
lms/supabase-schema.sql  tables and row level security for account mode
lms/README-lms.md        full setup guide
en/dashboard.qmd         reader progress dashboard
en/instructor.qmd        question inbox, instructor only
```

### Adding a knowledge check

A raw HTML block anywhere in a chapter. No shortcode, no filter, no build step.

````markdown
<script type="application/json" class="lms-quiz">
{
  "id": "ch02-signatures",
  "questions": [
    {
      "q": "What causes the near infrared plateau in a healthy leaf?",
      "options": ["Chlorophyll absorption",
                  "Internal cell structure scattering the light",
                  "Water content",
                  "Surface wax"],
      "answer": 1,
      "why": "Chlorophyll works in the red. The plateau comes from the spongy mesophyll."
    }
  ]
}
</script>
````

`answer` is a zero based index. `why` shows after answering whether the reader was right or wrong, because that is the moment an explanation lands hardest. Three or four options: two is a coin flip, five is padding. Put the check after the section it tests, not at the end of the chapter.

Chapters that already have one: EN 1, 2, 3, 9, 22 and ID 1, 2, 3.

### If the platform breaks

It cannot take the book down with it. `lms.js` wraps its startup in a catch, logs a warning and stops. Chapters still render, listings still copy, navigation still works.

---

## Licensing

Prose CC BY 4.0, code MIT. See `LICENSE-content.md`.
