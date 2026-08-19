# The learning platform layer

This book is a static site, and static sites cannot run code on a server. Everything below is built around that constraint rather than pretending it away.

## The two modes

| | Local mode | Account mode |
|---|---|---|
| Setup | None. Already working. | About twenty minutes |
| Sign in | A name, stored in the browser | Magic link to the reader's email |
| Progress | Saved in that browser only | Follows the reader across devices |
| Quiz scores | Same | Same |
| Notes | Same | Same |
| Questions reach you | Pre filled email, or a form endpoint | A table you read from the instructor page |
| Cost | Nothing | Nothing on Supabase's free tier |
| You can see who is learning | No | Yes |

Local mode is honest and adequate for a public self study book. Account mode is what you want if you are running cohorts, answering questions at volume, or need to know whether anyone actually finished Part III.

Switch between them by filling in two values in `lms/config.js`. Nothing else changes.

## What the reader gets, in both modes

**A reading progress bar** across the top of every chapter.

**Chapter completion.** A button at the end of each chapter, a tick beside finished chapters in the sidebar, and a course wide percentage above the table of contents.

**Knowledge checks.** Inline multiple choice, one question at a time, with an explanation after each answer that appears whether they were right or wrong. Scores are saved and shown on the dashboard.

**A private notepad** on every chapter, saved as they type.

**Ask a question.** A floating button on every page. The question carries the chapter and URL automatically, so nobody has to explain where they are.

**A dashboard** at `en/dashboard.html` and `id/dashboard.html` showing progress, quiz scores, notes and their question history, with export and reset.

## Enabling account mode

### 1. Create the project

Sign up at [supabase.com](https://supabase.com) and create a project. Any region near your readers.

### 2. Create the tables

Open the SQL editor and run `lms/supabase-schema.sql` in full. It creates two tables and the row level security policies that protect them.

### 3. Point the site at it

In the Supabase dashboard, go to **Settings → API** and copy the **Project URL** and the **anon public** key into `lms/config.js`:

```js
supabaseUrl: 'https://abcdefgh.supabase.co',
supabaseAnonKey: 'eyJhbGciOi...'
```

::: The anon key belongs in public code. That is what it is for. The row level security policies are what protect the data, not the secrecy of the key. Never put the `service_role` key in this file or anywhere in the repository.

### 4. Allow your site to sign people in

**Authentication → URL Configuration**. Set the **Site URL** to your published address, for example `https://rifkynauval.github.io/planetary-scale-cloud-gis/`, and add both language paths under **Redirect URLs**:

```
https://YOUR-SITE/en/*
https://YOUR-SITE/id/*
http://localhost:8080/*
```

The last one lets you test locally.

### 5. Check the email settings

**Authentication → Providers → Email** should have *Enable email provider* on and *Confirm email* on. Supabase's built in mailer is rate limited to a few messages an hour, which is fine for testing and not for a cohort. For real use, connect your own SMTP under **Project Settings → Auth → SMTP Settings**. A free Resend or Brevo account is enough.

### 6. Sign in as yourself once

Visit the site, sign in with `rifkynauvalhsp@gmail.com`, then open `en/instructor.html`. The policies in the schema recognise that address and unlock the question inbox. Any other signed in reader sees only their own questions.

## Getting notified about new questions

Account mode puts questions in a table, which is only useful if you know they arrived. Two routes.

**Webhook, no code.** Supabase dashboard, **Database → Webhooks**, create one on `lms_questions` for INSERT, point it at a Zapier, Make or n8n hook that emails you. Five minutes.

**SQL trigger.** The commented block at the bottom of `supabase-schema.sql` does the same thing with `pg_net`.

If neither appeals, stay in local mode with a Formspree endpoint and let the questions arrive as email. That is a perfectly reasonable choice and it is why the fallback exists.

## Writing a knowledge check

Quizzes are raw HTML blocks in a chapter, so they need no filter, no shortcode and no build step. Quarto passes them straight through.

````markdown
<script type="application/json" class="lms-quiz">
{
  "id": "ch02-signatures",
  "questions": [
    {
      "q": "What causes the near infrared plateau in a healthy leaf?",
      "options": [
        "Chlorophyll absorption",
        "Internal cell structure scattering the light",
        "Water content in the leaf",
        "Surface wax reflecting infrared"
      ],
      "answer": 1,
      "why": "Chlorophyll works in the red. The plateau comes from the spongy mesophyll, whose cell walls and air spaces scatter near infrared repeatedly until most of it exits."
    }
  ]
}
</script>
````

Rules that matter:

- `id` must be unique within the chapter. The storage key is chapter plus id.
- `answer` is a zero based index into `options`.
- `why` is shown after answering, right or wrong. Write it as teaching rather than as a verdict. A quiz where the explanation only appears on failure wastes the moment when the reader is most receptive.
- Three or four options. Two is a coin flip, five is padding.
- Put the check after the section it tests, not at the end of the chapter. Recall works better close to the material.

## Turning features off

`lms/config.js`, `features` block. Set any of them to `false`:

```js
features: {
  progress: true,
  quizzes: true,
  notes: true,
  questions: true,
  reading: false     // no scroll bar at the top
}
```

## What this is not

It is not Moodle. There are no enrolments, no cohorts, no grade book, no assignment submission, no certificates, no SCORM, no discussion forums.

It is the subset of an LMS that a self study technical book actually benefits from: know where you are, check that you understood, keep notes, and reach the author. Those four cover most of what readers of a book like this need, and each one that got left out is a maintenance burden that did not get created.

If you later need real enrolments and grading, the honest answer is to run actual Moodle or Canvas and link to these chapters from it, rather than growing this into something it was not designed to be.

## If the platform breaks

It cannot take the book down with it. `lms.js` wraps its whole startup in a catch, logs a warning and stops. The chapter still renders, the code listings still copy, the navigation still works. The book is the product; this layer is an enhancement.
