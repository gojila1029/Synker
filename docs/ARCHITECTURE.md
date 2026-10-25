# Synker — Architecture, Workflows & End-to-End Processes

> **Version**: synker-v1  
> **Stack**: FastAPI (Python 3.12) + React 18 (TypeScript) + PostgreSQL (Supabase) + Railway

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [High-Level Architecture](#2-high-level-architecture)
3. [End-to-End Pipeline](#3-end-to-end-pipeline)
4. [Backend Architecture](#4-backend-architecture)
5. [Frontend Architecture](#5-frontend-architecture)
6. [Database Schema](#6-database-schema)
7. [Job Worker System](#7-job-worker-system)
8. [AI Integration](#8-ai-integration)
9. [Source Adapters](#9-source-adapters)
10. [API Reference](#10-api-reference)
11. [Authentication & Security](#11-authentication--security)
12. [Deployment & CI/CD](#12-deployment--cicd)
13. [Development Workflow](#13-development-workflow)
14. [Technology Stack](#14-technology-stack)

---

## 1. Project Overview

Synker is an **AI-powered knowledge curation platform** that transforms approved source material (YouTube videos, websites, PDFs, local files) into structured, interconnected Markdown notes inside an Obsidian vault.

### Core Value Proposition

| Problem | Solution |
|---------|----------|
| Information overload from multiple sources | Unified ingestion pipeline with single approval queue |
| Manual note-taking is time-consuming | AI-generated notes with citations and wiki links |
| Notes are disconnected and siloed | Automatic `[[wiki link]]` generation across notes |
| Duplicate content wastes space | Jaccard similarity deduplication before writing |
| Content quality varies wildly | Quality scoring + human approval gate |

### Key Capabilities

- **Multi-source ingestion**: YouTube (channels, playlists, search, single video), websites, PDFs, local files
- **4-strategy YouTube extraction**: official transcripts → Supadata API → yt-dlp subs → Groq Whisper STT
- **AI note generation**: Claude / OpenAI / Ollama with structured Markdown output
- **Human-in-the-loop**: every candidate and every note requires explicit approval before vault write
- **Scheduled automation**: configurable background processing (default: every 10 minutes)
- **Duplicate detection**: Jaccard keyword similarity across vault + pending notes
- **Multi-replica worker**: atomic job claiming with stale-job recovery
- **Graceful degradation**: frontend demo mode on API failure

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          USER BROWSER                           │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │            React 18 + TypeScript + Vite                   │  │
│  │   Dashboard │ Sources │ Candidates │ Jobs │ Notes │ Vault  │  │
│  └────────────────────────┬──────────────────────────────────┘  │
└───────────────────────────│─────────────────────────────────────┘
                            │ HTTPS + Bearer JWT
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RAILWAY (Production)                         │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                  FastAPI + Uvicorn                         │  │
│  │                                                           │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │  │
│  │  │  Routers │  │ Adapters │  │ AI Client│  │  Worker  │ │  │
│  │  │ (REST API)│  │(Extract.)│  │(Claude/  │  │(Async   │ │  │
│  │  │          │  │          │  │ GPT/Ollama│  │ Jobs)   │ │  │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘ │  │
│  └───────│─────────────│─────────────│───────────────│───────┘  │
└──────────│─────────────│─────────────│───────────────│──────────┘
           │             │             │               │
           ▼             ▼             ▼               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SUPABASE (Cloud)                             │
│                                                                 │
│   PostgreSQL DB          Supabase Auth        JWKS Endpoint    │
│   (asyncpg pool)         (JWT tokens)         (ES256 keys)     │
└─────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────┐
│               EXTERNAL SERVICES                                 │
│                                                                 │
│  YouTube API  │  Supadata API  │  DuckDuckGo  │  Groq Whisper  │
│  (yt-dlp)    │  (transcripts) │  (web search)│  (STT)         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. End-to-End Pipeline

The full lifecycle from adding a source to a finalized Obsidian note:

```
STEP 1: ADD SOURCE
User adds a source URL or uploads files via UI
  → Source stored with status="queued"
  → source_scope classified: direct_resource | discovery_provider

STEP 2: ANALYSIS JOB (scheduler auto-creates or manual trigger)
Worker picks up Analysis job
  ├── discovery_provider sources (channels, playlists, search terms)
  │     → YouTubeDiscoveryAdapter enumerates videos
  │     → Creates one Candidate per discovered video
  └── direct_resource sources (single URL, PDF, local file)
        → Adapter extracts content (text, title, author, timestamps)
        → Jaccard similarity vs vault + notes (max 4.5s)
        → Creates Candidate with quality/confidence/duplicate scores
        → source_extraction evidence record written

STEP 3: CANDIDATE APPROVAL (Human Gate)
User reviews Candidates list:
  - Sees: title, domain, quality score, duplicate score, recommendation
  - Actions: Approve ✓ | Reject ✗ | Bulk select all
  → Approved candidates → Note Gen jobs queued
  → Rejected candidates → status="rejected" (no processing)

STEP 4: NOTE GENERATION JOB
Worker picks up Note Gen job per approved candidate
  → Sends extracted content to AI (Claude / GPT / Ollama)
  → AI returns structured JSON:
      {
        "title": "...",
        "content": "# Markdown content...",
        "citations": ["url1", "url2"],
        "wiki_links": ["[[Related Note]]"],
        "quality_score": 0.87,
        "ai_action": "created | merged | updated | skipped",
        "similarity_reasoning": "..."
      }
  → Note stored with status="pending"

STEP 5: NOTE APPROVAL (Human Gate)
User reviews Notes list:
  - Sees: title, quality score, AI action, has_duplicate flag
  - Can preview full Markdown content
  → Approved notes → written to vault_files table
                   → Graphify Sync job queued (knowledge graph update)
  → Rejected notes → status="rejected"

STEP 6: VAULT SYNC
User opens Vault tab to browse written notes:
  - Tree view of folders and files
  - Full Markdown preview with frontmatter
  - Backlinks count per note
```

### Pipeline State Machine

```
Source States:
  queued ──► processing ──► done
                │
                └──► failed ──► (reset) ──► queued

Candidate States:
  pending ──► approved ──► (Note Gen runs)
     └──────► rejected

Note States:
  pending ──► approved ──► (written to vault)
     └──────► rejected

Job States:
  queued ──► running ──► completed
               │
               └──► failed ──► (retry) ──► queued
```

---

## 4. Backend Architecture

### Directory Structure

```
backend/
├── app/
│   ├── main.py                    # App factory, lifespan, middleware, route registration
│   ├── core/
│   │   ├── config.py              # Pydantic Settings (env validation)
│   │   └── security.py            # Supabase JWT + JWKS verification
│   ├── db/
│   │   └── client.py              # asyncpg pool (PgBouncer-safe)
│   ├── api/
│   │   ├── deps.py                # Dependency injection: auth, db pool
│   │   └── routes/
│   │       ├── topics.py          # /api/topics
│   │       ├── sources.py         # /api/sources, /api/sources/upload
│   │       ├── candidates.py      # /api/candidates, approve/reject
│   │       ├── jobs.py            # /api/jobs, retry/cancel
│   │       ├── notes.py           # /api/notes, approve/reject
│   │       ├── vault.py           # /api/vault/tree, /api/vault/file
│   │       ├── settings_route.py  # /api/settings
│   │       ├── dashboard.py       # /api/dashboard/stats, activity
│   │       ├── scheduler.py       # /api/scheduler/trigger, status
│   │       ├── youtube.py         # /api/youtube/search, parse-intent, notes/batch
│   │       ├── website.py         # /api/website/search, parse-intent
│   │       └── health.py          # /health
│   ├── schemas/                   # Pydantic v2 request/response models
│   ├── adapters/                  # Source extraction (pluggable)
│   ├── ai/                        # LLM integration
│   └── worker/                    # Async job processor
├── tests/                         # pytest test suite
└── pyproject.toml                 # uv dependencies + pytest config
```

### Middleware Stack (request → response order)

```
1. CORS              — Allow configured origins
2. SlowAPI           — Rate limit: 200 req/min per IP
3. X-Request-ID      — Inject correlation ID for log tracing
4. Sentry            — Exception capture (if DSN configured)
5. Global Exception  — Sanitized 500 responses (no stack traces to client)
6. Route Handlers    — Business logic
```

### Application Lifespan

```python
# On startup:
1. Initialize asyncpg connection pool (min=2, max=10)
2. Register JSON codec for jsonb columns
3. Start worker_loop (if WORKER_ENABLED=true)
4. Start reaper_loop (stale job recovery)
5. Start scheduler_loop (auto-create Analysis jobs)

# On shutdown:
1. Cancel background tasks
2. Close DB pool
```

---

## 5. Frontend Architecture

### Directory Structure

```
AI Knowledge Curation Platform/
├── src/
│   ├── main.tsx               # React DOM mount point
│   ├── app/
│   │   ├── App.tsx            # Root: auth gate + tab layout
│   │   ├── LoginPage.tsx      # Supabase email/OTP auth
│   │   ├── sourceScopeLabel.ts
│   │   └── components/ui/     # shadcn/ui component library (50+ files)
│   ├── hooks/
│   │   ├── useAuth.ts         # Supabase session state
│   │   └── useApi.ts          # Generic API call hook
│   ├── services/
│   │   └── api.ts             # HTTP client with demo mode fallback
│   ├── lib/
│   │   └── supabase.ts        # Supabase client
│   ├── types/
│   │   └── index.ts           # All TypeScript interfaces
│   └── data/
│       └── seed.ts            # Demo mode mock data
├── package.json
├── vite.config.ts
└── tsconfig.json
```

### Tab Structure

| Tab | Purpose | Key Actions |
|-----|---------|-------------|
| **Dashboard** | Overview stats + activity feed | View pending counts, recent jobs |
| **Sources** | Manage input sources | Add URL, upload files, reset, delete |
| **Candidates** | Approve/reject discovered content | Bulk select, approve, reject |
| **Jobs** | Monitor processing pipeline | View progress, retry failed, cancel |
| **Notes** | Review AI-generated notes | Preview, approve (writes to vault), reject |
| **Vault** | Browse written Obsidian notes | Tree view, file preview with frontmatter |
| **Settings** | Configure AI providers + vault | API keys (encrypted), vault path |

### API Client Design (services/api.ts)

```typescript
// All methods share the same error handling:
// - 2xx: return parsed JSON
// - non-2xx: increment fail streak
// - 2 consecutive failures: enter demo mode (return seed data)
// - File upload: 120s timeout (multipart/form-data)

api.topics.list()
api.topics.create(label, color?)
api.topics.delete(id)

api.sources.list()
api.sources.add({ type, url, topicId, keyword, discoveryMode, discoveryLimit })
api.sources.delete(id)
api.sources.reset(id)
api.sources.upload(files, relativePaths, type)

api.candidates.list()
api.candidates.approve(ids[])
api.candidates.reject(ids[])

api.jobs.list()
api.jobs.retry(id)
api.jobs.cancel(id)
api.jobs.delete(id)

api.notes.list(status?)
api.notes.approve(id)
api.notes.reject(id)

api.vault.tree()
api.vault.file(path)

api.scheduler.trigger()
api.scheduler.status()

api.youtube.search(query, limit)
api.youtube.parseIntent(message)
api.youtube.createNotesBatch(urls[])

api.website.parseIntent(message)
```

### TypeScript Type Definitions

```typescript
interface Source {
  id: string
  type: "youtube" | "web" | "pdf" | "local"
  sourceScope: "direct_resource" | "discovery_provider"
  title: string
  url: string
  topicId: string | null
  status: "queued" | "processing" | "done" | "failed"
  addedAt: string
  discoveryMode: "single" | "channel_playlist" | "keyword" | "web_keyword" | null
  discoveryLimit: number | null
}

interface Candidate {
  id: string
  title: string
  sourceInfo: string          // URL of the candidate content
  domain: string
  publishedAt: string | null
  topicId: string | null
  recommendation: "process" | "merge" | "skip" | "review"
  qualityScore: number        // 0.0–1.0
  confidenceScore: number     // 0.0–1.0
  duplicateScore: number      // 0.0–1.0 (Jaccard similarity)
  summary: string
  extractedTopics: string[]
  status: "pending" | "approved" | "rejected"
}

interface Job {
  id: string
  sourceTitle: string
  type: "Extraction" | "Transcription" | "Analysis" | "PII Check"
       | "Note Gen" | "Verification" | "Graphify Sync" | "Cleanup"
  status: "queued" | "running" | "completed" | "failed"
  progress: number            // 0–100
  startedAt: string | null
  duration: number | null
  error: string | null
}

interface Note {
  id: string
  title: string
  source: string
  generatedAt: string
  aiAction: "created" | "merged" | "updated" | "skipped"
  qualityScore: number
  hasDuplicate: boolean
  content: string             // Full Markdown
  frontmatter: Record<string, unknown>
  citations: string[]
  wikiLinks: string[]
  similarityReasoning: string
}
```

---

## 6. Database Schema

All tables use `user_id UUID` for row-level isolation. No ORM — direct parameterized SQL via asyncpg.

### topics
```sql
CREATE TABLE topics (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID NOT NULL,
  label      TEXT NOT NULL,
  color      TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

### sources
```sql
CREATE TABLE sources (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL,
  type            TEXT NOT NULL,          -- youtube | web | pdf | local
  source_scope    TEXT NOT NULL,          -- direct_resource | discovery_provider
  title           TEXT,
  url             TEXT,
  keyword         TEXT,
  topic_id        UUID REFERENCES topics,
  status          TEXT DEFAULT 'queued',  -- queued | processing | done | failed
  discovery_mode  TEXT,                   -- single | channel_playlist | keyword | web_keyword
  discovery_limit INT,
  schedule        TEXT,
  added_at        TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now()
);
```

### candidates
```sql
CREATE TABLE candidates (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID NOT NULL,
  source_id        UUID REFERENCES sources ON DELETE CASCADE,
  title            TEXT NOT NULL,
  domain           TEXT,
  summary          TEXT,
  source_info      TEXT,
  topic_id         UUID REFERENCES topics,
  status           TEXT DEFAULT 'pending', -- pending | approved | rejected
  recommendation   TEXT,                  -- process | merge | skip | review
  quality_score    FLOAT DEFAULT 0.0,
  confidence_score FLOAT DEFAULT 0.0,
  duplicate_score  FLOAT DEFAULT 0.0,
  expected_notes   INT DEFAULT 1,
  estimated_tokens INT DEFAULT 0,
  extracted_topics TEXT[],
  published_at     DATE,
  created_at       TIMESTAMPTZ DEFAULT now(),
  updated_at       TIMESTAMPTZ DEFAULT now()
);
```

### source_extractions
```sql
CREATE TABLE source_extractions (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id    UUID REFERENCES sources ON DELETE CASCADE,
  user_id      UUID NOT NULL,
  source_url   TEXT,
  text         TEXT,
  title        TEXT,
  author       TEXT,
  published_at TEXT,
  timestamps   JSONB,                     -- [{time, text}] for videos
  word_count   INT DEFAULT 0,
  created_at   TIMESTAMPTZ DEFAULT now()
);
```

### jobs
```sql
CREATE TABLE jobs (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID NOT NULL,
  candidate_id     UUID REFERENCES candidates,
  source_id        UUID REFERENCES sources,
  source_title     TEXT,
  type             TEXT NOT NULL,
  status           TEXT DEFAULT 'queued', -- queued | running | completed | failed
  progress         INT DEFAULT 0,
  error            TEXT,
  error_code       TEXT,
  started_at       TIMESTAMPTZ,
  finished_at      TIMESTAMPTZ,
  heartbeat_at     TIMESTAMPTZ,
  claimed_by       TEXT,                  -- "hostname:pid"
  duration_seconds INT,
  created_at       TIMESTAMPTZ DEFAULT now(),
  updated_at       TIMESTAMPTZ DEFAULT now()
);
```

### notes
```sql
CREATE TABLE notes (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id              UUID NOT NULL,
  candidate_id         UUID REFERENCES candidates,
  source_id            UUID REFERENCES sources,
  title                TEXT NOT NULL,
  content              TEXT,
  source               TEXT,
  topic_id             UUID REFERENCES topics,
  status               TEXT DEFAULT 'pending',
  ai_action            TEXT,              -- created | merged | updated | skipped
  quality_score        FLOAT DEFAULT 0.0,
  has_duplicate        BOOLEAN DEFAULT FALSE,
  duplicate_score      FLOAT,
  frontmatter          JSONB,
  citations            TEXT[],
  wiki_links           TEXT[],
  similarity_reasoning TEXT,
  similar_to           UUID REFERENCES notes,
  generated_at         TIMESTAMPTZ DEFAULT now(),
  approved_at          TIMESTAMPTZ,
  created_at           TIMESTAMPTZ DEFAULT now(),
  updated_at           TIMESTAMPTZ DEFAULT now()
);
```

### vault_files
```sql
CREATE TABLE vault_files (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL,
  path            TEXT NOT NULL,
  content         TEXT,
  frontmatter     JSONB,
  last_modified   TIMESTAMPTZ DEFAULT now(),
  word_count      INT DEFAULT 0,
  backlinks       INT DEFAULT 0,
  graph_node_type TEXT,
  cloud_safe      BOOLEAN DEFAULT TRUE,
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now(),
  UNIQUE (user_id, path)
);
```

### processing_log
```sql
CREATE TABLE processing_log (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL,
  entity_type TEXT,
  entity_id   UUID,
  action      TEXT,
  details     JSONB,
  created_at  TIMESTAMPTZ DEFAULT now()
);
```

---

## 7. Job Worker System

The worker runs **in-process** alongside FastAPI (no Celery, no Redis — single deployment unit).

### Three Background Loops

```
worker_loop    runs every WORKER_POLL_SECONDS (default: 10s)
               Claims jobs: FOR UPDATE SKIP LOCKED
               Executes up to WORKER_CONCURRENCY jobs in parallel (default: 3)

reaper_loop    runs every 60s
               Finds jobs with heartbeat_at < now() - JOB_STALE_SECONDS (300s)
               Sets status='failed', error='Worker stalled — no heartbeat'

scheduler_loop runs every 10 × WORKER_POLL_SECONDS
               Finds users with queued sources but no pending Analysis job
               Auto-creates Analysis job to unblock the pipeline
```

### Atomic Job Claiming (Multi-Replica Safe)

```sql
UPDATE jobs
SET status = 'running',
    started_at = now(),
    heartbeat_at = now(),
    claimed_by = $1
WHERE id = (
  SELECT id FROM jobs
  WHERE status = 'queued'
  ORDER BY created_at
  LIMIT 1
  FOR UPDATE SKIP LOCKED
)
RETURNING *
```

### Job Handler Map

| Job Type | Description |
|----------|-------------|
| `Analysis` | Discover/extract sources → create candidates with similarity scoring |
| `Note Gen` | AI note generation from approved candidate |
| `Graphify Sync` | Update knowledge graph after note approval |
| `Cleanup` | Archive/delete processed source files |
| `Verification` | Re-run quality checks on generated notes |

### Analysis Job: Full Flow

```
For each queued source owned by user:

  IF source_scope == "discovery_provider":
    → YouTubeDiscoveryAdapter enumerates all videos in channel/playlist/search
    → Creates one Candidate per video (status=pending)

  IF source_scope == "direct_resource":
    → Appropriate adapter extracts content
    → IF extraction fails:
        Create Candidate with quality_score=0.0, recommendation="review"
        Honest error in summary (never fabricate scores)
    → IF extraction succeeds:
        Extract keywords from title + first 5 sentences
        Compute Jaccard similarity vs vault_files + notes (4.5s timeout)
        duplicate_score = max(sim_vs_vault, sim_vs_notes)
        recommendation = "merge" if dup > 0.8 else "process"
        Write source_extraction evidence record
        Create Candidate

  Update source.status = "done"
```

### Similarity Computation (Jaccard)

```python
def jaccard(set_a: set, set_b: set) -> float:
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)

# Keyword extraction:
# 1. title + first 5 sentences of extracted text
# 2. tokenize on whitespace/punctuation
# 3. filter: len >= 3, not in stopword list
# 4. compare against each vault_file and existing note
# 5. return max similarity
```

---

## 8. AI Integration

### Supported LLM Providers

| Provider | Models | Purpose |
|----------|--------|---------|
| **Anthropic Claude** | claude-3-5-haiku, claude-3-5-sonnet | Note generation, intent parsing |
| **OpenAI GPT** | gpt-4o, gpt-4o-mini | Note generation fallback |
| **Ollama** | any local model | Offline / privacy mode |

### Note Generation

The AI receives structured context and returns JSON:

```
System prompt: You are a knowledge curation assistant. Generate a structured
Obsidian note from the source content. Output valid JSON only.

Input:
  - Source URL + title
  - Full extracted text
  - Sample of existing vault notes (for context + dedup)

Output JSON:
  {
    "title": "Note Title",
    "content": "# Full Markdown...",
    "citations": ["https://source-url"],
    "wiki_links": ["[[Related Note]]"],
    "quality_score": 0.87,
    "ai_action": "created",
    "similarity_reasoning": "Why this is/isn't a duplicate"
  }
```

### Intent Parsing (Claude Haiku)

Translates natural language into structured search parameters:

```
Input:  "유튜브에서 파이썬 비동기 강의 10개 찾아줘"
Output: { "search_query": "파이썬 비동기", "limit": 10, "confidence": 0.95 }
```

Falls back to raw message on parsing failure. Preserves Korean text.

### API Key Encryption

```
plaintext key ──► AES-GCM(SETTINGS_ENCRYPTION_KEY) ──► base64 ──► DB
DB ──► base64 decode ──► AES-GCM decrypt ──► plaintext key ──► API call
```

---

## 9. Source Adapters

All adapters share the same interface:

```python
class SourceAdapter:
    async def extract(self, url: str) -> ExtractedContent

@dataclass
class ExtractedContent:
    text: str
    title: str
    author: str = ""
    published_at: str | None = None
    source_url: str = ""
    source_type: str = ""
    word_count: int = 0
    domain: str = ""
    timestamps: list[dict] = field(default_factory=list)
    error: str | None = None      # honest failure message
```

### YouTube Adapter — 4-Strategy Fallback Chain

```
Strategy 1: youtube-transcript-api
  Fastest. Works on videos with official captions.
  Falls through: IP blocked, no transcript, API error.

Strategy 1.5: Supadata API
  Handles YouTube IP blocks. Polls every 2s for long videos (max 60s).
  Falls through: API key missing, timeout, error.

Strategy 2: yt-dlp auto-subtitles
  Downloads VTT file, strips markup, deduplicates lines.
  Falls through: no auto-subs, yt-dlp error.

Strategy 3: Groq Whisper STT
  pytubefix downloads lowest-bitrate audio → Groq Whisper transcribes.
  Falls through: GROQ_API_KEY missing, file too large, error.

All fail → ExtractedContent(error="All extraction strategies failed")
          → Candidate with quality_score=0.0, recommendation="review"
```

### Web Adapter

```
1. HTTP GET with user-agent
2. SSRF guard: reject 127.x, 192.168.x, 10.x, 169.254.x
3. trafilatura: clean article text extraction from HTML
4. Open Graph metadata: author, publish date
```

### PDF Adapter

```
pdfplumber: page-by-page text extraction
Concatenates with page break markers
```

### Local File Adapter

```
Supported: .txt, .md, .docx, .xlsx, .csv, .json
.docx: python-docx paragraph extraction
.xlsx: openpyxl cell extraction (sheet by sheet)
```

### Source Scope Classification

```python
def classify_source_scope(source_type: str, url: str) -> str:
    if source_type == "youtube":
        if has_video_id(url):
            return "direct_resource"     # single video → direct extraction
        return "discovery_provider"      # channel/playlist/search → enumerate first
    return "direct_resource"             # web, pdf, local always direct
```

---

## 10. API Reference

All endpoints require `Authorization: Bearer <supabase_jwt>` except `/health`.

### Health
| Method | Path | Response |
|--------|------|---------|
| GET | `/health` | `{"status": "ok"}` |

### Topics
| Method | Path | Body | Description |
|--------|------|------|-------------|
| GET | `/api/topics` | — | List all topics |
| POST | `/api/topics` | `{label, color?}` | Create topic |
| DELETE | `/api/topics/{id}` | — | Delete topic |

### Sources
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/sources` | List all sources |
| POST | `/api/sources` | Add source `{type, url?, keyword?, topicId?, discoveryMode?, discoveryLimit?}` |
| DELETE | `/api/sources/{id}` | Delete source |
| GET | `/api/sources/{id}/reset` | Reset source to queued |
| POST | `/api/sources/upload` | Upload files (multipart, max 500MB/file) |

### Candidates
| Method | Path | Body | Description |
|--------|------|------|-------------|
| GET | `/api/candidates` | — | List all candidates |
| POST | `/api/candidates/approve` | `{ids: []}` | Bulk approve → queue Note Gen |
| POST | `/api/candidates/reject` | `{ids: []}` | Bulk reject |

### Jobs
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/jobs` | List all jobs |
| POST | `/api/jobs/{id}/retry` | Re-queue failed job |
| POST | `/api/jobs/{id}/cancel` | Mark job failed |
| DELETE | `/api/jobs/{id}` | Delete job record |

### Notes
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/notes?status=pending` | List notes by status |
| POST | `/api/notes/{id}/approve` | Approve → write to vault_files |
| POST | `/api/notes/{id}/reject` | Reject note |

### Vault
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/vault/tree` | Folder tree of all vault files |
| GET | `/api/vault/file?path=...` | Read single vault file with frontmatter |

### Scheduler
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/scheduler/trigger` | Manually trigger Analysis job |
| GET | `/api/scheduler/status` | Check scheduler running state |

### Dashboard
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/dashboard/stats` | Pending counts, notes today, active jobs |
| GET | `/api/dashboard/activity` | Recent processing activity log |

### YouTube
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/youtube/search?q=&limit=` | Search YouTube |
| POST | `/api/youtube/parse-intent` | NLU: message → search params |
| POST | `/api/youtube/notes/batch` | Create notes for list of video URLs |

### Settings
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/settings` | Get user settings |
| POST | `/api/settings/{section}` | Update settings section |

---

## 11. Authentication & Security

### JWT Verification Flow

```
Request: Authorization: Bearer <token>

1. Extract token from header
2. Fetch JWKS: GET {SUPABASE_URL}/auth/v1/.well-known/jwks.json
3. Select key by kid claim
4. Verify signature: ES256
5. Validate: aud == "authenticated", exp > now()
6. Extract sub (UUID) → user_id for all DB queries
7. Return 401 on any failure
```

### Security Layers

| Layer | Measure |
|-------|---------|
| Authentication | Supabase JWT + JWKS (ES256) |
| SSRF | Web adapter blocks private IPs, loopback, cloud metadata |
| SQL Injection | Parameterized queries only — no string concatenation |
| Path Traversal | Upload validates resolved paths stay in allowed directory |
| Secrets at rest | AES-GCM encryption for stored API keys |
| Rate limiting | 200 req/min per IP (SlowAPI) |
| XSS | DOMPurify sanitization in frontend |
| CORS | Explicit allowlist via ALLOWED_ORIGINS |
| Error leakage | Sanitized 500 responses — no stack traces to client |

---

## 12. Deployment & CI/CD

### Environments

| Environment | URL | Deploy Trigger |
|------------|-----|----------------|
| Staging | `https://synker-frontend-staging.up.railway.app` | Push to `synker-v1` |
| Production | TBD | Manual approval |

### Railway Configuration

```json
{
  "deploy": {
    "startCommand": "/app/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $PORT",
    "healthcheckPath": "/health"
  }
}
```

Build: `uv sync` installs dependencies from lockfile. Railway healthchecks `/health` after deploy.

### Required Environment Variables

```bash
# Supabase
SUPABASE_URL=
SUPABASE_JWT_SECRET=
DATABASE_URL=

# AI (at least one required)
ANTHROPIC_API_KEY=
OPENAI_API_KEY=

# Optional
GROQ_API_KEY=             # Whisper STT fallback
SUPADATA_API_KEY=         # YouTube transcript service
SETTINGS_ENCRYPTION_KEY=  # AES key for stored API keys
SENTRY_DSN=

# Worker
WORKER_ENABLED=true
WORKER_POLL_SECONDS=10
WORKER_CONCURRENCY=3
JOB_STALE_SECONDS=300
ALLOWED_ORIGINS=https://synker-frontend-staging.up.railway.app
```

### GitHub Actions CI

```yaml
# Runs on every push / PR

backend-tests:
  - python 3.12 + uv
  - ruff check .       # lint
  - pytest -q          # unit tests

frontend-tests:
  - node 20 + pnpm
  - pnpm install
  - pnpm test --run    # vitest
```

---

## 13. Development Workflow

### Local Setup

```bash
# Backend
cd backend
uv sync
cp ../.env.example .env    # fill in values
uv run uvicorn app.main:app --reload --port 8000

# Frontend
cd "AI Knowledge Curation Platform"
pnpm install
cp .env.example .env.local  # fill in VITE_SUPABASE_URL + VITE_SUPABASE_ANON_KEY
pnpm dev                    # http://localhost:5173
```

### Verification Commands

```bash
# Backend
cd backend
uv run ruff check .          # lint
uv run mypy app              # type check
uv run pytest -q             # tests

# Frontend
cd "AI Knowledge Curation Platform"
pnpm test --run              # unit tests
```

### Feature Development Pipeline

Every non-trivial change follows the Claude Harness v4 agent pipeline (see `CLAUDE.md`, `.claude/agents/`, `.claude/commands/`). Run it with `/autopilot <task>`.

```
0. orchestrator (main session) → runs the grill-me interview with the user; never writes app code
1. spec-interviewer   → .planning/PRD.md and atomic .planning/tasks/task-NN-brief.md
2. ui-taste-designer | clean-implementer → one brief at a time, test first (IMPLEMENTED / FAILED / BLOCKED)
3. reviewbench-judge  → read-only reviewer
                        Gate 1: scripts/verify/verify_feature.py
                        Gate 2: diff vs brief
                        Gate 3: scripts/harness/eval-reviewbench.py (F0.5 >= 0.85, 0 critical)
4. devops-shipper     → licence scan, staging E2E, then stops for user approval before any push, migration or deploy
```

Rules:
- The implementer never reviews its own work. A BLOCKED gate (for example `uv` missing) is never reported as PASS.
- Runtime verification must target the staging URL. Localhost evidence is not accepted.
- Budget is $3.00 per task (`.planning/budget-ledger.json`). Evidence goes in `verification/evidence/<run-id>/`.
- Hooks in `.claude/hooks/` block force-push, hard reset, `.env` access, secrets in commands or file content,
  Supabase db reset/push, and edits to the harness config.
- DONE is declared only when all applicable gates pass.

### Git Convention

```
Branch:  feature/<name> | fix/<name> | refactor/<name>
Commit:  <type>: <imperative description>
Types:   feat | fix | refactor | docs | test | chore | perf | ci
```

---

## 14. Technology Stack

### Backend

| Component | Technology | Version |
|-----------|-----------|---------|
| Framework | FastAPI | 0.115+ |
| Server | Uvicorn | 0.32+ |
| DB driver | asyncpg | 0.30+ |
| Auth | PyJWT + Supabase JWKS | 2.9+ |
| Crypto | cryptography (AES-GCM) | 43.0+ |
| Rate limiting | slowapi | 0.1.9+ |
| Error tracking | sentry-sdk | 2.0+ |
| HTTP client | httpx | 0.28+ |
| Web extraction | trafilatura | 2.0+ |
| PDF | pdfplumber | 0.11+ |
| YouTube transcripts | youtube-transcript-api | 0.6+ |
| YouTube download | yt-dlp | 2026.8+ |
| YouTube audio | pytubefix | 8.0+ |
| Speech-to-text | Groq Whisper | 0.11+ |
| AI (primary) | anthropic | 0.40+ |
| AI (fallback) | openai | 1.50+ |
| Linting | ruff | 0.9+ |
| Type checking | mypy | 1.13+ |
| Testing | pytest | 8.3+ |
| Package manager | uv | latest |

### Frontend

| Component | Technology | Version |
|-----------|-----------|---------|
| UI framework | React | 18.3.1 |
| Language | TypeScript | 5.x |
| Build tool | Vite | 6.3.5 |
| Styling | Tailwind CSS | 4.1.12 |
| Components | shadcn/ui (Radix UI) | latest |
| Icons | Lucide React | 0.487.0 |
| Auth | @supabase/supabase-js | 2.49+ |
| Router | React Router | 7.13.0 |
| Forms | React Hook Form | 7.55.0 |
| Notifications | Sonner | 2.0.3 |
| Charts | Recharts | 2.15.2 |
| Animation | Motion | 12.23.24 |
| HTML sanitize | DOMPurify | 3.4+ |
| Testing | Vitest + JSDOM | 3.0+ |
| Package manager | pnpm | latest |

### Infrastructure

| Component | Technology |
|-----------|-----------|
| Backend hosting | Railway |
| Frontend hosting | Railway |
| Database | Supabase (PostgreSQL) |
| Auth service | Supabase Auth |
| CI/CD | GitHub Actions |
| Version control | GitHub |

---

*Last updated: 2026-10-22 | Branch: synker-v1*
