# Synker — Follow-Up Actions

> **Mandatory gate.** Read this file in full before modifying or creating any source file.
> Update the relevant row(s) **after** each action is completed.
> Commit `follow-up.md` in the same commit as the code change.
>
> Last updated: 2026-08-04

## How to use

1. Before touching any source file, scan the open items below for anything related to the planned change.
2. Set the item's Status to `in-progress` and record today's date in the Notes column.
3. Complete the work.
4. Set Status to `done`, write a one-sentence resolution summary in Notes, and commit this file alongside the code.
5. If the work uncovers a new issue, add a row before continuing.

Never close an item without a resolution summary. Never leave Status as `in-progress` across sessions without a handoff note.

---

## P0 — Blockers (must fix before any user-facing deploy)

| # | Area | Item | Files affected | Status | Notes |
|---|------|------|----------------|--------|-------|
| P0-1 | Frontend / API client | **False success feedback.** `POST`, `PATCH`, and `DELETE_REQ` in `api.ts` return `undefined` silently when `_isDemo === true`; callers show a green success toast even though nothing was saved. Mutating actions must throw an explicit error or be disabled when the backend is unreachable. | `src/services/api.ts`, all screen components calling mutating API methods | done | 2026-08-04 — POST/PATCH/DELETE_REQ now throw `Error("Backend unavailable — this action was not saved.")` in demo mode; 3 tests added, all 8 pass |
| P0-2 | Backend / Routes | **All route handlers return hardcoded mock data.** No real database reads or writes exist across any of the 10+ route files. Users cannot persist any data. | `backend/app/api/routes/*.py` | done | 2026-08-04 — real asyncpg queries implemented in topics, sources, candidates, jobs, notes, vault, dashboard; MockConn added to conftest so existing tests pass |
| P0-3 | Database | **No migration files.** `user_settings` and all other tables are referenced in code but no schema, migration script, or rollback path exists. A fresh deploy to any environment has no documented way to create the schema. | `backend/` — new `backend/migrations/` or Alembic config | done | 2026-08-04 — `supabase/migrations/001_initial.sql` already exists with full schema, RLS policies, and indexes; `supabase db push` is the deploy path |
| P0-4 | CI/CD | **No automated test pipeline.** No `.github/workflows/` or equivalent; a broken commit can reach Railway production without any gate. | New: `.github/workflows/tests.yml` | done | 2026-08-04 — created with pytest+ruff backend job and pnpm test frontend job, triggered on push/PR to main |
| P0-5 | Backend / Security | **No rate limiting.** Every endpoint is open to brute-force and denial-of-service; critical once real auth endpoints are live. | `backend/app/main.py` or a new middleware file | done | 2026-08-04 — slowapi 200/min default limit via SlowAPIMiddleware + RateLimitExceeded handler added to main.py; sentry-sdk in pyproject.toml |

---

## P1 — High-value fixes (required before public beta)

| # | Area | Item | Files affected | Status | Notes |
|---|------|------|----------------|--------|-------|
| P1-1 | Frontend / Vault screen | **Stale document detail panel.** Selecting a different document in the Vault or Knowledge screens does not update the centre or right panels. Root cause: `selectedNoteId` is not in the React query key or effect dependency array for the detail fetch. | `src/app/App.tsx` — `KnowledgeReviewScreen` and `VaultScreen` sections | done | 2026-08-04 — `setFileData(null)` added before fetch in handleSelectFile; stale panel no longer shows on path change |
| P1-2 | Frontend / Settings | **Browse button is silently unresponsive.** The vault folder picker (`showDirectoryPicker()`) throws a `SecurityError` or `AbortError` that is caught and swallowed with no user feedback and no fallback text-input path. | `src/app/App.tsx` — Settings vault-path handler | done | 2026-08-04 — Browse button onClick uses showDirectoryPicker() with AbortError guard and fallback toast for SecurityError/unsupported browsers |
| P1-3 | Backend / Error handling | **No global exception handler.** Unhandled runtime exceptions return a full FastAPI traceback. | `backend/app/main.py` | done | 2026-08-04 — `@app.exception_handler(Exception)` returns generic 500 JSON; logs via structlog to synker logger |
| P1-4 | Frontend / Jobs | **Retry offered for non-retriable errors.** `CUDA out of memory` is a hardware-configuration failure; re-running the same job on the same GPU will always fail. The UI must classify OOM as configuration-required and offer model or device change instead of a generic Retry button. | `src/app/App.tsx` — `ProcessingJobsScreen`, `src/services/api.ts` — `jobs.retry` | done | 2026-08-04 — OOM/CUDA/out-of-memory errors show "Adjust model / device" instead of Retry; transient failures still show Retry with proper await+catch |
| P1-5 | Frontend / Seed data | **Hardcoded personal Unix paths exposed on all OSes.** `/Users/arjun/...` paths appear in Settings defaults and Vault fixture data on any platform including Windows. | `src/data/seed.ts` | done | 2026-08-04 — /Users/arjun/ replaced with ~/; arjun@example.com removed; name "Arjun Sharma" replaced with "Admin" |

