/* ===========================================================================
 * lms/config.js
 * ===========================================================================
 *
 * The only file you need to edit to configure the learning platform.
 *
 * The site works in two modes and switches automatically.
 *
 *   LOCAL MODE   (default, zero setup)
 *     supabaseUrl left empty. Progress, quiz scores and notes are stored in
 *     the reader's own browser. Questions open a pre filled email to you.
 *     Nothing is sent anywhere, nobody can see anyone else's data, and there
 *     is no account. Good enough for a public self study book.
 *
 *   ACCOUNT MODE (real accounts, about twenty minutes of setup)
 *     Fill in supabaseUrl and supabaseAnonKey. Readers sign in with a magic
 *     link sent to their email, progress follows them between devices, and
 *     questions land in a table you can read from the instructor page.
 *     Setup instructions are in lms/README-lms.md.
 *
 * The anon key below is safe to publish. It is designed to sit in public
 * client code, and row level security in supabase-schema.sql is what actually
 * protects the data. Never put a service_role key in this file.
 * =========================================================================== */

window.LMS_CONFIG = {

  // ---- Identity -----------------------------------------------------------
  courseId: 'planetary-scale-cloud-gis',
  instructorName: 'Rifky Nauval Hendrawan',
  instructorEmail: 'rifky.nhsp@gmail.com',

  // ---- Account mode. Leave both empty to stay in local mode. --------------
  supabaseUrl: '',
  supabaseAnonKey: '',

  // ---- Optional: a form endpoint for questions in local mode --------------
  // If you would rather questions arrive as form submissions than as emails
  // the reader has to send themselves, create a free endpoint at
  // https://formspree.io and paste it here. Leave empty to use mailto.
  formspreeEndpoint: '',

  // ---- Reader counter -----------------------------------------------------
  //
  // A static site cannot count its own readers, so this calls a third party
  // counter that does nothing but hold an integer. Two honest caveats:
  //
  //   1. It counts browsers, not people. One reader on a phone and a laptop
  //      is two. A reader who clears site data is new again.
  //   2. It is somebody else's free service. If it goes away or a reader
  //      blocks it, the badge hides itself and nothing else changes.
  //
  // provider: 'counterapi' uses https://counterapi.dev, which needs no
  // account and no key. Set provider to 'none' to switch the badge off.
  //
  // Change `namespace` if you fork this book, otherwise your readers and
  // mine land in the same bucket.
  visitors: {
    enabled: true,
    provider: 'counterapi',
    namespace: 'planetary-scale-cloud-gis',

    // Count one visit per browser per this many hours. Reloading a chapter
    // eleven times while debugging a script is one reader, not eleven.
    dedupeHours: 12
  },

  // ---- Runnable Python in the browser -------------------------------------
  //
  // Code blocks marked `.py-live` in a chapter get a Run button. The first
  // click downloads Pyodide, a CPython build compiled to WebAssembly, from
  // the CDN below, roughly 10 MB, cached by the browser afterwards. Nothing
  // downloads until a reader actually presses Run.
  //
  // Everything runs in the reader's own tab. There is no server, no account
  // and no quota, and the reader can edit the code before running it.
  pyodide: {
    enabled: true,
    indexUrl: 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/',

    // Packages fetched on first run. Keep this list short: each one is a
    // download the reader waits through.
    packages: ['numpy', 'matplotlib', 'pandas']
  },

  // ---- Feature switches ---------------------------------------------------
  features: {
    progress: true,   // completion tracking and progress bars
    quizzes: true,    // inline knowledge checks
    notes: true,      // per chapter private notepad
    questions: true,  // ask the instructor
    reading: true,    // scroll progress bar at the top of each page
    visitors: true,   // reader counter in the page footer
    pyodide: true     // Run buttons on .py-live code blocks
  }
};
