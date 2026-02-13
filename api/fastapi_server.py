"""Phase-6 FastAPI server (OpenAI-compatible incremental layer)."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
import os
import time
from typing import Any
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_utils.tasks import repeat_every

from denis_unified_v1.api.openai_compatible import DenisRuntime, build_openai_router
from denis_unified_v1.api.memory_handler import build_memory_router
from denis_unified_v1.api.query_interface import build_query_router
from denis_unified_v1.api.provider_config_handler import build_provider_config_router
from denis_unified_v1.api.voice_handler import build_voice_router
from denis_unified_v1.api.websocket_handler import build_ws_router
from denis_unified_v1.api.api_registry import build_registry_router
from denis_unified_v1.autopoiesis.dashboard import (
    build_router as build_autopoiesis_router,
)
from denis_unified_v1.feature_flags import load_feature_flags
from denis_unified_v1.metagraph.dashboard import build_router as build_metagraph_router
from denis_unified_v1.api.metacognitive_api import router as metacognitive_router
from denis_unified_v1.observability.tracing import setup_tracing
from denis_unified_v1.observability.metrics import setup_metrics


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class InMemoryRateLimiter:
    def __init__(self, limit_per_minute: int = 100) -> None:
        self.limit_per_minute = limit_per_minute
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> tuple[bool, int]:
        now = time.time()
        window = 60.0
        q = self.hits[key]
        while q and q[0] < now - window:
            q.popleft()
        if len(q) >= self.limit_per_minute:
            return False, len(q)
        q.append(now)
        return True, len(q)


def create_app() -> FastAPI:
    app = FastAPI(title="Denis Cognitive Engine", version="1.0.0")
    flags = load_feature_flags()
    runtime = DenisRuntime()
    limiter = InMemoryRateLimiter(
        limit_per_minute=int(os.getenv("DENIS_RATE_LIMIT_PER_MIN", "100"))
    )
    auth_token = (os.getenv("DENIS_API_BEARER_TOKEN") or "").strip()

    @app.on_event("startup")
    @repeat_every(seconds=60)  # Check every minute
    async def check_anomalies_background():
        """Background task para chequear anomalías."""
        from denis_unified_v1.observability.anomaly_detector import AlertManager
        
        alert_manager = AlertManager()
        await alert_manager.check_and_alert()

    raw_origins = os.getenv("DENIS_CORS_ORIGINS", "*")
    cors_origins = [x.strip() for x in raw_origins.split(",") if x.strip()]
    allow_all = cors_origins == ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if allow_all else cors_origins,
        allow_credentials=False if allow_all else True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount static files
    from fastapi.staticfiles import StaticFiles
    app.mount("/static", StaticFiles(directory="/media/jotah/SSD_denis/home_jotah/denis_unified_v1/api/static"), name="static")

    @app.middleware("http")
    async def trace_and_security_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        ip = request.client.host if request.client else "unknown"

        if auth_token:
            auth_header = request.headers.get("authorization", "")
            if auth_header != f"Bearer {auth_token}":
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": "unauthorized",
                        "request_id": request_id,
                        "timestamp_utc": _utc_now(),
                    },
                )

        ok, used = limiter.check(ip)
        if not ok:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limited",
                    "request_id": request_id,
                    "hits_last_minute": used,
                    "timestamp_utc": _utc_now(),
                },
            )

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)
        response.headers["x-request-id"] = request_id
        response.headers["x-duration-ms"] = str(duration_ms)
        return response

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": "unified-v1",
            "timestamp_utc": _utc_now(),
            "feature_flags": flags.as_dict(),
            "components": {
                "openai_compatible": True,
                "query_interface": True,
                "websocket_events": True,
                "voice_pipeline": flags.denis_use_voice_pipeline,
                "memory_unified": flags.denis_use_memory_unified,
                "atlas_bridge": flags.denis_use_atlas,
                "cognitive_router": True,
                "inference_router": flags.denis_use_inference_router,
            },
        }

    app.include_router(build_openai_router(runtime))
    app.include_router(build_query_router())
    app.include_router(build_provider_config_router())
    app.include_router(build_ws_router())
    if flags.denis_use_voice_pipeline:
        app.include_router(build_voice_router())
    if flags.denis_use_memory_unified:
        app.include_router(build_memory_router())
    metagraph_router = build_metagraph_router()
    if metagraph_router is not None:
        app.include_router(metagraph_router)
    autopoiesis_router = build_autopoiesis_router()
    if autopoiesis_router is not None:
        app.include_router(autopoiesis_router)

    # API Metacognitiva
    app.include_router(metacognitive_router)

    # API Registry Router
    registry_router = build_registry_router()
    if registry_router is not None:
        app.include_router(registry_router, prefix="/registry")

    return app


# Setup tracing (before app creation)
if os.getenv("ENABLE_TRACING", "true").lower() == "true":
    setup_tracing()

app = create_app()

# Setup metrics
setup_metrics(app)
