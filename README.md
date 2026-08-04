# Synker — AI Knowledge Curation Platform

Converts approved sources (YouTube, web, PDF, local files) into interconnected Obsidian vault notes using AI.

## Prerequisites

- Node.js 18+
- pnpm 9+
- Python 3.12
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Supabase CLI](https://supabase.com/docs/guides/cli) (for migrations)

## Setup

```bash
# 1. Install Python deps
cd backend
uv sync
cd ..

# 2. Install Node deps
npm install                              # installs concurrently at root
pnpm --prefix "AI Knowledge Curation Platform" install

# 3. Configure env vars
cp backend/.env.example backend/.env     # fill in SUPABASE_URL, JWT_SECRET, etc.
cp "AI Knowledge Curation Platform/.env.example" "AI Knowledge Curation Platform/.env.local"
# fill in VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY

# 4. Apply database migration
supabase db push                         # requires supabase login + project linked

# 5. Start everything
npm run dev
```

`npm run dev` starts:
- Backend: FastAPI on http://localhost:8000
- Frontend: Vite dev server on http://localhost:5173

## Verify

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

## Test

```bash
# Backend
cd backend && uv run pytest

# Frontend
cd "AI Knowledge Curation Platform" && pnpm test
```

## Lint & type-check

```bash
cd backend
uv run ruff check app/
uv run mypy app/
```

## Environment variables

### Backend (`backend/.env`)
| Variable | Description |
|---|---|
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_JWT_SECRET` | JWT secret from Supabase dashboard → Settings → API |
| `DATABASE_URL` | Supabase Session Pooler connection string (Transaction mode for async) |
| `CORS_ORIGINS` | Comma-separated allowed origins |

### Frontend (`AI Knowledge Curation Platform/.env.local`)
| Variable | Description |
|---|---|
| `VITE_API_BASE` | Backend URL (default `http://localhost:8000`) |
| `VITE_SUPABASE_URL` | Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Supabase anon/public key (safe to expose) |

> Never put `SUPABASE_JWT_SECRET`, AI provider keys, or service-role keys in any `VITE_*` variable.
