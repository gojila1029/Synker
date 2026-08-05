-- Worker heartbeat + claim ownership for the in-process job worker (SYN-V5-002).
-- Additive and nullable: safe to apply to a live database with running jobs.
--
-- Apply with:  supabase db push   (or via the Supabase SQL editor / MCP)
-- Enable the worker only AFTER this migration is applied: set WORKER_ENABLED=true.

ALTER TABLE public.jobs ADD COLUMN IF NOT EXISTS heartbeat_at timestamptz;
ALTER TABLE public.jobs ADD COLUMN IF NOT EXISTS claimed_by   text;

-- Supports the claim query: filter by status, take the oldest queued job first.
CREATE INDEX IF NOT EXISTS idx_jobs_claim ON public.jobs (status, started_at);
