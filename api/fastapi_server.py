"""Phase-6 FastAPI server (OpenAI-compatible incremental layer)."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
import logging
import os
import sys
import time
import uuid
from typing import Any

from fastapi import FastAPI, Request, APIRouter
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
# All other imports moved inside create_app() for complete fail-open behavior


# Pytest safety: avoid enabling exporters/instrumentation during module import,
# because this module creates a global `app = create_app()` as a fallback.
_running_pytest = ("pytest" in sys.modules) or any("pytest" in (arg or "") for arg in sys.argv)
if _running_pytest and (os.getenv("DENIS_TEST_ENABLE_OBSERVABILITY") or "").strip().lower() not in {
    "1",
    "true",
    "yes",
}:
    # Force-disable to prevent flaky hangs with exporters/instrumentation in tests.
    os.environ["DISABLE_OBSERVABILITY"] = "1"


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

# Global Prometheus metrics to prevent duplicate registration in tests.
# NOTE: must be defined before `create_app()` is executed at module import time.
import threading

_metrics_initialized = False
_metrics_lock = threading.Lock()

_requests_total = None
_denies_total = None
_degraded_total = None


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
                _requests_total = Counter("requests_total", "Total requests", ["critical"])
                _denies_total = Counter("denies_total", "Total denies", ["policy"])
                _degraded_total = Counter("degraded_total", "Total degraded responses", ["reason"])
                _metrics_initialized = True

        requests_total = _requests_total
        denies_total = _denies_total
        degraded_total = _degraded_total
    except ImportError:
        requests_total = denies_total = degraded_total = None

    # Neo4j client for identity checks (fail-open).
    # Never hard-probe network on startup; tests/contract mode must not hang here.
    neo4j_driver = None
    try:
        if os.getenv("DENIS_CONTRACT_TEST_MODE") == "1":
            neo4j_driver = None
        else:
            neo4j_uri = os.getenv("NEO4J_URI")
            neo4j_user = os.getenv("NEO4J_USER")
            neo4j_pass = os.getenv("NEO4J_PASSWORD")
            if neo4j_uri and neo4j_user and neo4j_pass:
                from neo4j import GraphDatabase

                neo4j_driver = GraphDatabase.driver(
                    neo4j_uri,
                    auth=(neo4j_user, neo4j_pass),
                    connection_timeout=float(os.getenv("DENIS_NEO4J_CONNECT_TIMEOUT_S", "0.2")),
                    connection_acquisition_timeout=float(
                        os.getenv("DENIS_NEO4J_ACQUIRE_TIMEOUT_S", "0.2")
                    ),
                    max_connection_pool_size=int(os.getenv("DENIS_NEO4J_POOL_SIZE", "1")),
                )
    except Exception:
        neo4j_driver = None

    def identity_check(request: Request, is_critical: bool = False) -> bool:
        """Check Denis identity and constitution. Fail-closed for critical actions."""
        # In contract test mode, allow all requests
        is_contract_mode = (
            os.getenv("DENIS_CONTRACT_TEST_MODE") == "1" and os.getenv("ENV") != "production"
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
                // Defensive: graph may contain duplicate Identity nodes. Pick the
                // best candidate deterministically (companion_mode=true first).
                MATCH (iden:Identity {id: 'identity:denis'})
                WITH iden
                ORDER BY coalesce(iden.companion_mode, false) DESC, size(keys(iden)) DESC
                LIMIT 1
                OPTIONAL MATCH (iden)-[:ENFORCED_BY]->(aa:System {id: 'system:action_authorizer'})
                OPTIONAL MATCH (iden)-[:GUARDED_BY]->(cg:System {id: 'system:ci_gate'})
                OPTIONAL MATCH (iden)-[:OBSERVED_BY]->(at:System {id: 'system:atlas'})
                OPTIONAL MATCH (iden)-[:BOUND_BY]->(hc:System {id: 'system:honesty_core'})
                RETURN iden.companion_mode AS mode, aa IS NOT NULL AS has_aa, cg IS NOT NULL AS has_cg, at IS NOT NULL AS has_at, hc IS NOT NULL AS has_hc
                """)
                record = result.single()
                if (
                    not record
                    or record["mode"] != True
                    or not all(
                        [
                            record["has_aa"],
                            record["has_cg"],
                            record["has_at"],
                            record["has_hc"],
                        ]
                    )
                ):
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
        critical_paths = [
            "/v1/chat/completions",
            "/v1/completions",
            "/registry",
            "/metacognitive",
        ]
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
                os.getenv("DENIS_CONTRACT_TEST_MODE") == "1" and os.getenv("ENV") != "production"
            )
            if is_test_mode and router_factory.__name__ == "build_openai_router":
                raise RuntimeError(
                    f"Critical router {router_factory.__name__} failed to load in test mode: {e}"
                )
            return False

    # Determine if critical dependencies are ready (not in degraded mode)
    # In contract test mode, allow requests even with degraded dependencies
    is_contract_mode = (
        os.getenv("DENIS_CONTRACT_TEST_MODE") == "1" and os.getenv("ENV") != "production"
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
        from denis_unified_v1.services.human_memory_manager import (
            get_human_memory_manager,
        )

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
        query = {
            "user_id": user_id,
            "group_id": group_id,
            "query_text": intent,
            "entities": [],
        }
        results = human_memory_manager._execute_query(query)
        episodic = results.get("episodes", [])[:1]  # Top 1
        summary = episodic[0]["summary"] if episodic else ""
        source_note = {}
        if episodic and "claim" in episodic[0]:
            claim = episodic[0]["claim"]
            source_note = {
                "type": "claim",
                "asserted_by": claim.get("source_type", "unknown"),
                "verified": False,
            }
        ask_style = {
            "tone": "preocupado",
            "question_bias": "preguntar primero",
            "do_not_assume": True,
        }
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
        from denis_unified_v1.services.human_memory_manager import (
            get_human_memory_manager,
        )

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
        query = {
            "user_id": user_id,
            "group_id": group_id,
            "query_text": intent,
            "entities": [],
        }
        results = human_memory_manager._execute_query(query)
        episodic = results.get("episodes", [])[:1]  # Top 1
        summary = episodic[0]["summary"] if episodic else ""
        source_note = {}
        if episodic and "claim" in episodic[0]:
            claim = episodic[0]["claim"]
            source_note = {
                "type": "claim",
                "asserted_by": claim.get("source_type", "unknown"),
                "verified": False,
            }
        ask_style = {
            "tone": "preocupado",
            "question_bias": "preguntar primero",
            "do_not_assume": True,
        }
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
            StaticFiles(directory="static", check_dir=False),
            name="static",
        )
    except Exception:
        pass

    @app.get("/")
    async def read_root():
        return FileResponse("static/index.html")

    @app.get("/cockpit")
    async def read_cockpit():
        return FileResponse("static/cockpit.html")

    @app.middleware("http")
    async def trace_and_security_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        ip = request.client.host if request.client else "unknown"
        start = time.perf_counter()

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

            # Rate limiting (MVP): only applied to non-trivial endpoints.
            # The frontend polls /health and /hass/* frequently; do not let that starve interactive endpoints
            # like /v1/voice/chat or /v1/chat/completions.
            path = request.url.path
            rate_limit_exempt = (
                path == "/health"
                or path == "/v1/events"
                or path.startswith("/hass/")
                or path.startswith("/static/")
                or path == "/"
                or path == "/cockpit"
                or path.startswith("/v1/voice/audio/")
            )
            if not rate_limit_exempt and not limiter.is_allowed(ip):
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
                    denies_total.labels(policy="runtime_deps").inc()
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
                    denies_total.labels(policy="identity_forbidden").inc()
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

            response = await call_next(request)
            duration_ms = int((time.perf_counter() - start) * 1000)
            response.headers["x-request-id"] = request_id
            response.headers["x-duration-ms"] = str(duration_ms)

            # Telemetry: check for degraded
            if (
                degraded_total
                and hasattr(response, "headers")
                and response.headers.get("x-runtime-mode") == "degraded"
            ):
                degraded_total.labels(reason="DEPENDENCY_MISSING").inc()

            # Logs
            print(
                f"LOG: request_id={request_id}, critical={critical}, status={response.status_code}",
                flush=True,
            )

            # Minimal in-memory telemetry (fail-open)
            try:
                from api.telemetry_store import get_telemetry_store

                get_telemetry_store().record_request(
                    path=request.url.path,
                    status_code=int(getattr(response, "status_code", 0) or 0),
                    latency_ms=int(duration_ms),
                )
            except Exception:
                pass

            return response

        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            try:
                from api.telemetry_store import get_telemetry_store

                get_telemetry_store().record_request(
                    path=request.url.path,
                    status_code=200,
                    latency_ms=int(duration_ms),
                )
            except Exception:
                pass
            return JSONResponse(
                status_code=200,
                content={
                    "error": "degraded",
                    "detail": "internal_error",
                    "request_id": request_id,
                    "timestamp_utc": _utc_now(),
                },
            )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        status = "healthy" if runtime_mode == "full" else "degraded"
        return {
            "status": status,
            "version": "unified-v1",
            "timestamp_utc": _utc_now(),
            "ready_critical": critical_ready,
            "ready_soft": True,
            "feature_flags": _safe_json(raw_flags),
            "components": {
                "openai_compatible": runtime_mode == "full",
                "query_interface": True,
                "websocket_events": True,
                "voice_pipeline": raw_flags.get("denis_use_voice_pipeline", False)
                if isinstance(raw_flags, dict)
                else getattr(raw_flags, "denis_use_voice_pipeline", False),
                "memory_unified": raw_flags.get("denis_use_memory_unified", False)
                if isinstance(raw_flags, dict)
                else getattr(raw_flags, "denis_use_memory_unified", False),
                "atlas_bridge": raw_flags.get("denis_use_atlas", False)
                if isinstance(raw_flags, dict)
                else getattr(raw_flags, "denis_use_atlas", False),
                "cognitive_router": True,
                "inference_router": raw_flags.get("denis_use_inference_router", False)
                if isinstance(raw_flags, dict)
                else getattr(raw_flags, "denis_use_inference_router", False),
                "agent_heart": True,
                "metacognitive": True,
            },
        }

    @app.get("/status")
    async def status():
        return {
            "model": "denis-cognitive",
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
    async def chat_completions_fallback(request: Request):
        # Anti-loop protection even in degraded mode.
        hop = 0
        max_hop = 0
        try:
            from denis_unified_v1.inference.hop import parse_hop

            hop = parse_hop(request.headers.get("x-denis-hop"))
            max_hop = int(os.getenv("DENIS_OPENAI_COMPAT_MAX_HOP", "0"))
        except Exception:
            hop = 0
            max_hop = 0

        # Try to extract minimal info for telemetry (no raw prompts persisted).
        user_text = ""
        model = "denis-cognitive"
        try:
            payload = await request.json()
            if isinstance(payload, dict):
                model = str(payload.get("model") or model)
                msgs = payload.get("messages") or []
                if isinstance(msgs, list):
                    for msg in reversed(msgs):
                        if (
                            isinstance(msg, dict)
                            and msg.get("role") == "user"
                            and isinstance(msg.get("content"), str)
                        ):
                            user_text = msg["content"]
                            break
        except Exception:
            pass

        blocked = hop > max_hop
        try:
            from api.telemetry_store import get_telemetry_store, sha256_text

            get_telemetry_store().record_chat_decision(
                {
                    "request_id": None,
                    "model": model,
                    "x_denis_hop": hop,
                    "blocked": bool(blocked),
                    "path": "blocked_hop" if blocked else "fallback_degraded",
                    "prompt_sha256": sha256_text(user_text),
                    "prompt_chars": len(user_text or ""),
                }
            )
        except Exception:
            pass

        if blocked:
            return JSONResponse(
                status_code=200,
                headers={"x-runtime-mode": "degraded"},
                content={
                    "id": f"chatcmpl-{uuid.uuid4().hex[:16]}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "Degraded response: loop protection (X-Denis-Hop) blocked request.",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                    },
                    "meta": {"path": "blocked_hop", "x_denis_hop": hop, "max_hop": max_hop},
                    "diagnostics": {"degraded": True, "reason": "HOP_BLOCKED"},
                },
            )

        return JSONResponse(
            status_code=200,
            headers={"x-runtime-mode": "degraded"},
            content={
                "id": f"chatcmpl-{uuid.uuid4().hex[:16]}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
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
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
                "meta": {"path": "fallback_degraded"},
                "diagnostics": {"degraded": True, "reason": "DEPENDENCY_MISSING"},
            },
        )

    @fallback_router.post("/v1/chat/completions/stream")
    async def chat_stream_fallback(request: Request):
        try:
            from denis_unified_v1.inference.hop import parse_hop

            hop = parse_hop(request.headers.get("x-denis-hop"))
            max_hop = int(os.getenv("DENIS_OPENAI_COMPAT_MAX_HOP", "0"))
            if hop > max_hop:
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
                                    "content": "Degraded response: loop protection (X-Denis-Hop) blocked request.",
                                },
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 1,
                            "completion_tokens": 1,
                            "total_tokens": 2,
                        },
                        "meta": {"path": "blocked_hop", "x_denis_hop": hop, "max_hop": max_hop},
                        "diagnostics": {"degraded": True, "reason": "HOP_BLOCKED"},
                    },
                )
        except Exception:
            pass

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

    # Healthz endpoint for brain visibility
    try:
        from .healthz import router as healthz_router

        app.include_router(healthz_router)
    except Exception:
        pass

    # Ops endpoints for Frontend/Care (P0: stubs, P1: full implementation)
    try:
        from .routes.health_ops import router as health_ops_router

        app.include_router(health_ops_router)
    except Exception:
        pass
    try:
        from .routes.control_room import router as control_room_router

        app.include_router(control_room_router)
    except Exception:
        pass
    # Graph read endpoints for cockpit UI (fail-open, read-only)
    try:
        from .routes.graph_read import router as graph_read_router

        app.include_router(graph_read_router)
    except Exception:
        pass

    try:
        from .routes.hass_ops import router as hass_ops_router

        app.include_router(hass_ops_router)
    except Exception:
        pass

    try:
        from .routes.telemetry_ops import router as telemetry_ops_router

        app.include_router(telemetry_ops_router)
    except Exception:
        pass

    # OpenCode-compatible Tools API (fail-open)
    try:
        from .routes.tools_api import router as tools_api_router

        app.include_router(tools_api_router)
    except Exception:
        pass

    # WebSocket-first Event Bus v1 (fail-open)
    try:
        from .routes.ws_events import router as ws_events_router

        app.include_router(ws_events_router)
    except Exception:
        pass
    try:
        from .routes.events_http import router as events_http_router

        app.include_router(events_http_router)
    except Exception:
        pass

    # WS15 Persona frontdoor (minimal gateway endpoints). Fail-open.
    try:
        from .routes.persona_gateway import router as persona_gateway_router

        app.include_router(persona_gateway_router)
    except Exception:
        pass

    # WS12-G Voice (Pipecat bridge + voice.* events). Fail-open.
    try:
        from .routes.voice import router as voice_router

        app.include_router(voice_router)
    except Exception:
        pass

    # Voice/Memory/Metagraph/Autopoiesis/Registry (gated + fail-open)
    try:
        if (
            raw_flags.get("denis_use_voice_pipeline", False)
            if isinstance(raw_flags, dict)
            else getattr(raw_flags, "denis_use_voice_pipeline", False)
        ):
            from .voice_handler import build_voice_router

            _safe_include(build_voice_router)
    except Exception:
        pass

    try:
        if (
            raw_flags.get("denis_use_memory_unified", False)
            if isinstance(raw_flags, dict)
            else getattr(raw_flags, "denis_use_memory_unified", False)
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
    # In tests we disable observability to avoid background exporters and
    # global instrumentation interfering with deterministic runs.
    running_under_pytest = _running_pytest
    if os.getenv("DISABLE_OBSERVABILITY") == "1" or is_contract_mode or running_under_pytest:
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

    @app.get("/gps")
    async def get_gps_location():
        import requests
        from fastapi import HTTPException

        hass_url = os.getenv("HASS_URL")
        hass_token = os.getenv("HASS_TOKEN")
        device_id = os.getenv("HASS_DEVICE_ID", "person.jotah")

        if not hass_url or not hass_token:
            raise HTTPException(status_code=500, detail="Hass config missing")

        url = f"{hass_url}/api/states/device_tracker.{device_id}"
        headers = {
            "Authorization": f"Bearer {hass_token}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            lat = data.get("attributes", {}).get("latitude")
            lng = data.get("attributes", {}).get("longitude")
            if lat is not None and lng is not None:
                return {"latitude": lat, "longitude": lng}
            else:
                raise HTTPException(status_code=404, detail="Location not available")
        except requests.RequestException as e:
            raise HTTPException(status_code=500, detail=f"Hass request failed: {str(e)}")

    # Include middleware router for OpenCode integration
    try:
        from .middleware_api import router as middleware_router

        app.include_router(middleware_router)
    except Exception as e:
        logger.warning(f"Failed to include middleware router: {e}")

    # Include compiler router for WS21-G OpenCode LLM Compiler
    try:
        from .routes.compiler import router as compiler_router

        app.include_router(compiler_router)
    except Exception as e:
        logger.warning(f"Failed to include compiler router: {e}")

    # WS23-G Neuroplasticity endpoints (fail-open)
    try:
        from .routes.neuro import router as neuro_router

        app.include_router(neuro_router)
    except Exception as e:
        logger.warning(f"Failed to include neuro router: {e}")

    return app


# Create app with complete fail-open
try:
    app = create_app()
except Exception as exc:
    # Emergency fallback: create minimal app with just health and agent heart
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    _create_app_error = str(exc)

    app = FastAPI(title="Denis Cognitive Engine - Emergency Mode", version="emergency")

    @app.get("/health")
    async def emergency_health():
        return {
            "status": "emergency_mode",
            "error": _create_app_error,
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
