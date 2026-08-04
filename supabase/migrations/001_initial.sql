-- Synker Phase 0 — initial schema
-- Run with: supabase db push

-- Extensions
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

-- ── Users ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.users (
  id          uuid        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email       text        NOT NULL,
  full_name   text,
  avatar_url  text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

-- Sync trigger: auth.users → public.users on sign-up
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  INSERT INTO public.users (id, email, full_name, avatar_url)
  VALUES (
    NEW.id,
    NEW.email,
    NEW.raw_user_meta_data->>'full_name',
    NEW.raw_user_meta_data->>'avatar_url'
  )
  ON CONFLICT (id) DO UPDATE SET
    email       = EXCLUDED.email,
    full_name   = EXCLUDED.full_name,
    avatar_url  = EXCLUDED.avatar_url,
    updated_at  = now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ── Teams ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.teams (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text        NOT NULL,
  tier        text        NOT NULL DEFAULT 'single' CHECK (tier IN ('single', 'small', 'larger')),
  owner_id    uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.team_members (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  team_id     uuid        NOT NULL REFERENCES public.teams(id) ON DELETE CASCADE,
  user_id     uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  role        text        NOT NULL DEFAULT 'viewer' CHECK (role IN ('admin', 'editor', 'viewer')),
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (team_id, user_id)
);

-- ── Topics ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.topics (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  label       text        NOT NULL,
  color       text        NOT NULL DEFAULT '#3b82f6',
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- ── Sources ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.sources (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  topic_id    uuid        REFERENCES public.topics(id) ON DELETE SET NULL,
  type        text        NOT NULL CHECK (type IN ('youtube', 'web', 'pdf', 'local')),
  title       text        NOT NULL DEFAULT '',
  url         text        NOT NULL DEFAULT '',
  status      text        NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'processing', 'done', 'failed')),
  schedule    text,
  added_at    timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

-- ── Candidates ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.candidates (
  id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
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

-- ── Jobs ──────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.jobs (
  id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  source_id        uuid        REFERENCES public.sources(id) ON DELETE SET NULL,
  candidate_id     uuid        REFERENCES public.candidates(id) ON DELETE SET NULL,
  source_title     text        NOT NULL DEFAULT '',
  type             text        NOT NULL CHECK (type IN ('Extraction','Transcription','Analysis','PII Check','Note Gen','Verification','Graphify Sync','Cleanup')),
  status           text        NOT NULL DEFAULT 'queued' CHECK (status IN ('running','queued','completed','failed')),
  progress         int         NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
  error            text,
  artifact_path    text,
  started_at       timestamptz NOT NULL DEFAULT now(),
  finished_at      timestamptz,
  duration_seconds int
);

-- ── Notes ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.notes (
  id                   uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id              uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  candidate_id         uuid        REFERENCES public.candidates(id) ON DELETE SET NULL,
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

-- Note embeddings — empty until Phase 3; vector(1536) matches text-embedding-3-small
CREATE TABLE IF NOT EXISTS public.notes_embeddings (
  note_id    uuid        PRIMARY KEY REFERENCES public.notes(id) ON DELETE CASCADE,
  embedding  vector(1536),
  model      text        NOT NULL DEFAULT 'text-embedding-3-small',
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ── Vault files ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.vault_files (
  id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  note_id         uuid        REFERENCES public.notes(id) ON DELETE SET NULL,
  path            text        NOT NULL,
  last_modified   timestamptz NOT NULL DEFAULT now(),
  word_count      int         NOT NULL DEFAULT 0,
  backlinks       int         NOT NULL DEFAULT 0,
  graph_node_type text        NOT NULL DEFAULT 'note',
  cloud_safe      bool        NOT NULL DEFAULT true,
  UNIQUE (user_id, path)
);

-- ── User settings ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.user_settings (
  user_id       uuid        PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
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
  user_id      uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  entity_type  text        NOT NULL,
  entity_id    uuid        NOT NULL,
  action       text        NOT NULL,
  details      jsonb       NOT NULL DEFAULT '{}',
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- ── Row Level Security ────────────────────────────────────────────────────────
ALTER TABLE public.users          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.teams          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.team_members   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.topics         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sources        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.candidates     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.jobs           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notes          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notes_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vault_files    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_settings  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.processing_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY users_own          ON public.users          USING (id = auth.uid());
CREATE POLICY teams_owner        ON public.teams          USING (owner_id = auth.uid());
CREATE POLICY team_members_own   ON public.team_members   USING (user_id = auth.uid());
CREATE POLICY topics_own         ON public.topics         USING (user_id = auth.uid());
CREATE POLICY sources_own        ON public.sources        USING (user_id = auth.uid());
CREATE POLICY candidates_own     ON public.candidates     USING (user_id = auth.uid());
CREATE POLICY jobs_own           ON public.jobs           USING (user_id = auth.uid());
CREATE POLICY notes_own          ON public.notes          USING (user_id = auth.uid());
CREATE POLICY vault_files_own    ON public.vault_files    USING (user_id = auth.uid());
CREATE POLICY user_settings_own  ON public.user_settings  USING (user_id = auth.uid());
CREATE POLICY processing_log_own ON public.processing_log USING (user_id = auth.uid());
CREATE POLICY notes_embeddings_own ON public.notes_embeddings
  USING (note_id IN (SELECT id FROM public.notes WHERE user_id = auth.uid()));

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_sources_user       ON public.sources(user_id);
CREATE INDEX IF NOT EXISTS idx_candidates_user    ON public.candidates(user_id);
CREATE INDEX IF NOT EXISTS idx_candidates_status  ON public.candidates(status);
CREATE INDEX IF NOT EXISTS idx_jobs_user          ON public.jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status        ON public.jobs(status);
CREATE INDEX IF NOT EXISTS idx_notes_user         ON public.notes(user_id);
CREATE INDEX IF NOT EXISTS idx_notes_status       ON public.notes(status);
CREATE INDEX IF NOT EXISTS idx_vault_files_user   ON public.vault_files(user_id);
CREATE INDEX IF NOT EXISTS idx_log_entity         ON public.processing_log(entity_type, entity_id);
