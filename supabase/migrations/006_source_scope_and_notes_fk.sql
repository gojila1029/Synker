-- Stage 3/4 contract decisions (ECC pipeline, 2026-09-13):
--   1. sources.source_scope distinguishes a source that IS content
--      (direct_resource: youtube/web/pdf/local) from one that DISCOVERS other
--      content (discovery_provider: future github/rss/web_search). Additive,
--      defaulted — existing rows are unaffected and read as direct_resource.
--   2. notes.topic_id / notes.source_id are direct FKs so a Note's lineage
--      survives its candidate being deleted (candidate_id is ON DELETE
--      SET NULL, which otherwise orphans provenance — CLAUDE.md #22/#23).
--   3. jobs.error_code is a short machine-readable code (e.g. NO_EVIDENCE),
--      separate from the free-text jobs.error column, so callers can branch
--      on failure reason without string-matching.
--
-- All four changes are additive/nullable-with-default — safe on a live table.
-- Apply with:  supabase db push   (or via the Supabase SQL editor / MCP)

ALTER TABLE public.sources ADD COLUMN IF NOT EXISTS source_scope text
  NOT NULL DEFAULT 'direct_resource'
  CHECK (source_scope IN ('direct_resource', 'discovery_provider'));

ALTER TABLE public.notes ADD COLUMN IF NOT EXISTS topic_id uuid
  REFERENCES public.topics(id) ON DELETE SET NULL;
ALTER TABLE public.notes ADD COLUMN IF NOT EXISTS source_id uuid
  REFERENCES public.sources(id) ON DELETE SET NULL;

ALTER TABLE public.jobs ADD COLUMN IF NOT EXISTS error_code text;
