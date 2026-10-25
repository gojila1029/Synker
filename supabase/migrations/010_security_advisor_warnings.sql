-- Security advisor WARNs on production (after 009):
--  1. extension_in_public: move pgvector out of public. The only user of the type is
--     public.notes_embeddings.embedding (empty, unused by the backend); columns reference the type by OID,
--     so the move does not touch data. 'extensions' is already on the default search_path of the API roles.
--  2. anon/authenticated_security_definer_function_executable: handle_new_user() is only an auth.users
--     trigger function. Trigger firing does not check the caller's EXECUTE privilege, so revoking the
--     API roles' access closes /rest/v1/rpc/handle_new_user without affecting signup.
-- Not covered here: auth_leaked_password_protection is an Auth dashboard setting, not SQL.
ALTER EXTENSION vector SET SCHEMA extensions;
REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM PUBLIC, anon, authenticated;
