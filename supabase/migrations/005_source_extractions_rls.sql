-- CRITICAL security fix: source_extractions had Row Level Security disabled
-- since its creation (migration 20260806_source_extractions never enabled
-- it, unlike every sibling table). Any holder of the Supabase anon key could
-- read or write every user's extracted source text, titles, authors, and
-- timestamps via the standard Supabase client / PostgREST.
--
-- Applied directly to production via Supabase MCP and verified fixed
-- (get_advisors no longer reports it; pg_policy confirms the policy) on
-- 2026-09-13. Committing here so the repo matches production and so a fresh
-- environment doesn't reintroduce the gap.
--
-- Apply with:  supabase db push   (or via the Supabase SQL editor / MCP)

ALTER TABLE public.source_extractions ENABLE ROW LEVEL SECURITY;

CREATE POLICY source_extractions_own ON public.source_extractions
  USING (user_id = auth.uid());
