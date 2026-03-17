-- Conversation memory
create table conversations (
  id         bigserial primary key,
  chat_id    text not null,
  role       text not null,
  content    text not null,
  created_at timestamptz default now()
);
create index on conversations(chat_id, created_at);

-- Tracks fetched and indexed content
create table content_cache (
  id            bigserial primary key,
  content_type  text not null,
  exam          text not null,
  title         text,
  source_url    text,
  year          int,
  subject       text,
  chroma_ids    text[],
  fetched_at    timestamptz default now()
);
create index on content_cache(exam, content_type);

-- Scheduled jobs per user
create table scheduled_jobs (
  id               bigserial primary key,
  chat_id          text not null,
  job_type         text not null,
  interval_minutes int not null,
  exam             text default 'HCS',
  subject          text default '',
  next_run_at      timestamptz not null,
  active           boolean default true,
  created_at       timestamptz default now()
);
create index on scheduled_jobs(active, next_run_at);

-- Quiz sessions per user
create table quiz_sessions (
  id             bigserial primary key,
  chat_id        text not null unique,
  exam           text,
  subject        text,
  question       text,
  options        jsonb,
  correct_answer text,
  explanation    text,
  score          int default 0,
  total          int default 0,
  active         boolean default true,
  created_at     timestamptz default now()
);
