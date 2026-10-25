-- Rollback for 010_security_advisor_warnings: moves pgvector back to public and restores the old EXECUTE grants
-- (re-opens the advisor warnings; use only if the API or signup breaks).
ALTER EXTENSION vector SET SCHEMA public;
GRANT EXECUTE ON FUNCTION public.handle_new_user() TO PUBLIC, anon, authenticated;
