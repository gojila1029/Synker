# Plan: Synker — AI Knowledge Curation Platform UI (Backend-Integrated)

## Context

Build the complete multi-screen React UI for **Synker**, wired to a FastAPI Python backend running at `http://localhost:8000`. The frontend fetches real data, posts real actions, and handles loading and error states throughout. When the backend is unavailable, realistic seed data is shown so the UI remains reviewable in isolation.

Stack per the agreed spec:
- React + TypeScript + Vite (frontend)
- FastAPI (backend, local HTTP)
- Supabase PostgreSQL (remote DB, synced via backend)
- Claude + OpenAI with automatic fallback (AI providers)

---

## Aesthetic stance

**Light, user-friendly productivity tool.** Soft warm-white canvas, white cards, dark slate sidebar. Professional and approachable — not AI-branded.

**Typography:**
- `Inter` — UI chrome, headings, body (readable and friendly)
- `JetBrains Mono` — file paths, job IDs, API keys only

**Token values (theme.css `:root`):**
```css
--background: #f4f6f9;
--foreground: #111827;
--card: #ffffff;
--primary: #2563eb;        /* clean blue — not violet */
--secondary: #f1f5f9;
--muted: #f1f5f9;
--muted-foreground: #64748b;
--accent: #eff6ff;
--border: #e2e8f0;
--ring: #93c5fd;
--radius: 0.75rem;
--sidebar: #1e293b;        /* dark slate sidebar */
```
`.dark` block and `@theme inline` mappings preserved unchanged.

---

## API integration architecture

### Base URL
```ts
const BASE = "http://localhost:8000"
```

### Service layer — `src/services/api.ts`
Typed fetch wrappers with 3 s timeout. On failure, falls back to seed data silently and sets `_isDemo = true`.

```ts
export const api = {
  dashboard: { getStats, getActivity },
  topics:    { list, create, delete },
  sources:   { list, add, delete },
  candidates:{ list, approve, reject },
  jobs:      { list, retry },
  notes:     { list, approve, reject },
  vault:     { tree, file },
  settings:  { get, update },
  scheduler: { trigger },
}
```

### Data-fetching hook — `src/hooks/useApi.ts`
Generic `useApi<T>(fetcher, fallback)` returning `{ data, loading, error, refetch }`.

### Seed data — `src/data/seed.ts`
Realistic fallback data (Indian Insurance / Claude AI / Backend Dev topics, real-looking job IDs, actual note content). Shapes match API response types exactly.

### Types — `src/types/index.ts`
Shared TypeScript interfaces for all entities (`DashboardStats`, `Source`, `Topic`, `Candidate`, `Job`, `Note`, `VaultNode`, `VaultFile`, `Settings`).

---

## Screens

### 1. Dashboard
- "Good morning 👋" header + last sync timestamp + **Run Discovery Now** button → `api.scheduler.trigger()`
- 4 KPI tiles: Pending Approvals, Active Jobs, Notes Published Today, Sources Indexed
- 9-stage pipeline swimlane: Discover → Analyze → Approve → Extract → Transcribe → Generate → Verify → Graphify → Cleanup
- Two-column lower section: Recent Activity feed + Needs Your Approval quick-list (top 3 candidates, inline Approve/Skip)
- Failures panel with per-job Retry button → `api.jobs.retry(id)`

### 2. Sources
- Discovery Topics sub-panel: topic color chips with delete; inline "Add a topic…" input (Enter or + button)
- Pill-style filter tabs: All / YouTube / Web / PDF / Local Folder
- Source card grid: type icon, title, URL, topic chip, status badge, schedule label, hover-reveal delete
- Add Source modal: URL/path, source type select, topic select (optional)

### 3. Candidate Approval
- Topic-group headers with colored dot and count pill; "Uncategorised" bucket for unmatched sources
- Per-candidate row: checkbox, title, source info, Recommendation badge (Process/Merge/Skip/Review), status badge
- Quality / Confidence / Duplicate shown as labeled progress bars (more readable than raw numbers)
- Expected notes count + estimated token cost
- **Summary** toggle per row — expands AI summary + extracted topic chips
- Bulk action bar: Select All, Approve (N), Reject (N) — disabled when nothing selected

### 4. Processing Jobs
- Pill-style filter tabs with counts: All / Running / Queued / Completed / Failed
- Table: Source title + job ID, Type, Status badge, Progress bar (animated for running), Started, Duration, action
- Running jobs poll every 5 s via `setInterval` in `useEffect`; polling stops when no running jobs remain
- Failed jobs show error text inline + Retry button
- Completed jobs show artifact filename in blue mono

