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
  instructorEmail: 'rifkynauvalhsp@gmail.com',

  // ---- Account mode. Leave both empty to stay in local mode. --------------
  supabaseUrl: '',
  supabaseAnonKey: '',

  // ---- Optional: a form endpoint for questions in local mode --------------
  // If you would rather questions arrive as form submissions than as emails
  // the reader has to send themselves, create a free endpoint at
  // https://formspree.io and paste it here. Leave empty to use mailto.
  formspreeEndpoint: '',

  // ---- Feature switches ---------------------------------------------------
  features: {
    progress: true,   // completion tracking and progress bars
    quizzes: true,    // inline knowledge checks
    notes: true,      // per chapter private notepad
    questions: true,  // ask the instructor
    reading: true     // scroll progress bar at the top of each page
  }
};
