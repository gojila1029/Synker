import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.api.routes import (
    candidates,
    dashboard,
    health,
    jobs,
    notes,
    scheduler,
    settings_route,
    sources,
    topics,
    vault,
)
from app.core.config import settings
from app.db.client import close_pool, get_pool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s",
)
_log = logging.getLogger("synker")

_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_var.get("-")  # type: ignore[attr-defined]
        return True


for _h in logging.root.handlers:
    _h.addFilter(_RequestIdFilter())

_sentry_dsn = os.getenv("SENTRY_DSN")
if _sentry_dsn:
    sentry_sdk.init(dsn=_sentry_dsn, traces_sample_rate=0.1)

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await get_pool()
        _log.info("DB pool initialized")
    except Exception as exc:  # noqa: BLE001
        _log.warning("DB pool init failed at startup (%s); will retry on first request", exc)

    stop = asyncio.Event()
    worker_tasks: list[asyncio.Task[None]] = []
    if settings.worker_enabled:
        from app.worker.runner import reaper_loop, worker_loop

        worker_tasks = [
            asyncio.create_task(worker_loop(stop)),
            asyncio.create_task(reaper_loop(stop)),
        ]
        _log.info("Job worker enabled")

    try:
        yield
    finally:
        stop.set()
        if worker_tasks:
            await asyncio.gather(*worker_tasks, return_exceptions=True)
        await close_pool()


app = FastAPI(title="Synker API", version="0.1.0", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    token = _request_id_var.set(req_id)
    try:
        response = await call_next(request)
    finally:
        _request_id_var.reset(token)
    response.headers["X-Request-ID"] = req_id
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    _log.error("Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(health.router)
app.include_router(dashboard.router, prefix="/api/dashboard")
app.include_router(topics.router, prefix="/api/topics")
app.include_router(sources.router, prefix="/api/sources")
app.include_router(candidates.router, prefix="/api/candidates")
app.include_router(jobs.router, prefix="/api/jobs")
app.include_router(notes.router, prefix="/api/notes")
app.include_router(vault.router, prefix="/api/vault")
app.include_router(settings_route.router, prefix="/api/settings")
app.include_router(scheduler.router, prefix="/api/scheduler")
