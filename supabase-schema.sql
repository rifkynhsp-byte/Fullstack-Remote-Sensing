-- ===========================================================================
-- lms/supabase-schema.sql
-- ===========================================================================
--
-- Run this once in the Supabase SQL editor to enable account mode.
--
-- Two tables carry everything:
--
--   lms_state      progress, quiz scores and notes, as a key value store
--   lms_questions  questions from readers and your replies
--
-- Row level security is what makes the public anon key safe to publish. Every
-- policy below is written so a reader can only ever touch their own rows, and
-- the instructor account is the only one that can read everybody's questions.
--
-- Replace the instructor email in the two policies at the bottom if it ever
-- changes.
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- State: progress, quiz results, notes
-- ---------------------------------------------------------------------------
-- A key value shape rather than three tables. Progress, quiz and notes have
-- different payloads but identical access rules and identical lifecycle, so
-- splitting them would triple the policy surface for no benefit.

create table if not exists public.lms_state (
  id          bigint generated always as identity primary key,
  user_id     uuid not null references auth.users (id) on delete cascade,
  course_id   text not null,
  bucket      text not null check (bucket in ('progress', 'quiz', 'notes')),
  key         text not null,
  value       jsonb,
  updated_at  timestamptz not null default now(),
  unique (user_id, course_id, bucket, key)
);

create index if not exists lms_state_lookup
  on public.lms_state (user_id, course_id, bucket);

alter table public.lms_state enable row level security;

-- A reader sees and writes only their own rows. auth.uid() is the id of the
-- signed in user, taken from the JWT, so this cannot be forged from the client.
drop policy if exists "own state read" on public.lms_state;
create policy "own state read" on public.lms_state
  for select using (auth.uid() = user_id);

drop policy if exists "own state write" on public.lms_state;
create policy "own state write" on public.lms_state
  for insert with check (auth.uid() = user_id);

drop policy if exists "own state update" on public.lms_state;
create policy "own state update" on public.lms_state
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "own state delete" on public.lms_state;
create policy "own state delete" on public.lms_state
  for delete using (auth.uid() = user_id);


-- ---------------------------------------------------------------------------
-- Questions
-- ---------------------------------------------------------------------------
-- user_id is nullable on purpose: a reader who has not signed in can still
-- ask, and the email they type is how the reply reaches them.

create table if not exists public.lms_questions (
  id           bigint generated always as identity primary key,
  course_id    text not null,
  user_id      uuid references auth.users (id) on delete set null,
  asker_name   text,
  asker_email  text not null,
  page_id      text,
  page_title   text,
  page_url     text,
  lang         text default 'en',
  body         text not null,
  answer       text,
  answered_at  timestamptz,
  created_at   timestamptz not null default now()
);

create index if not exists lms_questions_course
  on public.lms_questions (course_id, created_at desc);

alter table public.lms_questions enable row level security;

-- Anyone, signed in or not, may ask.
drop policy if exists "anyone can ask" on public.lms_questions;
create policy "anyone can ask" on public.lms_questions
  for insert with check (true);

-- A signed in reader sees their own questions and the replies to them.
drop policy if exists "own questions read" on public.lms_questions;
create policy "own questions read" on public.lms_questions
  for select using (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- Instructor access
-- ---------------------------------------------------------------------------
-- Identified by email rather than by a role table, because there is exactly
-- one instructor. If that ever changes, replace these two policies with a
-- lookup against an instructors table.

drop policy if exists "instructor reads all questions" on public.lms_questions;
create policy "instructor reads all questions" on public.lms_questions
  for select using (
    auth.jwt() ->> 'email' = 'rifkynauvalhsp@gmail.com'
  );

drop policy if exists "instructor answers questions" on public.lms_questions;
create policy "instructor answers questions" on public.lms_questions
  for update using (
    auth.jwt() ->> 'email' = 'rifkynauvalhsp@gmail.com'
  ) with check (
    auth.jwt() ->> 'email' = 'rifkynauvalhsp@gmail.com'
  );


-- ---------------------------------------------------------------------------
-- Optional: get an email whenever a question arrives
-- ---------------------------------------------------------------------------
-- Without this you have to open the instructor page to notice a new question.
-- Supabase Database Webhooks are the simplest route and need no SQL: in the
-- dashboard, go to Database, then Webhooks, create one on lms_questions for
-- INSERT, and point it at a Zapier, Make or n8n hook that emails you.
--
-- If you would rather do it in SQL, enable the pg_net extension and uncomment
-- the trigger below, replacing the endpoint with your own.
--
-- create extension if not exists pg_net;
--
-- create or replace function public.notify_new_question()
-- returns trigger
-- language plpgsql
-- security definer
-- as $$
-- begin
--   perform net.http_post(
--     url     := 'https://YOUR-WEBHOOK-ENDPOINT',
--     headers := '{"Content-Type": "application/json"}'::jsonb,
--     body    := jsonb_build_object(
--                  'from',    new.asker_email,
--                  'chapter', new.page_title,
--                  'url',     new.page_url,
--                  'body',    new.body
--                )
--   );
--   return new;
-- end;
-- $$;
--
-- drop trigger if exists on_new_question on public.lms_questions;
-- create trigger on_new_question
--   after insert on public.lms_questions
--   for each row execute function public.notify_new_question();
