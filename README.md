# Planetary-Scale Cloud GIS &middot; GIS Awan Skala Planet

Source for the bilingual book *Planetary-Scale Cloud GIS: Earth Engine and GeoAI, taught the way it is actually practised*, by Rifky Nauval Hendrawan.

Built with [Quarto](https://quarto.org). Renders an English site and an Indonesian site, published to GitHub Pages.

**Live at:** `https://<username>.github.io/<repo>/`

---

## Publishing checklist

Everything below is already configured. This is what you do once.

1. Create the repository and push this directory to `main`.
2. In **Settings → Pages**, set *Source* to **GitHub Actions**.
3. Push. The workflow in `.github/workflows/publish.yml` renders both languages and deploys.
4. Optional: set a custom domain in Settings → Pages, then uncomment the `CNAME` line in `tools/build_site.sh`.
5. Optional: uncomment `repo-url` and `repo-actions` in `en/_quarto.yml` and `id/_quarto.yml` so readers get an "edit this page" link. This is the cheapest source of typo fixes you will ever find.

### Working entirely on GitHub, no local install

You do not need Quarto on your own machine. Two things make browser only work practical.

**Pre-flight checks run first.** Every push triggers a ten second validation job before Quarto is installed. It catches missing includes, stray files at the repository root, unbalanced callouts, dangling cross references and malformed quizzes, and it names the file and line. Those are the errors that have actually broken this build, and Quarto would take several minutes to report the same thing less clearly.

**Codespaces gives you a terminal in a browser tab.** Green **Code** button, **Codespaces** tab, **Create codespace on main**. Quarto and Python are already installed by `.devcontainer/devcontainer.json`. Then:

```bash
bash tools/build_site.sh              # full build, about four minutes
python3 -m http.server -d docs 8080   # click the forwarded port to view
```

This is a local build in every sense that matters, except that it is not on your laptop. Free accounts include 60 core hours a month; a build costs a few minutes. Use it whenever a CI failure is not self explanatory, because a fifteen second edit and rebuild beats a five minute round trip.

To check without a full render:

```bash
python3 tools/build_snippets.py && python3 tools/check_project.py
```

### Building on your own machine

If you do have Quarto installed:

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
├── tools/build_snippets.py   script to snippet generator
├── tools/check_project.py    pre-flight validation, runs before Quarto
├── tools/build_site.sh       render both languages and assemble docs/
├── .devcontainer/            Codespaces setup, Quarto ready in the browser
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

#
---

## Editing the book

### From the web, no tooling

Every page carries **Edit this page** in the right margin. It opens the `.qmd`
in GitHub's web editor, and committing there triggers a rebuild. Three clicks
for a typo, no clone and no Codespace.

For anything larger than a sentence, press <kbd>.</kbd> on the repository page.
That opens `github.dev`, a full VS Code in the browser with the whole repo, no
container to start. Good for rewriting a section across several files. It
cannot run builds, so push and let CI check it.

When you want to see the result before pushing, open a Codespace and use the
Quarto extension's preview.

### Figures, maps and interactive widgets

Three separate things, kept separate on purpose.

| Kind | Made by | Contains satellite pixels |
|---|---|---|
| Diagrams in `images/` | `tools/figures/make_figures.py` | No, and captions say so |
| Maps in `images/map-*.png` | `notebooks/produce_maps.py` | Yes, from your own Earth Engine account |
| Widgets in `interactive/` | Hand written HTML and JS | No |

Regenerate all diagrams with `python3 tools/figures/make_figures.py`. Every
number the chapters quote from a figure, the GLCM entropy values, the nearest
neighbour distances, the confusion matrix percentages, is computed by that
script rather than asserted, so changing the script updates both the figure
and the claim.

Produce real maps with `notebooks/produce_maps.py`. It is the Python
equivalent of the JavaScript in `scripts/`, so a reader can compare their own
output against the book's.

Widgets live in `interactive/` and are copied into both language projects at
build time. Each detects the page language at runtime and labels itself, so
one file serves both editions. Include one with:

```markdown
{{< include ../interactive/spectral-explorer.qmd >}}
```

| Widget | Used in | What a reader does with it |
|---|---|---|
| `spectral-explorer` | Chapter 2 | Picks two land cover classes and an index, and sees whether that index separates them at all |
| `sensor-chooser` | Chapter 3 | Sets pixel size, revisit, cloud penetration and budget, and watches missions get ruled out until none are left |
| `composite-simulator` | Chapter 9 | Adds scenes to a cloud composite and sees where the holes are, with independent cloud against clustered cloud |
| `confusion-lab` | Chapter 17 | Types into a confusion matrix and watches overall accuracy and per class accuracy move apart |

Each one is a single self contained HTML block with no dependencies: no
framework, no CDN, no build step. The shared frame, the `.rs-widget` box, the
control row and the verdict panel, lives in `lms/lms.css`, so a widget's own
`<style>` block holds only what is specific to it. That split exists because
the second widget was written by copying the first and a chapter that
included the second without the first inherited none of its styling.

Bilingual text goes in `data-i18n-en` and `data-i18n-id` attributes, which the
widget's own script swaps on load. Strings generated in JavaScript switch on
`isID`. Keep the English in the markup as the fallback, so a widget with a
missing translation degrades to English rather than to an empty element.

`tools/check_project.py` fails the build if a chapter includes a widget that
does not exist, and reports, without failing, any widget included in one
language and not the other.

### Executed Python in the chapters

Six chapters compute their own figures and tables when the book renders, with
the jupyter engine declared by `jupyter: python3` in both `_quarto.yml` files:

| Chapter | What it computes |
|---|---|
| 2, physics | Reflectance curves, and the index separability table behind the chapter's central claim |
| 9, cloud masking | Clear pixel probability against scene count, and the scenes needed for 95 percent coverage |
| 12, band math | Every bounded index against every class pair, as a heatmap and a ranked table |
| 15, sampling | Olofsson sample sizes, and what proportional allocation does to a rare class |
| 17, accuracy | Overall accuracy, kappa, and per class producer's and user's accuracy |
| 21, time series | A harmonic fit on a series with a disturbance in it, and its residuals |

The point is not decoration. A number that is computed on the page cannot
drift away from the prose beside it, and three numbers in the chapters were
wrong before their arithmetic was put on the page: one rounding error, one
figure caption describing a different matrix, and one claim that skipped the
index that actually performed best.

Shared data and machinery live in **`booklib.py`** at the repository root,
copied into each language project by the build script alongside the other
shared assets. A chunk in a chapter should be short enough that a reader
reads it rather than scrolling past it, so anything longer than about fifteen
lines belongs in the library.

Two rules that are not negotiable, because breaking either makes the book
unbuildable by anybody but its author:

**Nothing touches the network at render time.** Every value is published,
synthetic or computed. A chapter that needed Earth Engine credentials to
render would break for the first person to fork this repository.

**Plotly figures go through `booklib.show()`.** Quarto's own Plotly path loads
a 2019 build of plotly.js through RequireJS. `show()` uses `to_html` instead,
which pins a current build and lets the chart be configured: no editing
toolbar, no screenshot button, responsive width. Tables go through
`booklib.table()` for the same kind of reason, so they inherit the book's CSS
rather than pandas' defaults.

Install the render dependencies with `pip install -r requirements.txt`. In CI
they are installed in the `build` job only, and `_freeze/` is cached across
runs, so a commit that touches only prose re-executes nothing.

One side effect worth knowing about: pages that execute Python carry Quarto's
jupyter HTML dependencies, which include RequireJS from cdnjs. It is
harmless, and it is why those twelve pages make one more third party request
than the rest.

### Runnable Python in the reader's browser

Twelve cells in the book have a **Run** button. They execute in the reader's
own tab through [Pyodide](https://pyodide.org), CPython compiled to
WebAssembly. There is no server, no account, no quota and no abuse surface,
and the reader can edit the code before running it.

Write one as a fenced div with an ordinary, non executable code block inside:

````markdown
::: {.py-live}
```python
print("this runs in the reader's browser")
```
:::
````

Note the fence is ```` ```python ````, not ```` ```{python} ````. The first is
a highlighted listing that `lms/pyodide-cell.js` turns into an editor; the
second executes at build time. A chapter often wants both: the executed
version makes the argument, the runnable version lets the reader push on it.

Rules that come from how it actually behaves:

- Keep the cell self contained. `booklib` does not exist in the browser.
- Prefer the standard library. `numpy`, `pandas` and `matplotlib` are
  available but each is a download the reader waits through; the packages
  fetched on first run are listed in `lms/config.js`.
- End with a comment suggesting what to change. A cell nobody edits is a
  listing with an extra button on it.
- `matplotlib` figures are captured and shown as images automatically.

Nothing downloads until a reader presses Run. If the CDN is unreachable or a
package fails to load, the cell says so once and pure Python keeps working;
with JavaScript off, the reader sees a normal highlighted code block.

### Adding images

Put files in `images/` at the repository root. They are copied into both
language projects at build time, so reference them the same way from either:

```markdown
![Annual composite over the Mahakam Delta.](../images/composite.png){#fig-composite}
```

Refer to it in prose as `@fig-composite` and Quarto numbers it and links to it.
`images/README.md` covers sizing, formats and how to keep pages from becoming
20 MB.

### Answers to exercises

Put them in a collapsed callout at the end of the chapter, so a reader has to
choose to look:

```markdown
::: {.callout-tip collapse="true"}
## Answers

**1.** ...
:::
```

`en/02-physics.qmd` has a worked example. Write the answers as teaching rather
than as a key: say why the wrong intuition is tempting, not just what the right
answer is.

### Open in Earth Engine buttons

Each JavaScript listing can carry a button that loads the script straight into
the Code Editor, ready to Run. One setup, then it applies to every listing
automatically.

1. Code Editor, Scripts panel, **New → Repository**. Name it something durable,
   for example `book`.
2. Add each file from `scripts/en/` as a script, keeping the filename without
   the `.js` extension.
3. Click the settings icon beside the repository, **Share**, tick
   **Anyone can read**.
4. Set `EE_REPO` near the top of `tools/build_snippets.py` to
   `users/<your-account>/book` and push.

The buttons appear above every JavaScript listing in both editions, labelled in
the reader's language. Leave `EE_REPO` empty to omit them.

Keeping the Earth Engine repository in step with `scripts/` is manual. The
alternative, a reader copying and pasting, already works and costs them ten
seconds, so do this when the scripts have settled rather than while they are
still changing.

## Callout conventions

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
| II. The platform | 5 to 7 | Written | **Written** |
| III. Analysis ready data | 8 to 11 | **Written** | **Written** |
| IV. Feature engineering | 12 to 15 | **Written** | **Written** |
| V. Machine learning | 16 to 18 | **Written** | **Written** |
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
| Questions reach you | Pre filled email to rifky.nhsp@gmail.com, or a Formspree endpoint | A table you read at `/en/instructor.html` |
| Cost | Nothing | Nothing, Supabase free tier |

Full setup is in **`lms/README-lms.md`**. The short version: create a Supabase project, run `lms/supabase-schema.sql`, paste the project URL and anon key into `lms/config.js`. The anon key is meant to be public; row level security is what protects the data.

### Files

```
lms/config.js            the only file you edit
lms/lms.js               engine: storage adapter, quizzes, progress, notes, questions
lms/lms.css              styling, light and dark, plus the shared widget frame
lms/visitors.js          reader counter
lms/pyodide-cell.js      Run buttons on .py-live code blocks
lms/supabase-schema.sql  tables and row level security for account mode
lms/README-lms.md        full setup guide
en/dashboard.qmd         reader progress dashboard
en/instructor.qmd        question inbox, instructor only
```

Anything added to `lms/` has to be listed in three places: the `<script>` tags
in both `_quarto.yml` files, and the copy line in `tools/build_site.sh`.
Forget the third and it works locally and 404s on the published site, so
`tools/check_project.py` fails the build if a script is loaded but not
copied.

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

Every numbered chapter in both editions now has one, 48 blocks and 182
questions in total. The appendices, the index, the dashboard and the
instructor page deliberately do not: a knowledge check on a glossary is
theatre.

`tools/check_project.py` parses every block and fails the build on invalid
JSON, a missing `id`, a duplicate `id` within a chapter, fewer than two
options, a missing `why`, or an `answer` index outside the options list. That
last one is the reason the check exists: it renders perfectly and then fails
silently in the reader's browser, and nobody reports it, they just stop
trusting the quizzes.

### The reader counter

A static site cannot count its own readers, so `lms/visitors.js` asks
[counterapi.dev](https://counterapi.dev), a free service that holds integers
and needs no account, for two numbers: total across the book and views on the
current page. They appear quietly at the foot of each chapter and on the
landing page.

Two things to be honest about, both stated in `lms/config.js`:

- It counts browsers, not people. One reader on a phone and a laptop is two,
  and a reader who clears site data is new again.
- It is somebody else's free service. If it disappears, or a reader blocks
  it, the badge hides itself and nothing else changes.

It counts one visit per browser per twelve hours, so reloading a chapter
while working through a script is one reader rather than eleven. No
identifier, referrer payload or analytics beacon goes with the request: what
the counter learns is that somebody, somewhere, opened a page.

Change `visitors.namespace` in `lms/config.js` if you fork this book,
otherwise your readers and mine land in the same bucket. Set
`visitors.provider` to `'none'`, or `features.visitors` to `false`, to switch
the badge off.

### Where questions go

`instructorEmail` in `lms/config.js`, currently `rifky.nhsp@gmail.com`, and
three routes are tried in order of how good the experience is: the Supabase
table in account mode, a Formspree endpoint if one is configured, and
otherwise a pre filled `mailto:` carrying the chapter title and URL.

Readers meet the invitation in three places: the floating button on every
page, a card at the end of every chapter, where a reader has just finished
and knows what they did not understand, and the landing page. Changing the
address means changing `lms/config.js`; the chapter card, the landing page
button and the instructor page all read from it or are checked against it by
the pre-flight checks.

### If the platform breaks

It cannot take the book down with it. `lms.js` wraps its startup in a catch, logs a warning and stops. Chapters still render, listings still copy, navigation still works.

---

## About PDF output

PDF is disabled, deliberately.

Two chapters carry mermaid diagrams. In HTML those render in the reader's browser through mermaid.js, which costs nothing at build time. For PDF, Quarto must rasterise them first, and that needs headless Chromium. On a runner without Chromium the step does not fail cleanly. It hangs, and the job spends its entire time budget on a single diagram.

To turn PDF back on, do both of these:

1. Restore the commented `pdf:` block at the bottom of `en/_quarto.yml` and `id/_quarto.yml`, and add `downloads: [pdf]` back under the `book:` key.
2. Add these to `.github/workflows/publish.yml` before the build step:

```yaml
      - uses: quarto-dev/quarto-actions/setup@v2
        with:
          tinytex: true
      - run: quarto install tool chromium --no-prompt
```

Expect the build to go from roughly four minutes to fifteen or more. Worth it if readers actually want a PDF; not worth it by default.

## Citation style

Citations use Pandoc's default, Chicago author-date. There is deliberately no `csl:` key.

The obvious thing to write is `csl: https://www.zotero.org/styles/apa`, and Pandoc will fetch that URL on every render. GitHub runners reset the connection often enough that builds fail on a stylesheet affecting nothing but the shape of a reference list. A build should not depend on a third party server being reachable.

If you want APA, vendor the file instead of fetching it:

1. Download `https://www.zotero.org/styles/apa` and save it as `apa.csl` in the repository root.
2. Add `apa.csl` to the `SHARED` array in `tools/build_site.sh`, and add `en/apa.csl` and `id/apa.csl` to `.gitignore`.
3. Add `csl: apa.csl` to both `_quarto.yml` files.

## When a build fails

The workflow has two jobs and which one failed tells you where to look.

**`check` failed.** A structural problem, named precisely with a file and line. Fix it and push again. Ten seconds, no Quarto involved.

**`build` failed.** Quarto rejected something the checks cannot see. Open a Codespace and run `bash tools/build_site.sh` there, where the edit and rebuild loop is seconds rather than minutes.

## Build times

A healthy run is three to six minutes. The workflow sets `timeout-minutes: 20`, because a job approaching twenty minutes is hung rather than slow, and a hung job silently consumes the whole billing budget.

## Licensing

Prose CC BY 4.0, code MIT. See `LICENSE-content.md`.
