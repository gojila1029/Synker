Synker — Pre-Implementation Approval Summary

Agreed Decisions

Stack

┌───────────────┬─────────────────────────────────────────────────────────────┐
│     Layer     │                           Choice                            │
├───────────────┼─────────────────────────────────────────────────────────────┤
│ Shell         │ Desktop app (Electron or Tauri — see Unresolved)            │
├───────────────┼─────────────────────────────────────────────────────────────┤
│ Frontend      │ React + TypeScript + Vite                                   │
├───────────────┼─────────────────────────────────────────────────────────────┤
│ Backend       │ FastAPI (Python, local HTTP server)                         │
├───────────────┼─────────────────────────────────────────────────────────────┤
│ Database      │ Supabase (PostgreSQL) — remote, user has account            │
├───────────────┼─────────────────────────────────────────────────────────────┤
│ AI providers  │ Claude (Anthropic) + OpenAI/ChatGPT with automatic fallback │
├───────────────┼─────────────────────────────────────────────────────────────┤
│ Transcription │ Whisper (local) + YouTube video download option             │
└───────────────┴─────────────────────────────────────────────────────────────┘

Sources (all four in v1)

YouTube/video · Websites · PDFs · Local files and folders

Users

Configurable tiers selectable at setup: single user, small team (2–5), larger team (5+). Team tiers require Supabase auth and role management.

Knowledge Pipeline

1. Discovery — 10-min default interval (configurable per source type); local folders also watch file-change events with 30–60 s debounce.
2. Approval — Adaptive AI Preview per source type grouped by topic. Each candidate shows: title, source info, AI summary, extracted topics, quality/confidence/duplicate scores, expected note count, estimated token cost, and an AI recommendation (Process / Merge / Skip / Review).
3. Processing — triggers immediately after user approves a batch, not on a timer.
4. Note generation — knowledge-centric AI workflow:
  - < 40 % similarity → create new note
  - 40–80 % → merge new information into existing note
  - 80–95 % → update existing note, preserve history
▎ 95 % → skip duplicate, update references and metadata only
  - Knowledge Curator role: continuously reorganize MOCs, fix links, reclassify, surface low-value notes for review.
5. Wiki links — AI-driven; create [[links]] to related existing notes.
6. Vault write — atomic, containment-validated, path-traversal-safe.
7. Verification — re-read note, verify citations and links.
8. Graphify sync — once per verified development task (not on a timer).
9. Cleanup — three-tier:
  - User-owned files → read-only, never touched.
  - App-managed downloaded sources → configurable per vault (Keep / ZIP / Delete) with per-type retention rules; only after full verification.
  - Temporary artifacts → auto-deleted after successful run.

Metadata — Two-tier schema

- Tier 1 (YAML frontmatter) — Obsidian-facing: title, tags, source, dates, status, quality_score, confidence, moc, related_topics, graph_node_type.
- Tier 2 (Supabase) — AI system data: embeddings, duplicate analysis, processing history, retry state, Graphify sync logs, raw extraction artifacts.

Privacy

PII (names, IDs, health info) and insurance client data must not be sent to any cloud AI provider. PII detection runs locally before cloud dispatch.

Notifications

Desktop OS + in-app badge/alert + email (email provider TBD — see Unresolved).

Folder structure

By topic/category; all notes carry rich wiki links across folders.

Scheduling

Scheduled (default 10 min, configurable, stoppable) and manual trigger. Different activities run at different cadences as detailed during the interview.

---
Proposed Module Layout

synker/
├── electron/               # or tauri/
├── frontend/               # React + Vite
├── backend/
│   ├── adapters/           # youtube, web, pdf, local
│   ├── extraction/         # normalization, Whisper, OCR
│   ├── analysis/           # AI topic extraction, embedding, similarity
│   ├── approval/           # candidate management, approval persistence
│   ├── knowledge/          # note generation, wiki links, MOC, curator
│   ├── quality/            # citation checks, duplicate detection, PII guard
│   ├── vault/              # Obsidian write, path validation, atomicity
│   ├── graphify/           # Graphify plugin sync
│   ├── scheduler/          # discovery schedule, job orchestration
│   ├── cleanup/            # retention rules, archive
│   ├── notifications/      # desktop, email, in-app
│   └── auth/               # user tiers, roles
└── tests/                  # fixtures, disposable vault, unit + integration

---
Unresolved Items (must resolve before affected modules are built)