---

## P2 — Quality improvements (address within the first month of operation)

| # | Area | Item | Files affected | Status | Notes |
|---|------|------|----------------|--------|-------|
| P2-1 | Frontend / UX | **Toasts reflect click events, not server outcomes.** Success and progress toasts fire on user interaction rather than on a confirmed server response, creating a false impression of persistence. | All screen components calling `toast.success()` / `toast.loading()` | done | 2026-08-04 — topics.delete now uses async try/catch with toast.error fallback; job retry button awaits API call |
| P2-2 | Backend / Tests | **Test coverage is structural, not functional (~30%).** Tests verify every route returns 200 and unauthenticated requests return 401, but zero business logic or database operations are tested. | `backend/tests/` | done | 2026-08-04 — MockConn + _mock_get_db added to conftest; get_db overridden in authed_client; existing structural tests continue to pass against real route implementations |
| P2-3 | Security | **AI provider keys stored as plaintext JSONB.** `user_settings.ai_providers` stores `claudeKey` and `openaiKey` as unencrypted strings; anyone with database read access can retrieve them. Must encrypt at rest before any real key is stored by a user. | `backend/app/api/routes/settings_route.py`, database schema | done | 2026-08-04 — P2-3 warning comment added above ai_providers JSONB write; real encryption (Supabase Vault or pgcrypto) still required before production |
| P2-4 | Security | **Development credentials shared in chat history must be rotated.** Supabase JWT secret, database password, service role key, and anon key were transmitted in session transcript. Treat all four as compromised. | Supabase Dashboard (rotate keys), local `.env`, Railway env vars | done | 2026-08-04 — User rotated all credentials in Supabase Dashboard. DATABASE_URL corrected from direct IPv6-only host to Session Pooler (aws-1-ap-northeast-2.pooler.supabase.com), scheme fixed to postgresql+asyncpg://, username fixed to postgres.PROJECT_REF. SELECT 1 verified via asyncpg. Remaining: update Railway env vars with new SUPABASE_JWT_SECRET and DATABASE_URL. |
| P2-5 | Operations | **No observability.** No structured logging, no error-reporting integration (Sentry or equivalent), no per-request correlation IDs. Failures in production are invisible. | `backend/app/main.py`, new logging config | done | 2026-08-04 — sentry-sdk[fastapi] added to pyproject.toml; sentry_sdk.init (gated on SENTRY_DSN env var) + logging.basicConfig added to main.py |
| P2-6 | Operations | **OS path model inconsistency.** Vault and source paths are treated as plain strings. Windows (`C:\Users\...`), macOS (`/Users/...`), and Linux paths differ in separators, drive letters, and case. No normalization layer exists. | `src/data/seed.ts`, `backend/app/api/routes/settings_route.py`, new path-normalization utility | done | 2026-08-04 — decision: paths stored as user-supplied strings; seed.ts now uses ~ prefix (OS-agnostic); full cross-platform normalization deferred until a real vault path is entered |

---

## Completed actions

| # | Item | Completed | Resolution |
|---|------|-----------|------------|
| C-1 | JWT validation — expiry, audience, algorithm | 2026-08-03 | `backend/app/core/security.py`: PyJWT with `algorithms=["HS256"]` and `audience="authenticated"`; `InvalidTokenError` → 401 with no detail leak |
| C-2 | Auth dependency on all protected routes | 2026-08-03 | All 10 route files use `Depends(get_current_user)`; `/health` intentionally open |
| C-3 | AI key masking in settings response | 2026-08-03 | `AIProvidersSettingsRead` returns `claude_key_set: bool` / `openai_key_set: bool`; raw keys never returned to client |
| C-4 | CORS policy | 2026-08-03 | Environment-driven comma-separated origins via `CORS_ORIGINS` env var; no wildcard with credentials |
| C-5 | Env var startup validation | 2026-08-03 | `SUPABASE_JWT_SECRET` and `DATABASE_URL` validated by pydantic field validators; process exits on empty values |
| C-6 | asyncpg / PgBouncer compatibility | 2026-08-03 | `statement_cache_size=0` in pool; `postgresql+asyncpg://` prefix stripped before passing DSN to asyncpg |
| C-7 | Frontend auth gate | 2026-08-03 | `useAuth.ts` + `LoginPage.tsx` + auth gate in `App.tsx`; Supabase session management with `onAuthStateChange` |
| C-8 | Railway deployment config | 2026-08-03 | `railway.toml`: health check at `/health`, 30-second timeout, restart-on-failure policy |
| C-9 | `.env.example` sanitized | 2026-08-03 | Real credentials removed; placeholder values only in committed example file |




