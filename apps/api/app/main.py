"""FastAPI app entry. Thin — all logic lives in routers + pipeline."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth.repository import init_auth_db
from .auth.security import initialize_signing_secret
from .config import log_provider_validation, settings
from .db import init_db
from .routers import auth, generate, jobs
from .topic_intelligence.router import router as topic_intelligence_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Phase 2A: additive topic-intelligence tables. Creates only what is missing;
    # never touches the existing Job table.
    from .topic_intelligence.repository import init_ti_db

    init_ti_db()
    init_auth_db()
    initialize_signing_secret()
    if not settings().auth_required:
        print(
            "[auth] ⚠⚠⚠ WARNING: AUTHENTICATION IS DISABLED; PROTECTED ROUTES "
            "ARE PUBLIC ⚠⚠⚠",
            flush=True,
        )
    log_provider_validation()       # non-fatal: warn on incomplete provider config
    yield


app = FastAPI(title="Shorts Factory API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],   # Next.js dashboard
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(generate.router)
app.include_router(jobs.router)
app.include_router(topic_intelligence_router)
app.include_router(auth.router)


@app.get("/health")
def health():
    return {"ok": True}
