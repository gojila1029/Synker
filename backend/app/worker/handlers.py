"""Job-type handlers.

A handler does the real work for one job and returns a short, truthful result
summary. Handlers report progress via the injected async callback and MUST NOT
fabricate notes, candidates, or citations — if there is nothing real to do, they
say so honestly. The content pipeline (source adapters, extraction, note
generation) is not built yet, so the discovery handler currently performs an
honest no-op: it drives the lifecycle so status is observable, and reports that
no source adapters are configured.
"""
import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

# pct -> None. Persists progress + heartbeat for the running job.
ProgressFn = Callable[[int], Awaitable[None]]

# (job_row, progress) -> result summary string.
Handler = Callable[[dict[str, Any], ProgressFn], Awaitable[str]]

# Seconds between discovery progress steps. Kept short; tests set it to 0.
STEP_DELAY_SECONDS = 1.2


async def _discovery_handler(job: dict[str, Any], progress: ProgressFn) -> str:
    """Honest discovery pass. No source adapters exist yet, so nothing is
    ingested and nothing is fabricated — the job simply runs to completion and
    reports the truth."""
    await progress(20)
    await asyncio.sleep(STEP_DELAY_SECONDS)
    await progress(60)
    await asyncio.sleep(STEP_DELAY_SECONDS)
    await progress(90)
    await asyncio.sleep(STEP_DELAY_SECONDS)
    return "0 new candidates — no source adapters configured yet"


HANDLERS: dict[str, Handler] = {
    "Analysis": _discovery_handler,
}


def get_handler(job_type: str) -> Handler | None:
    return HANDLERS.get(job_type)
