-- Add source_url to source_extractions so that when a discovery_provider
-- channel produces multiple video extractions (all sharing the same source_id),
-- Note Gen can look up the exact extraction for the approved candidate's URL
-- rather than always picking the most-recently-extracted row for that source.
--
-- Additive and nullable — safe to apply to a live database.
-- Apply with:  supabase db push   (or via the Supabase SQL editor / MCP)

ALTER TABLE public.source_extractions
  ADD COLUMN IF NOT EXISTS source_url text;

CREATE INDEX IF NOT EXISTS idx_source_extractions_url
  ON public.source_extractions(source_url)
  WHERE source_url IS NOT NULL;
