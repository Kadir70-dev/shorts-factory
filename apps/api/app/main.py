"""FastAPI app entry. Thin — all logic lives in routers + pipeline."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import log_provider_validation
from .db import init_db
from .routers import generate, jobs


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
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


@app.get("/health")
def health():
    return {"ok": True}
