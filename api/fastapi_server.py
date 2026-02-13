"""Phase-6 FastAPI server (OpenAI-compatible incremental layer)."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
import os
import time
import uuid
from typing import Any

from fastapi import FastAPI, Request, APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
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


# Global flags for idempotent setup
tracing_setup_done = False
metrics_setup_done = False


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
    global tracing_setup_done, metrics_setup_done

    app = FastAPI(title="Denis Cognitive Engine", version="1.0.0")

    # Load feature flags with fail-open
    try:
        from feature_flags import load_feature_flags

        raw_flags = load_feature_flags()
    except Exception:
        # Record degradation for missing feature flags
        try:
            from denisunifiedv1.control_plane.registry import (
                get_control_plane_registry,
                DegradationRecord,
            )

            registry = get_control_plane_registry()
            registry.record_degraded(
                DegradationRecord(
                    id="import.openai_compatible.missing",
                    component="api.fastapi_server",
                    severity=3,
                    category="import",
                    reason="missing_module",
                    evidence={"module": "openai_compatible", "error": str(e)},
                    first_seen_utc=time.time(),
                    last_seen_utc=time.time(),
                    count=1,
                )
            )
        except Exception:
            pass

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

        app.mount(
            "/static",
            StaticFiles(directory="api/static", check_dir=False),
            name="static",
        )
    except Exception:
        pass

    @app.middleware("http")
    async def trace_and_security_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        ip = request.client.host if request.client else "unknown"

        try:
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

            if not limiter.is_allowed(ip):
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "rate_limited",
                        "request_id": request_id,
                        "timestamp_utc": _utc_now(),
                    },
                )

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
                "openai_compatible": runtime_mode == "full",
                "query_interface": True,  # Always available as fallback
                "websocket_events": True,  # Always available as fallback
                "voice_pipeline": flags.get("denis_use_voice_pipeline", False)
                if isinstance(flags, dict)
                else getattr(flags, "denis_use_voice_pipeline", False),
                "memory_unified": flags.get("denis_use_memory_unified", False)
                if isinstance(flags, dict)
                else getattr(flags, "denis_use_memory_unified", False),
                "atlas_bridge": flags.get("denis_use_atlas", False)
                if isinstance(flags, dict)
                else getattr(flags, "denis_use_atlas", False),
                "cognitive_router": True,
                "inference_router": flags.get("denis_use_inference_router", False)
                if isinstance(flags, dict)
                else getattr(flags, "denis_use_inference_router", False),
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

    @app.get("/controlplane/status")
    async def controlplane_status() -> dict[str, Any]:
        try:
            from denisunifiedv1.control_plane.policy import get_control_plane_status

            return get_control_plane_status()
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "releaseable": False,
                "timestamp_utc": _utc_now(),
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
    build_openai_router = None
    try:
        from .openai_compatible import DenisRuntime, build_openai_router

        runtime = DenisRuntime()
        runtime_mode = "full"
    except Exception as e:

        class DegradedRuntime:
            def __init__(self, flags):
                self.flags = flags
                self.models = [{"id": "denis-cognitive", "object": "model"}]
                self.budget_manager = None

            async def generate(self, req):
                return {
                    "id": f"chatcmpl-{uuid.uuid4().hex[:16]}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": getattr(req, "model", "denis-cognitive"),
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "Service temporarily unavailable due to missing dependencies.",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                    },
                    "meta": {"path": "degraded", "reason": "missing_dependencies"},
                }

        runtime = DegradedRuntime(flags)
        runtime_mode = "degraded"
        try:
            from denisunifiedv1.control_plane.registry import (
                get_control_plane_registry,
                DegradationRecord,
            )

            registry = get_control_plane_registry()
            registry.record_degraded(
                DegradationRecord(
                    id="import.openai_compatible.missing",
                    component="api.fastapi_server",
                    severity=3,
                    category="import",
                    reason="missing_module",
                    evidence={"module": "openai_compatible", "error": str(e)},
                    first_seen_utc=time.time(),
                    last_seen_utc=time.time(),
                    count=1,
                )
            )
        except Exception:
            pass

    included_openai = False
    try:
        if build_openai_router is not None:
            included_openai = _safe_include(build_openai_router, runtime)
    except Exception:
        included_openai = False

    # Always include a degraded fallback router to guarantee OpenAI endpoints are present
    fallback_router = APIRouter()

    @fallback_router.get("/v1/models")
    async def list_models_fallback():
        return {
            "object": "list",
            "data": [{"id": "denis-cognitive", "object": "model"}],
        }

    @fallback_router.post("/v1/chat/completions")
    async def chat_completions_fallback(_: Request):
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:16]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "denis-cognitive",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Degraded runtime response.",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    @fallback_router.post("/v1/chat/completions/stream")
    async def chat_stream_fallback(_: Request):
        async def streamer():
            yield 'data: {"choices":[{"delta":{"content":"Degraded runtime response."}}]}\n\n'
            yield "data: [DONE]\n\n"

        return StreamingResponse(streamer(), media_type="text/event-stream")

    app.include_router(fallback_router)
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
        if (
            flags.get("denis_use_voice_pipeline", False)
            if isinstance(flags, dict)
            else flags.enabled("denis_use_voice_pipeline", False)
        ):
            from .voice_handler import build_voice_router

            _safe_include(build_voice_router)
    except Exception:
        pass

    try:
        if (
            flags.get("denis_use_memory_unified", False)
            if isinstance(flags, dict)
            else flags.enabled("denis_use_memory_unified", False)
        ):
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

    # Setup tracing and metrics with complete fail-open
    tracing_enabled = False
    metrics_enabled = False
    if os.getenv("DISABLE_OBSERVABILITY") == "1":
        tracing_enabled = False
        metrics_enabled = False
    else:
        if not tracing_setup_done:
            try:
                from observability.tracing import setup_tracing

                setup_tracing()
                tracing_setup_done = True
            except Exception:
                pass

        if not metrics_setup_done:
            try:
                from observability.metrics import setup_metrics

                setup_metrics(app)
                metrics_setup_done = True
            except Exception:
                pass

        tracing_enabled = tracing_setup_done
        metrics_enabled = metrics_setup_done

    @app.get("/observability")
    async def observability_status():
        return {
            "status": "ok",
            "timestamp_utc": _utc_now(),
            "observability": {
                "tracing_enabled": tracing_enabled,
                "metrics_enabled": metrics_enabled,
                "reason": None
                if (tracing_enabled and metrics_enabled)
                else "partial_observability",
            },
        }

    return app


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
            "available_components": ["health"],
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

# No more endpoints added after create_app - all moved inside
