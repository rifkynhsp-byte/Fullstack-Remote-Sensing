/* ===========================================================================
 * lms/pyodide-cell.js
 * ===========================================================================
 *
 * Runnable, editable Python inside a static book.
 *
 * Why this exists
 * ---------------
 * The book renders Python at build time, so a reader sees real output rather
 * than a claim about output. What that does not give them is the ability to
 * change a number and look again, which is where the understanding actually
 * happens. A hosted kernel would give them that and would also give the
 * author a server, a quota and an abuse surface.
 *
 * Pyodide is CPython compiled to WebAssembly. It runs in the reader's own
 * tab. There is no server, nothing to pay for, nothing to rate limit, and
 * nothing a reader can do to it that affects anybody else.
 *
 * The cost is honest and worth stating: the runtime is about 10 MB, plus each
 * package. So nothing is downloaded until a reader presses Run, the progress
 * is shown while it happens, and the browser caches it for every later cell.
 *
 * Markup it looks for
 * -------------------
 * Any element with class `py-live` containing a code block. In a chapter:
 *
 *     ::: {.py-live}
 *     ```python
 *     print("hello")
 *     ```
 *     :::
 *
 * Quarto highlights the code as usual; this script adds the editor, the Run
 * button and the output pane. With JavaScript off, or if the CDN is
 * unreachable, the reader still sees a normal highlighted code block, which
 * is exactly what they would have seen without any of this.
 *
 * Optional attributes on the div:
 *     data-autorun="true"   run as soon as the runtime is ready
 *     data-packages="numpy" extra packages for this cell only
 * =========================================================================== */

