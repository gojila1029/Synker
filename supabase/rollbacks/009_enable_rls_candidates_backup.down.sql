-- Rollback for 009_enable_rls_candidates_backup: turns RLS off again (re-opens the exposure; use only if the API breaks).
ALTER TABLE public.candidates_backup_20260918 DISABLE ROW LEVEL SECURITY;
