-- Discovery mode columns for source discovery customization
ALTER TABLE public.sources
  ADD COLUMN IF NOT EXISTS keyword         text,
  ADD COLUMN IF NOT EXISTS discovery_mode  text
    CHECK (discovery_mode IN ('single', 'channel_playlist', 'keyword', 'web_keyword')),
  ADD COLUMN IF NOT EXISTS discovery_limit integer DEFAULT 25
    CHECK (discovery_limit BETWEEN 1 AND 50);

-- Set defaults for existing sources
UPDATE public.sources SET discovery_mode = 'single'
  WHERE discovery_mode IS NULL AND source_scope = 'direct_resource';
UPDATE public.sources SET discovery_mode = 'channel_playlist'
  WHERE discovery_mode IS NULL AND source_scope = 'discovery_provider' AND type = 'youtube';

-- Index for candidate deduplication by source info
CREATE UNIQUE INDEX IF NOT EXISTS idx_candidates_user_source_info
  ON public.candidates(user_id, source_info);

-- Index for keyword sources to prevent duplicates
CREATE UNIQUE INDEX IF NOT EXISTS idx_sources_user_type_keyword
  ON public.sources(user_id, type, keyword)
  WHERE keyword IS NOT NULL AND keyword <> '';
