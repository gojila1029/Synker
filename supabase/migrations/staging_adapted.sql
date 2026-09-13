-- STAGING ONLY — never apply to production Supabase
-- Combines migrations 001 + 002 + 003 adapted for Railway postgres:16
--
-- Changes from production:
--   - vector extension and notes_embeddings OMITTED (pgvector unavailable)
--   - public.users: no FK to auth.users (Supabase auth schema absent)
--   - Auth sync trigger and function OMITTED
--   - All user_id FK constraints to public.users DROPPED (plain uuid NOT NULL)
--     so Supabase JWT sub values work without a matching public.users row
--   - All ENABLE ROW LEVEL SECURITY and CREATE POLICY OMITTED
--   - 002 heartbeat columns and 003 vault content columns merged in-place
--
-- Apply once:
--   railway run --environment staging psql $DATABASE_URL -f supabase/migrations/staging_adapted.sql

-- ── Extensions ────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ── Users ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.users (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  email       text        NOT NULL,
  full_name   text,
  avatar_url  text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

-- ── Teams ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.teams (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text        NOT NULL,
  tier        text        NOT NULL DEFAULT 'single' CHECK (tier IN ('single', 'small', 'larger')),
  owner_id    uuid        NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.team_members (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  team_id     uuid        NOT NULL REFERENCES public.teams(id) ON DELETE CASCADE,
  user_id     uuid        NOT NULL,
  role        text        NOT NULL DEFAULT 'viewer' CHECK (role IN ('admin', 'editor', 'viewer')),
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (team_id, user_id)
);

-- ── Topics ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.topics (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid        NOT NULL,
  label       text        NOT NULL,
  color       text        NOT NULL DEFAULT '#3b82f6',
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- ── Sources ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.sources (
  id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid        NOT NULL,
  topic_id      uuid        REFERENCES public.topics(id) ON DELETE SET NULL,
  type          text        NOT NULL CHECK (type IN ('youtube', 'web', 'pdf', 'local')),
  source_scope  text        NOT NULL DEFAULT 'direct_resource'
                            CHECK (source_scope IN ('direct_resource', 'discovery_provider')),
  title         text        NOT NULL DEFAULT '',
  url           text        NOT NULL DEFAULT '',
  status        text        NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'processing', 'done', 'failed')),
  schedule      text,
  added_at      timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

-- ── Source extractions (004 source_extractions, staging-adapted: no RLS,
--    no FK to auth.users, matching this file's convention) ────────────────────
CREATE TABLE IF NOT EXISTS public.source_extractions (
  id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id     uuid        NOT NULL REFERENCES public.sources(id) ON DELETE CASCADE,
  user_id       uuid        NOT NULL,
  text          text        NOT NULL,
  title         text,
  author        text,
  published_at  timestamptz,
  timestamps    jsonb,
  word_count    int         NOT NULL DEFAULT 0,
  extracted_at  timestamptz NOT NULL DEFAULT now()
);

-- ── Candidates ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.candidates (
  id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           uuid        NOT NULL,
  source_id         uuid        REFERENCES public.sources(id) ON DELETE SET NULL,
  topic_id          uuid        REFERENCES public.topics(id) ON DELETE SET NULL,
  title             text        NOT NULL,
  source_info       text        NOT NULL DEFAULT '',
  domain            text        NOT NULL DEFAULT '',
  published_at      timestamptz,
  recommendation    text        NOT NULL DEFAULT 'review' CHECK (recommendation IN ('process', 'merge', 'skip', 'review')),
  quality_score     float       NOT NULL DEFAULT 0,
  confidence_score  float       NOT NULL DEFAULT 0,
  duplicate_score   float       NOT NULL DEFAULT 0,
  expected_notes    int         NOT NULL DEFAULT 0,
  estimated_tokens  int         NOT NULL DEFAULT 0,
  summary           text        NOT NULL DEFAULT '',
  extracted_topics  text[]      NOT NULL DEFAULT '{}',
  status            text        NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);

-- ── Jobs (002 heartbeat columns included) ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.jobs (
  id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          uuid        NOT NULL,
  source_id        uuid        REFERENCES public.sources(id) ON DELETE SET NULL,
  candidate_id     uuid        REFERENCES public.candidates(id) ON DELETE SET NULL,
  source_title     text        NOT NULL DEFAULT '',
  type             text        NOT NULL CHECK (type IN ('Extraction','Transcription','Analysis','PII Check','Note Gen','Verification','Graphify Sync','Cleanup')),
  status           text        NOT NULL DEFAULT 'queued' CHECK (status IN ('running','queued','completed','failed')),
  progress         int         NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
  error            text,
  error_code       text,
  artifact_path    text,
  started_at       timestamptz NOT NULL DEFAULT now(),
  finished_at      timestamptz,
  duration_seconds int,
  heartbeat_at     timestamptz,
  claimed_by       text
);

-- ── Notes ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.notes (
  id                   uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id              uuid        NOT NULL,
  candidate_id         uuid        REFERENCES public.candidates(id) ON DELETE SET NULL,
  topic_id             uuid        REFERENCES public.topics(id) ON DELETE SET NULL,
  source_id            uuid        REFERENCES public.sources(id) ON DELETE SET NULL,
  title                text        NOT NULL,
  source               text        NOT NULL DEFAULT '',
  ai_action            text        NOT NULL DEFAULT 'created' CHECK (ai_action IN ('created','merged','updated','skipped')),
  quality_score        float       NOT NULL DEFAULT 0,
  has_duplicate        bool        NOT NULL DEFAULT false,
  similar_to           uuid        REFERENCES public.notes(id) ON DELETE SET NULL,
  content              text        NOT NULL DEFAULT '',
  frontmatter          jsonb       NOT NULL DEFAULT '{}',
  citations            text[]      NOT NULL DEFAULT '{}',
  wiki_links           text[]      NOT NULL DEFAULT '{}',
  similarity_reasoning text        NOT NULL DEFAULT '',
  generated_at         timestamptz NOT NULL DEFAULT now(),
  approved_at          timestamptz,
  status               text        NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected'))
);

-- notes_embeddings OMITTED — requires pgvector (not bundled in postgres:16)

-- ── Vault files (003 content + frontmatter columns included) ──────────────────
CREATE TABLE IF NOT EXISTS public.vault_files (
  id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         uuid        NOT NULL,
  note_id         uuid        REFERENCES public.notes(id) ON DELETE SET NULL,
  path            text        NOT NULL,
  last_modified   timestamptz NOT NULL DEFAULT now(),
  word_count      int         NOT NULL DEFAULT 0,
  backlinks       int         NOT NULL DEFAULT 0,
  graph_node_type text        NOT NULL DEFAULT 'note',
  cloud_safe      bool        NOT NULL DEFAULT true,
  content         text,
  frontmatter     jsonb       NOT NULL DEFAULT '{}',
  UNIQUE (user_id, path)
);

-- ── User settings ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.user_settings (
  user_id       uuid        PRIMARY KEY,
  vault_path    text        NOT NULL DEFAULT '',
  vault_name    text        NOT NULL DEFAULT 'My Vault',
  ai_providers  jsonb       NOT NULL DEFAULT '{"claudeKey":"","openaiKey":"","ollamaUrl":"","fallbackOrder":["claude","openai"]}',
  privacy       jsonb       NOT NULL DEFAULT '{"piiMode":"regex","blockInsuranceData":false,"cloudBlockList":[]}',
  discovery     jsonb       NOT NULL DEFAULT '{"defaultInterval":3600,"youtubeInterval":3600,"webInterval":86400,"pdfInterval":0,"localDebounce":300}',
  cleanup       jsonb       NOT NULL DEFAULT '{"youtube":"keep","web":"keep","pdf":"keep","local":"keep"}',
  notifications jsonb       NOT NULL DEFAULT '{"desktop":false,"inApp":true,"email":false,"emailProvider":"resend","emailAddress":""}',
  team_tier     text        NOT NULL DEFAULT 'single' CHECK (team_tier IN ('single','small','larger')),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

-- ── Processing log ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.processing_log (
  id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid        NOT NULL,
  entity_type  text        NOT NULL,
  entity_id    uuid        NOT NULL,
  action       text        NOT NULL,
  details      jsonb       NOT NULL DEFAULT '{}',
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_sources_user       ON public.sources(user_id);
CREATE INDEX IF NOT EXISTS idx_source_extractions_source ON public.source_extractions(source_id);
CREATE INDEX IF NOT EXISTS idx_source_extractions_user   ON public.source_extractions(user_id);
CREATE INDEX IF NOT EXISTS idx_candidates_user    ON public.candidates(user_id);
CREATE INDEX IF NOT EXISTS idx_candidates_status  ON public.candidates(status);
CREATE INDEX IF NOT EXISTS idx_jobs_user          ON public.jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status        ON public.jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_claim         ON public.jobs(status, started_at);
CREATE INDEX IF NOT EXISTS idx_notes_user         ON public.notes(user_id);
CREATE INDEX IF NOT EXISTS idx_notes_status       ON public.notes(status);
CREATE INDEX IF NOT EXISTS idx_vault_files_user   ON public.vault_files(user_id);
CREATE INDEX IF NOT EXISTS idx_log_entity         ON public.processing_log(entity_type, entity_id);
