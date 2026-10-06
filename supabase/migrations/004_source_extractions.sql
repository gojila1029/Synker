-- Raw source extraction results, written by
-- backend/app/worker/handlers.py _extraction_handler.
--
-- This table was originally applied directly to Supabase as migration
-- 20260806_source_extractions and was never committed to this repo — a fresh
-- environment built from these tracked migrations could not reproduce the
-- live schema. Committing it now (2026-09-13) to close that drift.
--
-- Known gap carried over unchanged from the live table: user_id has no FK to
-- public.users, unlike every sibling table. Not fixed here — this migration
-- only records what is already live in production; deciding whether to add
-- the FK is a separate change.
--
-- Apply with:  supabase db push   (or via the Supabase SQL editor / MCP)

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

CREATE INDEX IF NOT EXISTS idx_source_extractions_source ON public.source_extractions(source_id);
CREATE INDEX IF NOT EXISTS idx_source_extractions_user   ON public.source_extractions(user_id);
