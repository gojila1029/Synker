# TDD Evidence Report — Discovery Engine Fix (Evidence Wiring + YouTube Discovery)

**Source plan:** produced inline via `/ecc:plan` in this session (no `*.plan.md` artifact file was written — conversational-mode plan, approved by the user directly in-thread).
**Branch:** `debug/synker-20260808-full-error-audit-phase4-C`

## User journeys

1. As a user, I add a specific YouTube video / web page / PDF / local file as a Source, so that Synker extracts it, and once I approve the resulting Candidate, a real Note appears in my Vault.
2. As a user, I add a YouTube channel or playlist URL as a Source, so that Synker discovers its videos as individual Candidates instead of silently failing.
3. As a user, when a channel/playlist source can't be discovered (e.g. a search-results URL), I see an honest reason instead of a misleading "Unknown" status.
4. As a user, once I've approved or rejected a discovered Candidate, a later scheduled run must not recreate it.
5. As a user, I can tell from the Sources screen that a channel/playlist source behaves differently from a single-video source.

## Task report

| Task | Summary | Validation command | Result |
|---|---|---|---|
| Phase 0 — Evidence wiring | `_analysis_handler` now persists a successful extraction into `source_extractions` immediately (no separate "Extraction" job exists anywhere in the codebase to do this later) | `uv run pytest tests/test_worker.py` | RED → GREEN, then full suite GREEN |
| Phase 1 — YouTube discovery module | New `app/adapters/youtube_discovery.py` enumerates a channel/playlist via yt-dlp (no login/API key); search URLs explicitly unsupported | `uv run pytest tests/adapters/test_youtube_discovery.py` | RED → GREEN (8/8) |
| Phase 1 — Wiring into `_analysis_handler` | `discovery_provider` sources now run real discovery instead of an unconditional skip; one candidate + Evidence row per discovered video; dedup broadened to all statuses, not just `pending` | `uv run pytest tests/test_worker.py` | RED → GREEN |
| Phase 2 — Frontend visibility | New `sourceScopeLabel()` helper + wiring into `SourcesScreen`'s card and the Add Source modal hint | `pnpm test`, `pnpm build` | RED → GREEN |

## Test specification

| # | What is guaranteed | Test file | Type | Result | Evidence |
|---|---|---|---|---|---|
| 1 | A successful extraction in `_analysis_handler` is persisted to `source_extractions` (Evidence), or Note Gen can never find it | `backend/tests/test_worker.py::test_analysis_handler_persists_evidence_on_successful_extraction` | unit | PASS | `uv run pytest tests/test_worker.py -v` |
| 2 | A `/results?search_query=` URL is reported as `unsupported_reason`, not a fake empty result | `backend/tests/adapters/test_youtube_discovery.py::test_search_url_is_explicitly_unsupported` | unit | PASS | `uv run pytest tests/adapters/test_youtube_discovery.py -v` |
| 3 | A channel/playlist URL returns its flat video entries (url + title) | `...test_youtube_discovery.py::test_channel_url_returns_flat_entries` | unit | PASS | same |
| 4 | An entry with no `url` field falls back to building one from `id` | `...test_youtube_discovery.py::test_entry_without_url_falls_back_to_id` | unit | PASS | same |
| 5 | `None` entries (deleted/private videos in a playlist) are skipped, not crashed on | `...test_youtube_discovery.py::test_blank_entries_in_playlist_are_skipped` | unit | PASS | same |
| 6 | A real yt-dlp failure surfaces as `.error` text, never silent empty success | `...test_youtube_discovery.py::test_yt_dlp_failure_is_reported_honestly` | unit | PASS | same |
| 7 | yt-dlp not installed is reported honestly, not a crash | `...test_youtube_discovery.py::test_yt_dlp_not_installed_is_reported_honestly` | unit | PASS | same |
| 8 | `limit` is actually passed through as yt-dlp's `playlistend` option | `...test_youtube_discovery.py::test_limit_is_passed_to_yt_dlp_options` | unit | PASS | same |
| 9 | Flat extraction (`extract_flat=True`) is always used, never full per-video fetch | `...test_youtube_discovery.py::test_extract_flat_option_is_set` | unit | PASS | same |
| 10 | Unsupported/failed discovery still skips honestly with the real reason, `adapter_extract` is never called | `backend/tests/test_worker.py::test_analysis_handler_skips_extraction_for_unsupported_discovery` | unit | PASS | `uv run pytest tests/test_worker.py -v` |
| 11 | Successful discovery creates one candidate + one Evidence row per discovered video, with the channel's id as lineage and the video's own URL as `source_info` | `...test_worker.py::test_analysis_handler_discovery_provider_creates_candidates_from_videos` | unit | PASS | same |
| 12 | The candidate dedup check does not filter by `status='pending'` (approved/rejected candidates are never silently recreated) | `...test_worker.py::test_dedup_check_does_not_filter_by_pending_status` | unit | PASS | same |
| 13 | `sourceScopeLabel()` returns the discovery hint only for `discovery_provider`, `null` otherwise (including `undefined`) | `AI Knowledge Curation Platform/src/app/sourceScopeLabel.test.ts` | unit | PASS | `pnpm test` |

## Coverage and known gaps

- Backend: 119/119 tests pass (`uv run pytest tests/`); `ruff check` and `mypy --strict` clean on every changed file (one pre-existing, unrelated `E501` in `_note_gen_handler` was left untouched per "avoid unrelated refactors").
- Frontend: 30/30 tests pass (`pnpm test`); no dedicated typecheck/lint script exists in this frontend (pre-existing gap, not introduced by this work) — `pnpm build` (production build) was used as the available compile-time signal and succeeds.
- **Not covered by any automated test in this repository, before or after this change:** a true end-to-end run against a real Postgres database and real network (yt-dlp against a real YouTube channel, real transcript extraction, a real Note landing in a real Obsidian vault). All tests above are unit-level with a hermetic fake DB connection (`FakeConn`/`FakePool`) or mocked `yt_dlp`/`adapter_extract`. This mirrors the pre-existing test strategy in this codebase (see `backend/tests/worker/test_note_gen_handler.py`, which is exactly the gap that let the Evidence-wiring bug go undetected until this session's manual code audit).
- **Explicitly out of scope for this change** (per this session's confirmed decisions): Reddit/Instagram/Facebook/Agent-Reach, website homepage discovery (RSS/sitemap), local folder discovery. Tracked as follow-up work, not attempted here.
- **Not yet live-verified**: this was implemented and unit-tested in this session but not run against Staging with a real disposable account and a real YouTube channel. Per the project's Evidence-First Rule, this must be stated plainly: **implemented and unit-tested, not end-to-end verified.**
