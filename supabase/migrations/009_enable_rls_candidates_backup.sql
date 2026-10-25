-- Security fix: public.candidates_backup_20260918 was created without Row Level Security
-- (Supabase advisor rls_disabled_in_public, level ERROR). With RLS off, anyone holding the
-- anon key could read it through PostgREST.
-- No policy on purpose: anon and authenticated get no access; the service role bypasses RLS.
-- Additive in effect and trivially reversible (see supabase/rollbacks/009_enable_rls_candidates_backup.down.sql).
ALTER TABLE public.candidates_backup_20260918 ENABLE ROW LEVEL SECURITY;
