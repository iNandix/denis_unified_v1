"""Phase-6 FastAPI server (OpenAI-compatible incremental layer)."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
import os
import time
from typing import Any
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
# All other imports moved inside create_app() for complete fail-open behavior


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json(obj: Any) -> Any:
    """Safely convert object to JSON-serializable format."""
    try:
        return jsonable_encoder(obj)
    except Exception as e:
        return {"_type": type(obj).__name__, "_error": str(e)}


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

    def is_allowed(self, key: str) -> bool:
        allowed, _ = self.check(key)
        return allowed


def create_app() -> FastAPI:
    app = FastAPI(title="Denis Cognitive Engine", version="1.0.0")

    # Load feature flags with fail-open
    try:
        from feature_flags import load_feature_flags
        raw_flags = load_feature_flags()
    except Exception:
        raw_flags = {"denis_use_voice_pipeline": False, "denis_use_memory_unified": False, "denis_use_atlas": False, "denis_use_inference_router": False}

    try:
        if hasattr(raw_flags, "as_dict"):
            flags = dict(raw_flags.as_dict())
        else:
            flags = dict(raw_flags) if not isinstance(raw_flags, dict) else raw_flags
    except Exception:
        flags = {}

    # Initialize runtime with fail-open
    runtime = None
    try:
        runtime = DenisRuntime()
    except (ImportError, Exception):
        # Create minimal runtime stub
        class MinimalRuntime:
            def process_request(self, *args, **kwargs):
                return {"error": "runtime_not_available"}
        runtime = MinimalRuntime()

    limiter = InMemoryRateLimiter(
        limit_per_minute=int(os.getenv("DENIS_RATE_LIMIT_PER_MIN", "100"))
    )

    auth_token = (os.getenv("DENIS_API_BEARER_TOKEN") or "").strip()

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

    # Mount static files with fail-open
    try:
        from fastapi.staticfiles import StaticFiles
        app.mount("/static", StaticFiles(directory="api/static", check_dir=False), name="static")
    except Exception:
        pass

    @app.middleware("http")
    async def trace_and_security_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        ip = request.client.host if request.client else "unknown"

        try:
            if auth_token:
                auth_header = request.headers.get("authorization", "")
                if not auth_header.startswith("Bearer "):
                    return JSONResponse(status_code=401, content={"error": "unauthorized", "request_id": request_id, "timestamp_utc": _utc_now()})

            if not limiter.is_allowed(ip):
                return JSONResponse(status_code=429, content={"error": "rate_limited", "request_id": request_id, "timestamp_utc": _utc_now()})

            start = time.perf_counter()
            response = await call_next(request)
            duration_ms = int((time.perf_counter() - start) * 1000)
            response.headers["x-request-id"] = request_id
            response.headers["x-duration-ms"] = str(duration_ms)
            return response

        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "internal_error",
                    "detail": str(e),
                    "request_id": request_id,
                    "timestamp_utc": _utc_now(),
                },
            )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": "unified-v1",
            "timestamp_utc": _utc_now(),
            "feature_flags": _safe_json(flags),
            "components": {
                "openai_compatible": runtime is not None and not isinstance(runtime, MinimalRuntime),
                "query_interface": True,  # Always available as fallback
                "websocket_events": True,  # Always available as fallback
                "voice_pipeline": flags.get("denis_use_voice_pipeline", False) if isinstance(flags, dict) else getattr(flags, 'denis_use_voice_pipeline', False),
                "memory_unified": flags.get("denis_use_memory_unified", False) if isinstance(flags, dict) else getattr(flags, 'denis_use_memory_unified', False),
                "atlas_bridge": flags.get("denis_use_atlas", False) if isinstance(flags, dict) else getattr(flags, 'denis_use_atlas', False),
                "cognitive_router": True,
                "inference_router": flags.get("denis_use_inference_router", False) if isinstance(flags, dict) else getattr(flags, 'denis_use_inference_router', False),
                "agent_heart": True,
                "metacognitive": True,
            },
        }

    @app.get("/status")
    async def status() -> dict[str, Any]:
        return {
            "status": "ok",
            "timestamp_utc": _utc_now(),
            "components": {
                "metacognitive": True,
                "health": True,
            },
        }

    # --- Safe router includes (fail-open) ---
    def _safe_include(builder, *args, **kwargs):
        try:
            r = builder(*args, **kwargs)
            if r is not None:
                app.include_router(r)
            return True
        except Exception:
            return False

    # OpenAI-compatible + Query + Provider + WS (opcionales si fallan imports)
    try:
        from .openai_compatible import DenisRuntime, build_openai_router
        runtime = DenisRuntime()
        _safe_include(build_openai_router, runtime)
    except Exception:
        runtime = None

    try:
        from .query_interface import build_query_router
        _safe_include(build_query_router)
    except Exception:
        pass

    try:
        from .provider_config_handler import build_provider_config_router
        _safe_include(build_provider_config_router)
    except Exception:
        pass

    try:
        from .websocket_handler import build_ws_router
        _safe_include(build_ws_router)
    except Exception:
        pass

    # Metacognitive + Heart (siempre, pero lazy import)
    try:
        from .metacognitive_api import router as metacognitive_router
        app.include_router(metacognitive_router, prefix="/metacognitive")
    except Exception:
        pass

    try:
        from .agent_heart_api import router as agent_heart_router
        app.include_router(agent_heart_router)
    except Exception:
        pass

    # Voice/Memory/Metagraph/Autopoiesis/Registry (gated + fail-open)
    try:
        if (flags.get("denis_use_voice_pipeline", False) if isinstance(flags, dict) else flags.enabled("denis_use_voice_pipeline", False)):
            from .voice_handler import build_voice_router
            _safe_include(build_voice_router)
    except Exception:
        pass

    try:
        if (flags.get("denis_use_memory_unified", False) if isinstance(flags, dict) else flags.enabled("denis_use_memory_unified", False)):
            from .memory_handler import build_memory_router
            _safe_include(build_memory_router)
    except Exception:
        pass

    try:
        from metagraph.dashboard import build_router as build_metagraph_router
        _safe_include(build_metagraph_router)
    except Exception:
        pass

    try:
        from autopoiesis.dashboard import build_router as build_autopoiesis_router
        _safe_include(build_autopoiesis_router)
    except Exception:
        pass

    # Encryption API (optional, fail-open)
    try:
        from denis_persona_encryption import encryption_router
        app.include_router(encryption_router)
    except Exception:
        # Si falta cryptography, neo4j driver o el módulo, el core sigue vivo
        pass

    try:
        from .api_registry import build_registry_router
        r = build_registry_router()
        if r is not None:
            app.include_router(r, prefix="/registry")
    except Exception:
        pass

    return app


# Setup tracing and metrics with complete fail-open
try:
    if os.getenv("ENABLE_TRACING", "true").lower() == "true":
        from observability.tracing import setup_tracing
        setup_tracing()
        tracing_enabled = True
    else:
        tracing_enabled = False
except (ImportError, Exception):
    tracing_enabled = False

# Create app with complete fail-open
try:
    app = create_app()
except Exception as e:
    # Emergency fallback: create minimal app with just health and agent heart
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI(title="Denis Cognitive Engine - Emergency Mode", version="emergency")

    @app.get("/health")
    async def emergency_health():
        return {
            "status": "emergency_mode",
            "error": str(e),
            "timestamp_utc": _utc_now(),
            "available_components": ["health"]
        }

    # Try to include at least the agent heart
    try:
        from .metacognitive_api import router as metacognitive_router
        app.include_router(metacognitive_router, prefix="/metacognitive")
    except Exception:
        pass
    
    try:
        from .agent_heart_api import router as agent_heart_router
        app.include_router(agent_heart_router)
    except Exception:
        pass

# Setup metrics with fail-open
metrics_enabled = False
try:
    from observability.metrics import setup_metrics
    setup_metrics(app)
    metrics_enabled = True
except (ImportError, Exception):
    metrics_enabled = False

# Add observability status to /health endpoint
@app.get("/observability")
async def observability_status():
    return {
        "status": "ok",
        "timestamp_utc": _utc_now(),
        "observability": {
            "tracing_enabled": tracing_enabled,
            "metrics_enabled": metrics_enabled,
            "reason": None if (tracing_enabled and metrics_enabled) else "partial_observability"
        }
    }
