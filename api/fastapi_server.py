"""Phase-6 FastAPI server (OpenAI-compatible incremental layer)."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
import logging
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

    logger = logging.getLogger(__name__)
    app = FastAPI(title="Denis Cognitive Engine", version="1.0.0")

    # Basic telemetry: metrics
    try:
        from prometheus_client import Counter
        
        # Thread-safe global initialization
        global _metrics_initialized, _requests_total, _denies_total, _degraded_total
        with _metrics_lock:
            if not _metrics_initialized:
                _requests_total = Counter('requests_total', 'Total requests', ['critical'])
                _denies_total = Counter('denies_total', 'Total denies', ['policy'])
                _degraded_total = Counter('degraded_total', 'Total degraded responses', ['reason'])
                _metrics_initialized = True
        
        requests_total = _requests_total
        denies_total = _denies_total
        degraded_total = _degraded_total
    except ImportError:
        requests_total = denies_total = degraded_total = None

    # Neo4j client for identity checks (fail-open)
    neo4j_driver = None
    try:
        neo4j_uri = os.getenv("NEO4J_URI")
        neo4j_user = os.getenv("NEO4J_USER")
        neo4j_pass = os.getenv("NEO4J_PASSWORD")
        if neo4j_uri and neo4j_user and neo4j_pass:
            from neo4j import GraphDatabase
            neo4j_driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))
            # Test connection
            with neo4j_driver.session() as session:
                session.run("RETURN 1")
    except Exception:
        neo4j_driver = None

    def identity_check(request: Request, is_critical: bool = False) -> bool:
        """Check Denis identity and constitution. Fail-closed for critical actions."""
        # In contract test mode, allow all requests
        is_contract_mode = (
            os.getenv("DENIS_CONTRACT_TEST_MODE") == "1" and
            os.getenv("ENV") != "production"
        )
        if is_contract_mode:
            return True
            
        if not neo4j_driver:
            if is_critical:
                return False  # Fail-closed: no graph, deny critical
            return True  # Fail-open for non-critical

        try:
            with neo4j_driver.session() as session:
                # Check companion_mode and required edges in single query
                result = session.run("""
                MATCH (iden:Identity {id: 'identity:denis'})
                OPTIONAL MATCH (iden)-[:ENFORCED_BY]->(aa:System {id: 'system:action_authorizer'})
                OPTIONAL MATCH (iden)-[:GUARDED_BY]->(cg:System {id: 'system:ci_gate'})
                OPTIONAL MATCH (iden)-[:OBSERVED_BY]->(at:System {id: 'system:atlas'})
                OPTIONAL MATCH (iden)-[:BOUND_BY]->(hc:System {id: 'system:honesty_core'})
                RETURN iden.companion_mode AS mode, aa IS NOT NULL AS has_aa, cg IS NOT NULL AS has_cg, at IS NOT NULL AS has_at, hc IS NOT NULL AS has_hc
                """)
                record = result.single()
                if not record or record["mode"] != True or not all([record["has_aa"], record["has_cg"], record["has_at"], record["has_hc"]]):
                    if is_critical:
                        return False
                    return True

                return True
        except Exception:
            if is_critical:
                return False  # Fail-closed
            return True  # Fail-open

    def is_critical_action(request: Request) -> bool:
        """Classify if request is critical (repo mutation, constitution changes, etc.)."""
        path = request.url.path
        method = request.method
        # Critical: chat completions (potential code gen), any POST to sensitive paths, etc.
        # For now, classify based on path/method; expand as needed
        critical_paths = ["/v1/chat/completions", "/v1/completions", "/registry", "/metacognitive"]
        if method == "POST" and any(p in path for p in critical_paths):
            return True
        # Add more logic if needed (e.g., check body for mutation keywords)
        return False

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
                    id="import.feature_flags.missing",
                    component="api.fastapi_server",
                    severity=3,
                    category="import",
                    reason="missing_module",
                    evidence={"module": "feature_flags", "error": str(e)},
                    first_seen_utc=time.time(),
                    last_seen_utc=time.time(),
                    count=1,
                )
            )
        except Exception:
            pass

        raw_flags = {}  # fallback

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

        runtime = DegradedRuntime(raw_flags)
        runtime_mode = "degraded"

    def _safe_include(router_factory, *args):
        """Safely include a router by calling the factory and adding it to the app."""
        try:
            router = router_factory(*args)
            app.include_router(router)
            logger.debug(f"Successfully included router from {router_factory.__name__}")
            return True
        except Exception as e:
            logger.exception(f"Failed to include router from {router_factory.__name__}")
            # In test mode, fail fast if we can't include critical routers
            is_test_mode = (
                os.getenv("DENIS_CONTRACT_TEST_MODE") == "1" and
                os.getenv("ENV") != "production"
            )
            if is_test_mode and router_factory.__name__ == "build_openai_router":
                raise RuntimeError(f"Critical router {router_factory.__name__} failed to load in test mode: {e}")
            return False

    # Determine if critical dependencies are ready (not in degraded mode)
    # In contract test mode, allow requests even with degraded dependencies
    is_contract_mode = (
        os.getenv("DENIS_CONTRACT_TEST_MODE") == "1" and
        os.getenv("ENV") != "production"
    )
    critical_ready = (runtime_mode == "full") or is_contract_mode

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

    # Human memory and context managers (fail-open for humanlike/IDE modes)
    human_memory_manager = None
    context_manager = None
    try:
        from denis_unified_v1.services.human_memory_manager import get_human_memory_manager
        human_memory_manager = get_human_memory_manager()
    except Exception:
        pass
    try:
        from denis_unified_v1.services.context_manager import get_context_manager
        context_manager = get_context_manager()
    except Exception:
        pass

    def inject_i2_human_memory(request: Request, user_id: str, group_id: str, intent: str) -> str:
        """I2: Inject human memory (narrative state + episodic)."""
        if not human_memory_manager:
            return ""
        narrative = human_memory_manager.get_narrative_state(user_id, group_id)
        followup_due = narrative.get("followup_due", [])
        # Query episodic for intent
        query = {"user_id": user_id, "group_id": group_id, "query_text": intent, "entities": []}
        results = human_memory_manager._execute_query(query)
        episodic = results.get("episodes", [])[:1]  # Top 1
        summary = episodic[0]["summary"] if episodic else ""
        source_note = {}
        if episodic and "claim" in episodic[0]:
            claim = episodic[0]["claim"]
            source_note = {"type": "claim", "asserted_by": claim.get("source_type", "unknown"), "verified": False}
        ask_style = {"tone": "preocupado", "question_bias": "preguntar primero", "do_not_assume": True}
        return f"Narrative context: {narrative}. Relevant episode: {summary}. Source note: {source_note}. Ask style: {ask_style}. Followup due: {followup_due}."

    def inject_i4_human_style(response_content: str) -> str:
        """I4: Apply human-like style (natural questions, continuity)."""
        # Simple: add follow-up if open threads
        if "está bien" in response_content.lower():
            response_content += " ¿Necesitas algo más?"
        return response_content

    # Human memory and context managers (fail-open for humanlike/IDE modes)
    human_memory_manager = None
    context_manager = None
    try:
        from denis_unified_v1.services.human_memory_manager import get_human_memory_manager
        human_memory_manager = get_human_memory_manager()
    except Exception:
        pass
    try:
        from denis_unified_v1.services.context_manager import get_context_manager
        context_manager = get_context_manager()
    except Exception:
        pass

    def inject_i2_human_memory(request: Request, user_id: str, group_id: str, intent: str) -> str:
        """I2: Inject human memory (narrative state + episodic)."""
        if not human_memory_manager:
            return ""
        narrative = human_memory_manager.get_narrative_state(user_id, group_id)
        followup_due = narrative.get("followup_due", [])
        # Query episodic for intent
        query = {"user_id": user_id, "group_id": group_id, "query_text": intent, "entities": []}
        results = human_memory_manager._execute_query(query)
        episodic = results.get("episodes", [])[:1]  # Top 1
        summary = episodic[0]["summary"] if episodic else ""
        source_note = {}
        if episodic and "claim" in episodic[0]:
            claim = episodic[0]["claim"]
            source_note = {"type": "claim", "asserted_by": claim.get("source_type", "unknown"), "verified": False}
        ask_style = {"tone": "preocupado", "question_bias": "preguntar primero", "do_not_assume": True}
        return f"Narrative context: {narrative}. Relevant episode: {summary}. Source note: {source_note}. Ask style: {ask_style}. Followup due: {followup_due}."

    def inject_i4_human_style(response_content: str) -> str:
        """I4: Apply human-like style (natural questions, continuity)."""
        # Simple: add follow-up if open threads
        if "está bien" in response_content.lower():
            response_content += " ¿Necesitas algo más?"
        return response_content

    # Mount static files with fail-open</parameter
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

            # Identity check (companion_mode + constitution for critical actions)
            critical = is_critical_action(request)
            if critical and not critical_ready:
                if denies_total:
                    denies_total.labels(policy='runtime_deps').inc()
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": "service_degraded",
                        "reason": "runtime_dependencies_missing",
                        "request_id": request_id,
                        "timestamp_utc": _utc_now(),
                    },
                )
            if not identity_check(request, critical):
                if denies_total:
                    denies_total.labels(policy='identity_forbidden').inc()
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": "identity_forbidden",
                        "request_id": request_id,
                        "timestamp_utc": _utc_now(),
                    },
                )

            # Telemetry: increment requests
            if requests_total:
                requests_total.labels(critical=str(critical)).inc()

            start = time.perf_counter()
            response = await call_next(request)
            duration_ms = int((time.perf_counter() - start) * 1000)
            response.headers["x-request-id"] = request_id
            response.headers["x-duration-ms"] = str(duration_ms)

            # Telemetry: check for degraded
            if degraded_total and hasattr(response, 'headers') and response.headers.get('x-runtime-mode') == 'degraded':
                degraded_total.labels(reason='DEPENDENCY_MISSING').inc()

            # Logs
            print(f"LOG: request_id={request_id}, critical={critical}, status={response.status_code}", flush=True)

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
            "ready_critical": critical_ready,
            "ready_soft": True,
            "feature_flags": _safe_json(flags),
            "components": {
                "openai_compatible": runtime_mode == "full",
                "query_interface": True,
                "websocket_events": True,
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
    async def status():
        return {
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

    included_openai = False
    try:
        logger.debug("Attempting to build OpenAI router")
        if build_openai_router is not None:
            logger.debug("build_openai_router is not None, calling _safe_include")
            included_openai = _safe_include(build_openai_router, runtime)
            logger.debug(f"_safe_include returned {included_openai}")
        else:
            logger.debug("build_openai_router is None")
    except Exception as e:
        logger.exception("_safe_include failed")
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
        return JSONResponse(
            status_code=200,
            headers={"x-runtime-mode": "degraded"},
            content={
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
                "diagnostics": {"degraded": True, "reason": "DEPENDENCY_MISSING"},
            }
        )

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

# Global Prometheus metrics to prevent duplicate registration in tests
import threading
_metrics_initialized = False
_metrics_lock = threading.Lock()

_requests_total = None
_denies_total = None  
_degraded_total = None
