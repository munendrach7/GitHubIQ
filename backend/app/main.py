"""GitHubIQ FastAPI application entry point."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .llm import llm_available
from .messaging import servicebus_enabled
from .routers import analyze, auth, tts
from .storage import get_store

logging.basicConfig(level=logging.INFO)
# Quiet the very chatty Azure SDK HTTP request/response logging (Cosmos, Service
# Bus, Identity); our own app logs stay at INFO.
logging.getLogger("azure").setLevel(logging.WARNING)

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(analyze.router)
app.include_router(tts.router)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.environment,
        "llm_configured": llm_available(),
        "speech_configured": settings.speech_configured,
        "store": type(get_store()).__name__,
        "async_dispatch": servicebus_enabled(),
        "managed_identity": settings.use_managed_identity,
    }


@app.get("/")
def root() -> dict:
    return {"service": settings.app_name, "docs": "/docs"}