┌─────┬─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┬──────────────────────┐
│  #  │                                                              Item                                                               │        Impact        │
├─────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────────────────┤
│ 1   │ Electron vs Tauri — Electron is heavier (~200 MB) but mature; Tauri is lighter and uses Rust but adds a Rust build dependency.  │ Shell packaging, CI  │
├─────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────────────────┤
│ 2   │ Supabase connectivity — Remote Supabase works great when online but breaks the desktop app offline. Should we use local SQLite  │ Database             │
│     │ as the primary store and sync to Supabase for team features?                                                                    │ architecture         │
├─────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────────────────┤
│ 3   │ Email provider for notifications (Resend, SendGrid, or user's SMTP).                                                            │ Notifications module │
├─────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────────────────┤
│ 4   │ Your Obsidian vault path(s) — provided at first-run setup, not hardcoded.                                                       │ Vault module, tests  │
├─────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────────────────┤
│ 5   │ PII detection approach — rule-based regex + pattern matching (fast, free) or a local ML classifier (more accurate, heavier).    │ Quality / privacy    │
│     │                                                                                                                                 │ module               │
└─────┴─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┴──────────────────────┘

---
Risks

┌───────────────────────────────────────────────────────────────────────┬────────┬─────────────────────────────────────────────────────────────────────────────┐
│                                 Risk                                  │ Level  │                                 Mitigation                                  │
├───────────────────────────────────────────────────────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────┤
│ Electron/Tauri + FastAPI desktop packaging                            │ HIGH   │ Prototype shell + backend IPC early as Phase 0 spike                        │
├───────────────────────────────────────────────────────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────┤
│ Whisper is slow without GPU                                           │ HIGH   │ Show estimated time before processing; allow skipping                       │
├───────────────────────────────────────────────────────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────┤
│ Embedding + similarity for dedup requires significant Supabase        │ MEDIUM │ Use pgvector extension; batch embeddings; dedup on demand                   │
│ storage                                                               │        │                                                                             │
├───────────────────────────────────────────────────────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────┤
│ PII slipping through to cloud AI                                      │ MEDIUM │ Mandatory local PII scan before every cloud API call; configurable block    │
│                                                                       │        │ list                                                                        │
├───────────────────────────────────────────────────────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────┤
│ Supabase latency in offline / poor-connectivity desktop use           │ MEDIUM │ SQLite fallback + async Supabase sync                                       │
├───────────────────────────────────────────────────────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────┤
│ Graphify sync failures blocking note-writing                          │ LOW    │ Sync is post-verification, non-blocking; report failure separately          │
└───────────────────────────────────────────────────────────────────────┴────────┴─────────────────────────────────────────────────────────────────────────────┘

---
Acceptance Criteria (v1)

- [ ] User can configure an Obsidian vault and change it safely
- [ ] All four source types are discoverable and processable
- [ ] Adaptive AI approval dashboard shows topic-grouped candidates with quality scores
- [ ] Approved sources are processed immediately; unapproved sources are never auto-processed
- [ ] Notes are written with correct YAML frontmatter and wiki links inside the selected vault
- [ ] Knowledge-centric duplicate workflow correctly creates / merges / updates / skips
- [ ] Cleanup policy executes only after full verification (note + citations + links + Graphify)
- [ ] PII and insurance client data are blocked from cloud AI dispatch
- [ ] Scheduler runs on configurable interval with manual override; no overlapping runs
- [ ] Desktop + in-app + email notifications fire on run complete and failure
- [ ] All automated tests pass; end-to-end run on a disposable vault produces valid notes
- [ ] Graphify sync runs once at end of each verified development task

---
Awaiting your approval. Please confirm with "approved" (or note any changes), and I'll resolve the unresolved items above, then write the phased implementation plan before touching any code.

✻ Worked for 2m 46s

❯ btw, before the discovery, will I be able to give the discovery topics/category to the web application, right?

● User answered Claude's questions:
· What does "giving discovery topics" mean for you in practice? → Its more of the first option.

Yes, confirmed. You define the topic/category labels upfront (e.g., "Indian Insurance", "Claude AI", "Backend Dev"), and the AI uses those as the classification buckets when it discovers and sorts incoming sources. Sources that don't match any defined topic can either be flagged as "Uncategorised" for your review or auto-suggested as a potential new topic.

I'll add this to the approval summary as:

▎ Discovery topics — user-defined topic/category labels configured before discovery runs. The AI classifies each discovered source against these labels. Unmatched sources are held in an "Uncategorised" queue for user review or topic-creation suggestion.

This also means the approval dashboard naturally inherits the topic structure — each topic group already exists because you defined it, rather than the AI inventing groupings from scratch.

Does that match your expectation? Any other clarifications before you approve the summary?

✻ Brewed for 21s

❯ while note generation(4th section of the Knowledge Pipeline), the similariy of the note must be definded by AI, ok?

Understood. The percentage thresholds I listed (< 40%, 40–80%, etc.) will not be hard-coded rules. Instead, the AI receives the new content and the existing candidate notes, and makes its own judgment on similarity and the appropriate action (create / merge / update / skip) — with its reasoning recorded in the processing log.

The updated note in the approval summary reads:

▎ Note generation — knowledge-centric AI workflow: For each piece of approved content, the AI evaluates semantic similarity against existing vault notes and autonomously decides the action — create new note, merge into existing, update existing, or skip as duplicate. The AI determines similarity itself; no fixed percentage thresholds are imposed. Its decision and reasoning are recorded in the processing log for auditability.