-- Vault file content + frontmatter storage (SYN-V5-003).
-- Additive and backwards-compatible: safe to apply to a live database.
-- Fixes the vault /file endpoint which queries these columns but they were
-- missing from the initial schema.
--
-- Apply with:  supabase db push   (or via the Supabase SQL editor / MCP)

ALTER TABLE public.vault_files
  ADD COLUMN IF NOT EXISTS content     text,
  ADD COLUMN IF NOT EXISTS frontmatter jsonb NOT NULL DEFAULT '{}';
