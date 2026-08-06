# Follow-up: Local Backend + Tunnel Setup

## Goal
Connect the deployed Railway frontend to your local machine so that:
- Browse button opens your local folder picker
- Notes are written directly to your local Obsidian vault
- No re-authentication ever needed

## How it works

```
Browser (Railway frontend) ──► tunnel URL ──► your local machine ──► local backend (port 8000)
                                                                              │
                                                                     your local vault folder
```

---

## Steps

### Step 1 — Get a stable public tunnel URL (ngrok free static domain)

1. Sign up at https://ngrok.com (free)
2. You get one free static domain (e.g. `your-name.ngrok-free.app`) — never changes
3. Install ngrok on Windows: `winget install ngrok`
4. Authenticate: `ngrok config add-authtoken YOUR_TOKEN`
5. Run: `ngrok http --domain=your-name.ngrok-free.app 8000`

### Step 2 — Update local backend CORS

Add the Railway frontend to your local backend's allowed origins.
Edit `backend/.env` (or set environment variable):

```
CORS_ORIGINS=http://localhost:5173,https://synker-frontend-production.up.railway.app
```

### Step 3 — Update Railway frontend env var

In Railway → synker-frontend service → Variables, set:

```
VITE_API_BASE=https://your-name.ngrok-free.app
```

This makes the deployed frontend talk to your local backend instead of the Railway backend.

### Step 4 — Start everything locally

```powershell
# Terminal 1 — backend
cd backend
.venv\Scripts\activate
uvicorn app.main:app --port 8000

# Terminal 2 — tunnel
ngrok http --domain=your-name.ngrok-free.app 8000
```

---

## Result

Open `https://synker-frontend-production.up.railway.app` in any browser:
- Browse button opens your local folder picker (native OS dialog)
- Notes write directly to your local Obsidian vault path
- No re-authentication ever needed across sessions

---

## Notes

- The Railway backend (`adaptable-charm`) stays running but is no longer used by the frontend once VITE_API_BASE is updated to the tunnel URL
- If ngrok is not running, the frontend falls back to demo mode (seed data shown)
- To switch back to the Railway backend, revert VITE_API_BASE to `https://adaptable-charm-production-ed58.up.railway.app`
- Step 2 (CORS) and Step 3 (Railway env var) can be done any time — ready and waiting for when you set up ngrok

---

# Full Pipeline Implementation Plan (Phases 1–4)

## Current State

| Feature | Status | Gap |
|---------|--------|-----|
| Dashboard | Ready | Shows zeros until pipeline runs |
| Sources | Ready | CRUD works; no actual scraping yet |
| Jobs | Partial | Worker runs but all handlers are no-ops |
| Approval (Candidates) | Ready | UI works; candidates never generated |
| Knowledge (Notes) | Ready | UI works; notes never generated |
| Vault | Broken | `content` + `frontmatter` columns missing from DB schema |
| Settings | Ready | Fully working |

---

## Phase 1 — Fix the vault DB bug (1 day)

Apply a migration to add the missing `content` and `frontmatter` columns to the `vault_files` table. This is the only outright bug — everything else is missing features, not broken code.

---

## Phase 2 — Source adapters (3–5 days)

Implement content extraction for initial source types:

- **YouTube** — fetch transcript via `youtube-transcript-api`, extract metadata (title, channel, duration, timestamps)
- **Web pages** — fetch HTML via `httpx`, extract clean text via `trafilatura` or `readability`
- **PDF** — extract text via `pdfplumber` or `pymupdf`
- **Local files** — read `.txt`, `.md`, `.pdf` from the configured vault path

Each adapter normalises to a shared `ExtractedContent` schema (text, title, author, date, source_url, timestamps).

---

## Phase 3 — Job handlers (5–7 days)

Wire up the worker pipeline stage by stage:

1. **Discovery handler** — scan configured sources, create candidate records
2. **Extraction handler** — call the right adapter per source type, store content
3. **Analysis handler** — cluster candidates by topic, score duplicates, flag for approval
4. **Note generation handler** — call Claude/OpenAI with extracted content, produce structured Markdown + frontmatter + citations + wiki links
5. **Verification handler** — quality checks (citation presence, completeness, hallucination flags)
6. **Vault write handler** — write approved notes as `.md` files to the configured vault path

---

## Phase 4 — Vault content persistence (1 day)

After Phase 1 migration, update the vault write handler to store note content and frontmatter back into `vault_files` so the Vault viewer shows real content.

---

## Estimated total: 10–14 days of implementation

**Start with:** Phase 1 (vault schema migration) — 30 minutes, unblocks the Vault screen immediately.