### 5. Knowledge Review
- Split layout: left note list (72-wide) + right preview panel
- Note list: AI action badge (Created/Merged/Updated/Skipped), quality progress bar, duplicate warning badge
- Preview: note title + source, Accept & Save / Reject buttons, duplicate warning banner (Merge / Keep Both)
- Note content rendered as HTML via regex-based Markdown converter
- "Why did the AI choose this action?" accordion → `similarityReasoning`
- Right meta column: YAML frontmatter table, citations list, `[[wiki links]]` chips

### 6. Vault Browser
- Left file-tree: collapsible folders, file icons, search filter; selected file highlighted in blue
- Main area: breadcrumb path, frontmatter property table, Markdown content render
- Right meta rail: Words, Backlinks, Modified date, graph node type badge, Cloud-safe / Local only indicator

### 7. Settings
Seven independent sections, each with its own **Save changes** button:

| Section | Fields |
|---|---|
| Vault | Vault name, Vault path (Browse button) |
| AI Providers | Anthropic API key, OpenAI API key, Fallback order display |
| Privacy & Security | PII detection mode (Regex / Local ML), Block insurance client data toggle |
| Discovery Schedule | YouTube interval, Web interval, PDF interval, Local folder debounce |
| File Cleanup | Per-type policy: YouTube / Web / PDF / Local (Keep / ZIP / Delete) |
| Notifications | Desktop toggle, In-app toggle, Email toggle; email provider + address (shown only when email is on) |
| Team | Tier selector (Single / Small / Larger); member table shown for team tiers |

> **Removed fields:** Local Ollama URL (AI Providers) and Default interval (Discovery Schedule) — not required.

---

## File layout

```
src/
├── app/App.tsx          ← all 7 screens + shell, ~900 lines
├── services/api.ts      ← typed fetch wrappers + demo-mode flag
├── hooks/useApi.ts      ← generic data-fetching hook
├── types/index.ts       ← shared TypeScript interfaces
├── data/seed.ts         ← offline fallback data
└── styles/
    ├── fonts.css        ← Inter + JetBrains Mono (Google Fonts)
    └── theme.css        ← light theme tokens
```

---

## Error and loading patterns

- **Loading**: skeleton shimmer (`animate-pulse bg-slate-100`) matching the layout being loaded
- **Offline / backend down**: seed data shown silently; "Demo mode" + WifiOff icon in sidebar footer
- **Connected**: "Connected · localhost:8000" + Wifi icon in sidebar footer
- **Mutation success**: `sonner` `toast.success(…)` + list refetch
- **Mutation failure**: `toast.error(…)` — no silent failures

---

## API endpoint reference

| Priority | Endpoint | Method | Screen |
|---|---|---|---|
| 1 | `/api/dashboard/stats` | GET | Dashboard |
| 1 | `/api/dashboard/activity` | GET | Dashboard |
| 2 | `/api/topics` | GET, POST, DELETE | Sources, Candidates |
| 2 | `/api/sources` | GET, POST, DELETE | Sources |
| 3 | `/api/candidates` | GET | Candidates |
| 3 | `/api/candidates/approve` | POST | Candidates |
| 3 | `/api/candidates/reject` | POST | Candidates |
| 4 | `/api/jobs` | GET | Jobs |
| 4 | `/api/jobs/{id}/retry` | POST | Jobs |
| 5 | `/api/notes` | GET | Knowledge Review |
| 5 | `/api/notes/{id}/approve` | POST | Knowledge Review |
| 5 | `/api/notes/{id}/reject` | POST | Knowledge Review |
| 6 | `/api/vault/tree` | GET | Vault Browser |
| 6 | `/api/vault/file` | GET | Vault Browser |
| 7 | `/api/settings` | GET, PATCH | Settings |
| 7 | `/api/scheduler/trigger` | POST | Dashboard |

---

## Verification checklist

1. All 7 nav screens switch and render correctly
2. Each screen shows skeleton while loading, then data (or seed if backend is down)
3. Candidate accordion toggles independently per row; bulk select/approve/reject work
4. Job filter tabs filter correctly; running jobs poll every 5 s; polling stops when idle
5. Note selection updates Knowledge Review preview; Accept/Reject call API and refetch
6. Vault tree: folder expand/collapse, file selection, search filter all work
7. Settings: each section saves independently with a toast; email fields appear only when email toggle is on
8. "Demo mode" badge appears in sidebar when backend is unreachable
9. Local Ollama URL field is absent from AI Providers
10. Default interval field is absent from Discovery Schedule
