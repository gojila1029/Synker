import logging
import os
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.core.config import settings
from app.db.client import close_pool, get_pool
from app.api.routes import (
    health,
    dashboard,
    topics,
    sources,
    candidates,
    jobs,
    notes,
    vault,
    settings_route,
    scheduler,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
_log = logging.getLogger("synker")

_sentry_dsn = os.getenv("SENTRY_DSN")
if _sentry_dsn:
    sentry_sdk.init(dsn=_sentry_dsn, traces_sample_rate=0.1)

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    yield
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
    allow_headers=["Authorization", "Content-Type"],
)


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