(function () {
  'use strict';

  var CFG = (window.LMS_CONFIG || {});
  var PY = CFG.pyodide || {};
  var LANG = (document.documentElement.lang || 'en').slice(0, 2) === 'id' ? 'id' : 'en';

  var T = {
    en: {
      run: 'Run', running: 'Running', reset: 'Reset', edit: 'Editable',
      loading: 'Starting Python in your browser',
      loadingNote: 'First run downloads the runtime, about 10 MB. Cached afterwards.',
      ready: 'Ready', output: 'Output', noOutput: 'Ran without printing anything.',
      failed: 'Python could not start in this browser. The code above still',
      failedLink: 'runs anywhere you have Python installed.',
      error: 'Error', hint: 'Change a value and run it again.'
    },
    id: {
      run: 'Jalankan', running: 'Menjalankan', reset: 'Atur ulang', edit: 'Dapat diubah',
      loading: 'Menyalakan Python di peramban Anda',
      loadingNote: 'Jalan pertama mengunduh runtime, sekitar 10 MB. Setelah itu tersimpan di cache.',
      ready: 'Siap', output: 'Keluaran', noOutput: 'Berjalan tanpa mencetak apa pun.',
      failed: 'Python tidak dapat dijalankan di peramban ini. Kode di atas tetap',
      failedLink: 'bisa dijalankan di mana pun Python terpasang.',
      error: 'Galat', hint: 'Ubah sebuah nilai lalu jalankan lagi.'
    }
  }[LANG];

  /* ------------------------------------------------------------------ */
  /* The runtime, loaded once and shared by every cell on the page       */
  /* ------------------------------------------------------------------ */

  var runtime = null;          // Promise<pyodide>, created on first Run
  var listeners = [];          // progress messages while it loads

  function progress(message) {
    listeners.forEach(function (fn) { try { fn(message); } catch (e) {} });
  }

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = src;
      s.onload = resolve;
      s.onerror = function () { reject(new Error('could not load ' + src)); };
      document.head.appendChild(s);
    });
  }

  function getRuntime(extraPackages) {
    if (!runtime) {
      var indexUrl = PY.indexUrl || 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/';
      progress(T.loading);
      runtime = loadScript(indexUrl + 'pyodide.js')
        .then(function () {
          return window.loadPyodide({ indexURL: indexUrl });
        })
        .then(function (py) {
          // Each package is loaded on its own and a failure is survivable. A
          // reader behind a proxy that blocks one wheel should still get a
          // working cell for code that does not need it, rather than a dead
          // Run button on every cell in the book.
          var packages = (PY.packages || []).slice();
          if (!packages.length) return py;
          progress(T.loading + ': ' + packages.join(', '));
          return packages.reduce(function (chain, name) {
            return chain.then(function () {
              return py.loadPackage(name).catch(function (err) {
                console.warn('py-live: package ' + name + ' unavailable:', err);
              });
            });
          }, Promise.resolve()).then(function () { return py; });
        })
        .then(function (py) {
          // Matplotlib must not try to open a window, and Pyodide's canvas
          // backend needs a target element we do not have. Rendering to a PNG
          // buffer and handing back base64 works in every browser.
          //
          // The whole shim is optional: if matplotlib did not load, figure
          // collection returns nothing and text output still works.
          return py.runPythonAsync([
            'import io, base64',
            'try:',
            '    import matplotlib',
            '    matplotlib.use("AGG")',
            '    import matplotlib.pyplot as plt',
            '    def _lms_figures():',
            '        out = []',
            '        for num in plt.get_fignums():',
            '            buf = io.BytesIO()',
            '            plt.figure(num).savefig(buf, format="png", dpi=140, bbox_inches="tight")',
            '            out.append(base64.b64encode(buf.getvalue()).decode())',
            '        plt.close("all")',
            '        return out',
            'except Exception:',
            '    def _lms_figures():',
            '        return []'
          ].join('\n')).then(function () { return py; });
        })
        .catch(function (err) {
          runtime = null;                 // let a later click try again
          throw err;
        });
    }

    if (!extraPackages || !extraPackages.length) return runtime;
    return runtime.then(function (py) {
      progress(T.loading + ': ' + extraPackages.join(', '));
      return py.loadPackage(extraPackages).then(function () { return py; });
    });
  }

  /* ------------------------------------------------------------------ */
  /* One cell                                                            */
  /* ------------------------------------------------------------------ */

  function wire(host, order) {
    var codeEl = host.querySelector('code');
    if (!codeEl) return;

    var original = codeEl.textContent.replace(/\n$/, '');
    var extra = (host.getAttribute('data-packages') || '')
      .split(/[,\s]+/).filter(Boolean);

    host.classList.add('pyc');
    host.setAttribute('data-pyc-index', String(order));

    // The highlighted block becomes the editor. contenteditable on the
    // existing <code> keeps Quarto's highlighting visible while typing,
    // which a <textarea> would throw away.
    codeEl.setAttribute('contenteditable', 'plaintext-only');
    codeEl.setAttribute('spellcheck', 'false');
    codeEl.classList.add('pyc-code');

    var bar = document.createElement('div');
    bar.className = 'pyc-bar';

    var runBtn = document.createElement('button');
    runBtn.className = 'pyc-run';
    runBtn.type = 'button';
    runBtn.innerHTML = '<span class="pyc-run-glyph" aria-hidden="true">▶</span>' +
                       '<span class="pyc-run-text">' + T.run + '</span>';

    var resetBtn = document.createElement('button');
    resetBtn.className = 'pyc-reset';
    resetBtn.type = 'button';
    resetBtn.textContent = T.reset;
    resetBtn.hidden = true;

    var status = document.createElement('span');
    status.className = 'pyc-status';
    status.textContent = T.edit;

    bar.appendChild(runBtn);
    bar.appendChild(resetBtn);
    bar.appendChild(status);
    host.appendChild(bar);

    var out = document.createElement('div');
    out.className = 'pyc-out';
    out.hidden = true;
    host.appendChild(out);

    listeners.push(function (message) {
      if (runBtn.disabled) status.textContent = message;
    });

    codeEl.addEventListener('input', function () {
      resetBtn.hidden = codeEl.textContent.replace(/\n$/, '') === original;
    });

    // Enter inside the editor must not submit anything, and Ctrl/Cmd+Enter
    // is the run shortcut every notebook user already has in their fingers.
    codeEl.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        run();
      }
    });

    resetBtn.addEventListener('click', function () {
      codeEl.textContent = original;
      resetBtn.hidden = true;
      out.hidden = true;
      out.innerHTML = '';
      status.textContent = T.edit;
    });

    runBtn.addEventListener('click', run);

    function show(kind, nodes) {
      out.hidden = false;
      out.className = 'pyc-out pyc-out-' + kind;
      out.innerHTML = '';
      nodes.forEach(function (n) { out.appendChild(n); });
    }

    function text(cls, value) {
      var n = document.createElement(cls === 'pre' ? 'pre' : 'p');
      n.className = 'pyc-' + cls;
      n.textContent = value;
      return n;
    }

    function run() {
      var source = codeEl.textContent;
      runBtn.disabled = true;
      runBtn.classList.add('is-busy');
      status.textContent = T.running;

      var note = document.createElement('p');
      note.className = 'pyc-note';
      note.textContent = T.loadingNote;
      show('busy', [text('pre', T.running + '…'), note]);

      getRuntime(extra)
        .then(function (py) {
          status.textContent = T.running;

          // stdout and stderr are captured rather than left to the console,
          // and the traceback is shown to the reader, because a traceback is
          // the most useful output a teaching cell can produce.
          py.runPython([
            'import sys, io',
            '_lms_stdout = io.StringIO()',
            '_lms_stderr = io.StringIO()',
            'sys.stdout = _lms_stdout',
            'sys.stderr = _lms_stderr'
          ].join('\n'));

          return py.runPythonAsync(source)
            .then(function (value) { return { py: py, value: value, error: null }; })
            .catch(function (err) { return { py: py, value: null, error: err }; });
        })
        .then(function (r) {
          var py = r.py;
          var stdout = py.runPython('_lms_stdout.getvalue()');
          var stderr = py.runPython('_lms_stderr.getvalue()');
          py.runPython('sys.stdout = sys.__stdout__\nsys.stderr = sys.__stderr__');

          var figures = [];
          try {
            figures = py.runPython('_lms_figures()').toJs();
          } catch (e) {
            console.warn('py-live: could not collect figures:', e);
          }

          var nodes = [];
          if (r.error) {
            nodes.push(text('pre', String(r.error.message || r.error)));
          } else {
            if (stdout) nodes.push(text('pre', stdout.replace(/\n$/, '')));
            if (stderr) nodes.push(text('pre', stderr.replace(/\n$/, '')));
            // A trailing expression, the way a notebook cell shows its value.
            if (!stdout && !figures.length && r.value !== undefined && r.value !== null) {
              nodes.push(text('pre', String(r.value)));
            }
            figures.forEach(function (b64) {
              var img = document.createElement('img');
              img.className = 'pyc-fig';
              img.alt = T.output;
              img.src = 'data:image/png;base64,' + b64;
              nodes.push(img);
            });
            if (!nodes.length) nodes.push(text('note', T.noOutput));
            else nodes.push(text('note', T.hint));
          }

          show(r.error ? 'error' : 'ok', nodes);
          status.textContent = r.error ? T.error : T.ready;
        })
        .catch(function (err) {
          // The runtime itself did not load. Say so once, plainly, and leave
          // the code block readable.
          var p = document.createElement('p');
          p.className = 'pyc-note';
          p.textContent = T.failed + ' ' + T.failedLink;
          show('error', [p, text('pre', String(err.message || err))]);
          status.textContent = T.error;
        })
        .then(function () {
          runBtn.disabled = false;
          runBtn.classList.remove('is-busy');
        });
    }

    if (host.getAttribute('data-autorun') === 'true') run();
  }

  /* ------------------------------------------------------------------ */
  /* Start                                                               */
  /* ------------------------------------------------------------------ */

  function start() {
    if (PY.enabled === false) return;
    var cells = document.querySelectorAll('.py-live');
    Array.prototype.forEach.call(cells, function (host, i) {
      try { wire(host, i); } catch (e) { console.warn('py-live cell skipped:', e); }
    });
  }

  window.LMS_PYODIDE = { start: start };
})();
