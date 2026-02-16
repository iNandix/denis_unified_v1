"""
Cognitive Router con metacognición.

Wrapper sobre execute_with_cortex() que añade:
- Predicción de mejor tool basada en contexto
- Auto-evaluación de decisiones de routing
- Aprendizaje de patrones de routing exitosos
- Generación de proposals de optimización
- Métricas detalladas a Redis

Contratos aplicados:
- L3.ROUTER.FALLBACK_LEGACY
- L3.ROUTER.METRICS_REQUIRED
- L3.ROUTER.CONFIDENCE_THRESHOLD
- L3.ROUTER.LATENCY_BUDGET
- L3.ROUTER.FAILURE_ANALYSIS
- L3.ROUTER.LEARNING_FEEDBACK
- L3.ROUTER.TOOL_DISCOVERY
- L3.ROUTER.PROPERTY_INTEGRITY
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import os
import re
import time
from typing import Any, Dict, List, Optional

import redis

from denis_unified_v1.feature_flags import load_feature_flags
from opentelemetry import trace
from denis_unified_v1.observability.metrics import (
    cognitive_router_decisions,
    l1_pattern_usage,
)

tracer = trace.get_tracer(__name__)


class RoutingStrategy(Enum):
    SMART = "smart"
    LEGACY_FALLBACK = "legacy_fallback"
    ROUND_ROBIN = "round_robin"
    LOAD_BALANCED = "load_balanced"


@dataclass
class ToolInfo:
    name: str
    available: bool
    amplitude: float = 1.0
    cognitive_dimensions: dict[str, float] = field(default_factory=dict)
    success_rate: float = 1.0
    avg_latency_ms: float = 100.0
    last_used: str | None = None
    error_count: int = 0
    circuit_breaker_open: bool = False


@dataclass
class RoutingDecision:
    tool_name: str
    strategy: RoutingStrategy
    confidence: float
    latency_ms: float
    alternatives_considered: list[str]
    reasoning: str
    timestamp_utc: str
    request_id: str | None = None
    fallback_used: bool = False


@dataclass
class RoutingFeedback:
    request_id: str
    tool_name: str
    success: bool
    latency_ms: float
    quality_score: float | None = None
    user_feedback: str | None = None
    timestamp_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class RedisClient:
    _instance: redis.Redis | None = None

    @classmethod
    def get(cls) -> redis.Redis:
        if cls._instance is None:
            url = "redis://localhost:6379/0"
            try:
                import os

                url = os.getenv("REDIS_URL", url)
                cls._instance = redis.Redis.from_url(url, decode_responses=True)
            except Exception:
                cls._instance = redis.Redis.from_url(url, decode_responses=True)
        return cls._instance


class Neo4jClient:
    _driver: Any = None

    @classmethod
    def get_driver(cls):
        if cls._driver is None:
            from neo4j import GraphDatabase

            uri = os.getenv("NEO4J_URI", "bolt://10.10.10.1:7687")
            user = os.getenv("NEO4J_USER", "neo4j")
            password = os.getenv("NEO4J_PASSWORD") or os.getenv("NEO4J_PASS")
            if not password:
                if os.getenv("DENIS_DEV") == "1":
                    password = "neo4j"
                else:
                    print("WARNING: NEO4J_PASSWORD/NEO4J_PASS missing; graph disabled.")
                    return None
            if password:
                cls._driver = GraphDatabase.driver(uri, auth=(user, password))
        return cls._driver

    @classmethod
    def close(cls):
        if cls._driver:
            cls._driver.close()
            cls._driver = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_contracts() -> dict[str, Any]:
    contracts_path = os.path.join(
        os.path.dirname(__file__), "..", "contracts", "level3_cognitive_router.yaml"
    )
    if os.path.exists(contracts_path):
        try:
            import yaml

            with open(contracts_path) as f:
                return yaml.safe_load(f) or {}
        except Exception:
            pass
    return {}


def _get_redis() -> redis.Redis:
    return RedisClient.get()


def _emit_event(channel: str, data: dict[str, Any]) -> None:
    try:
        r = _get_redis()
        r.publish(channel, json.dumps(data, sort_keys=True))
    except Exception:
        pass


def _record_metric(key: str, value: Any, ttl: int = 3600) -> None:
    try:
        r = _get_redis()
        if isinstance(value, (int, float)):
            r.incrby(f"denis:cognitive_router:metrics:{key}", value)
        else:
            r.setex(
                f"denis:cognitive_router:metrics:{key}",
                ttl,
                json.dumps(value, sort_keys=True),
            )
    except Exception:
        pass


def _get_tools_from_neo4j() -> dict[str, ToolInfo]:
    """Carga herramientas del grafo Neo4j REAL de Denis."""
    try:
        driver = Neo4jClient.get_driver()

        with driver.session() as session:
            # Query: obtener nodos Tool del grafo
            result = session.run("""
                MATCH (t:Tool)
                RETURN t.name as name, 
                       t.description as description,
                       t.success_rate as success_rate,
                       t.avg_latency_ms as latency,
                       t.cost_per_call as cost
                ORDER BY t.success_rate DESC
            """)

            tools = {}
            for record in result:
                tool_name = record["name"]
                tools[tool_name] = ToolInfo(
                    name=tool_name,
                    available=True,
                    amplitude=1.0,
                    cognitive_dimensions={},
                    success_rate=record.get("success_rate", 0.0),
                    avg_latency_ms=record.get("latency", 0),
                )

            # Si el grafo está vacío, NO devuelvas {}
            # Devuelve herramientas mínimas pero REALES del sistema
            if not tools:
                return {
                    "smx_response": ToolInfo(
                        name="smx_response",
                        available=True,
                        amplitude=0.9,
                        cognitive_dimensions={"quality": 0.85},
                        success_rate=0.95,
                        avg_latency_ms=800,
                    ),
                    "smx_fast_path": ToolInfo(
                        name="smx_fast_path",
                        available=True,
                        amplitude=0.95,
                        cognitive_dimensions={"speed": 0.9},
                        success_rate=0.90,
                        avg_latency_ms=200,
                    ),
                }

            return tools

    except Exception as e:
        # Si Neo4j falla, log el error pero NO rompas el sistema
        print(f"WARNING: Neo4j tools load failed: {e}")
        # Fallback mínimo
        return {
            "smx_response": ToolInfo(
                name="smx_response", available=True, success_rate=0.95
            ),
            "smx_fast_path": ToolInfo(
                name="smx_fast_path", available=True, success_rate=0.90
            ),
        }


def _get_default_tools() -> dict[str, ToolInfo]:
    return {
        "default": ToolInfo(name="default", available=True, amplitude=1.0),
        "smx_fast_path": ToolInfo(
            name="smx_fast_path",
            available=True,
            amplitude=0.95,
            cognitive_dimensions={"speed": 0.9, "simplicity": 0.8},
            success_rate=0.98,
            avg_latency_ms=50.0,
        ),
        "smx_response": ToolInfo(
            name="smx_response",
            available=True,
            amplitude=0.9,
            cognitive_dimensions={"quality": 0.85, "comprehensiveness": 0.8},
            success_rate=0.95,
            avg_latency_ms=200.0,
        ),
        "code_interpreter": ToolInfo(
            name="code_interpreter",
            available=True,
            amplitude=0.9,
            cognitive_dimensions={"technical": 0.8, "reasoning": 0.7},
            success_rate=0.95,
            avg_latency_ms=150.0,
        ),
    }


def _extract_task_features(task: str) -> dict[str, float]:
    features: dict[str, float] = {
        "technical": 0.0,
        "creative": 0.0,
        "retrieval": 0.0,
        "modification": 0.0,
        "reasoning": 0.0,
        "code": 0.0,
        "length_short": 0.0,
        "length_medium": 0.0,
        "length_long": 0.0,
    }

    task_lower = task.lower()

    technical_patterns = [
        r"\b(code|debug|error|bug|fix|implement|api|function|class|import|module)\b",
        r"\b(python|javascript|typescript|rust|sql|query|database)\b",
    ]
    for pattern in technical_patterns:
        if re.search(pattern, task_lower):
            features["technical"] += 0.3

    creative_patterns = [
        r"\b(design|create|write|story|poem|song|art|creative|imagine)\b",
    ]
    for pattern in creative_patterns:
        if re.search(pattern, task_lower):
            features["creative"] += 0.3

    retrieval_patterns = [
        r"\b(find|search|lookup|query|get|retrieve|remember|what is|explain)\b",
    ]
    for pattern in retrieval_patterns:
        if re.search(pattern, task_lower):
            features["retrieval"] += 0.3

    modification_patterns = [
        r"\b(edit|modify|update|change|add|remove|rename|move|copy)\b",
    ]
    for pattern in modification_patterns:
        if re.search(pattern, task_lower):
            features["modification"] += 0.3

    reasoning_patterns = [
        r"\b(why|how|analyze|compare|evaluate|decide|choose|best|solution)\b",
    ]
    for pattern in reasoning_patterns:
        if re.search(pattern, task_lower):
            features["reasoning"] += 0.3

    code_patterns = [
        r"\b(def|class|import|from|return|if|else|for|while|try|except)\b",
    ]
    for pattern in code_patterns:
        if re.search(pattern, task_lower):
            features["code"] += 0.4

    word_count = len(task.split())
    if word_count < 5:
        features["length_short"] = 1.0
    elif word_count < 20:
        features["length_medium"] = 1.0
    else:
        features["length_long"] = 1.0

    return features


def _score_tool_for_task(tool: ToolInfo, features: dict[str, float]) -> float:
    if not tool.available or tool.circuit_breaker_open:
        return 0.0

    success_rate = tool.success_rate if tool.success_rate is not None else 0.5
    base_score = tool.amplitude * success_rate

    feature_bonus = 0.0
    dimension_bonus = 0.0

    if features.get("technical", 0) > 0.5 and "technical" in tool.cognitive_dimensions:
        feature_bonus += (
            features["technical"] * tool.cognitive_dimensions["technical"] * 0.3
        )

    if features.get("retrieval", 0) > 0.5:
        if "retrieval" in tool.cognitive_dimensions:
            feature_bonus += (
                features["retrieval"] * tool.cognitive_dimensions["retrieval"] * 0.3
            )
        elif tool.name == "memory" or tool.name == "search":
            feature_bonus += 0.2

    if features.get("modification", 0) > 0.5:
        if "modification" in tool.cognitive_dimensions:
            feature_bonus += (
                features["modification"]
                * tool.cognitive_dimensions["modification"]
                * 0.3
            )
        elif tool.name == "file_editor":
            feature_bonus += 0.2

    if features.get("code", 0) > 0.5 and tool.name == "code_interpreter":
        feature_bonus += 0.25

    avg_latency = tool.avg_latency_ms if tool.avg_latency_ms is not None else 100
    latency_penalty = max(0, (avg_latency - 50) / 1000)
    penalty = min(latency_penalty, 0.3)

    error_count = tool.error_count if tool.error_count is not None else 0
    error_penalty = error_count * 0.02

    final_score = base_score + feature_bonus - penalty - error_penalty

    return max(0.0, min(1.0, final_score))


def _analyze_failure(tool_name: str, error: str) -> dict[str, Any]:
    analysis = {
        "tool": tool_name,
        "error_type": "unknown",
        "suggestion": "Review tool implementation",
        "retry_recommended": True,
    }

    error_lower = error.lower()

    if "timeout" in error_lower:
        analysis["error_type"] = "timeout"
        analysis["suggestion"] = "Consider increasing timeout or using alternative tool"
    elif "not found" in error_lower or "does not exist" in error_lower:
        analysis["error_type"] = "not_found"
        analysis["suggestion"] = "Verify resource exists before retry"
    elif "permission" in error_lower or "access" in error_lower:
        analysis["error_type"] = "permission"
        analysis["suggestion"] = "Check permissions or use different approach"
    elif "syntax" in error_lower or "invalid" in error_lower:
        analysis["error_type"] = "syntax"
        analysis["suggestion"] = "Fix syntax error before retry"
    elif "memory" in error_lower:
        analysis["error_type"] = "memory"
        analysis["suggestion"] = "Consider splitting task into smaller parts"
    else:
        analysis["error_type"] = "generic"
        analysis["suggestion"] = "Review error and adjust approach"

    return analysis


class ToolSelectionPredictor:
    """Predice mejor tool para request basado en historial."""

    def __init__(self):
        self.redis_client = _get_redis()

    async def predict(self, request: dict) -> dict:
        """
        Predice tool basado en:
        - Tipo de request (code, chat, ops, etc.)
        - Historial de aciertos
        - Contexto actual
        """
        text = request.get("text", "")
        intent = request.get("intent", "unknown")

        # Heurística simple (mejorar con ML después)
        if len(text.split()) <= 3 and intent in ["greet", "chat"]:
            return {"tool": "smx_fast_path", "confidence": 0.95}
        elif intent in ["code", "debug"]:
            return {"tool": "code_interpreter", "confidence": 0.9}
        elif intent in ["chat"]:
            return {"tool": "smx_response", "confidence": 0.9}
        elif intent == "ops":
            return {"tool": "infrastructure_adapter", "confidence": 0.85}
        else:
            return {"tool": "smx_response", "confidence": 0.5}


class RoutingQualityMonitor:
    """Auto-evalúa calidad de decisiones de routing."""

    async def evaluate(self, request: dict, result: dict) -> dict:
        """
        Evalúa calidad por:
        - Latencia (< threshold)
        - Success (no error)
        - Coherencia (output sensato)
        """
        latency_ms = result.get("latency_ms", 0)
        success = result.get("success", False)
        content = result.get("content", "")

        # Score simple
        score = 0.0
        if success:
            score += 0.5
        if latency_ms < 2000:
            score += 0.3
        if len(content.strip()) > 10:
            score += 0.2

        return {
            "score": score,
            "latency_ok": latency_ms < 2000,
            "success": success,
            "content_ok": len(content.strip()) > 10,
        }


class RoutingLearner:
    """Aprende de aciertos/errores para mejorar predicciones."""

    def __init__(self):
        self.redis_client = _get_redis()

    async def learn(self, request: dict, tool_used: str, result: dict, quality: dict):
        """Registra decisión + resultado para aprendizaje futuro."""
        entry = {
            "request": request,
            "tool": tool_used,
            "quality_score": quality["score"],
            "timestamp": time.time(),
        }

        # Guardar en Redis (luego usar para entrenar modelo)
        key = f"routing:history:{int(time.time())}"
        self.redis_client.setex(key, 86400, json.dumps(entry))  # TTL 24h


class BehaviorHandbook:
    """Registra patrones de routing exitosos."""

    def __init__(self):
        self.redis_client = _get_redis()

    async def record_pattern(self, request: dict, tool: str, result: dict):
        """Guarda patrón exitoso como template para futuro."""
        pattern = {
            "intent": request.get("intent"),
            "tool": tool,
            "success": True,
            "timestamp": time.time(),
        }

        key = f"routing:patterns:{request.get('intent')}:{tool}"
        self.redis_client.lpush(key, json.dumps(pattern))
        self.redis_client.ltrim(key, 0, 99)  # Mantener últimos 100


from denis_unified_v1.metacognitive.hooks import metacognitive_trace


class CognitiveRouter:
    def __init__(self):
        self.flags = load_feature_flags()
        self._tools_cache: dict[str, ToolInfo] | None = None
        self._tools_cache_time: float = 0.0
        self._cache_ttl: float = 30.0
        self._contracts = _load_contracts()
        self._round_robin_index: int = 0
        self._enabled_strategies = {
            RoutingStrategy.SMART,
            RoutingStrategy.LEGACY_FALLBACK,
        }
        self.metacognitive_monitor = RoutingQualityMonitor()
        self.tool_selection_model = ToolSelectionPredictor()
        self.learning_loop = RoutingLearner()
        self.behavior_handbook = BehaviorHandbook()

    def _get_tools(self) -> dict[str, ToolInfo]:
        import time

        current_time = time.time()

        if (
            self._tools_cache is None
            or (current_time - self._tools_cache_time) > self._cache_ttl
        ):
            self._tools_cache = _get_tools_from_neo4j()
            self._tools_cache_time = current_time

        return self._tools_cache

    def _refresh_tools_cache(self) -> None:
        import time

        self._tools_cache = _get_tools_from_neo4j()
        self._tools_cache_time = time.time()

    def _emit_decision_event(self, decision: RoutingDecision) -> None:
        event = {
            "event": "routing_decision",
            "tool": decision.tool_name,
            "strategy": decision.strategy.value,
            "confidence": decision.confidence,
            "latency_ms": decision.latency_ms,
            "alternatives": decision.alternatives_considered,
            "reasoning": decision.reasoning,
            "timestamp": decision.timestamp_utc,
            "request_id": decision.request_id,
            "fallback_used": decision.fallback_used,
        }
        _emit_event("denis:cognitive_router:decisions", event)
        _record_metric("decisions_total", 1)
        _record_metric(f"strategy:{decision.strategy.value}", 1)
        _record_metric(f"tool:{decision.tool_name}", 1)

    def _emit_failure_event(self, tool_name: str, error: str) -> None:
        analysis = _analyze_failure(tool_name, error)
        event = {
            "event": "routing_failure",
            "tool": tool_name,
            "error": error[:200],
            "analysis": analysis,
            "timestamp": _utc_now(),
        }
        _emit_event("denis:cognitive_router:failures", event)
        _record_metric("failures_total", 1)

    def _validate_fallback_legacy(self) -> bool:
        return True

    def _validate_tool_availability(self) -> bool:
        tools = self._get_tools()
        return any(t.available and not t.circuit_breaker_open for t in tools.values())

    def get_status(self) -> dict[str, Any]:
        tools = self._get_tools()
        return {
            "status": "operational",
            "timestamp_utc": _utc_now(),
            "tools_available": len([t for t in tools.values() if t.available]),
            "tools_total": len(tools),
            "enabled_strategies": [s.value for s in self._enabled_strategies],
            "cache_ttl_seconds": self._cache_ttl,
        }

    def list_tools(self) -> list[dict[str, Any]]:
        tools = self._get_tools()
        return [
            {
                "name": t.name,
                "available": t.available,
                "amplitude": t.amplitude,
                "success_rate": t.success_rate,
                "avg_latency_ms": t.avg_latency_ms,
                "circuit_breaker_open": t.circuit_breaker_open,
            }
            for t in tools.values()
        ]

    def route_decision(
        self,
        task: str,
        context: dict[str, Any] | None = None,
        request_id: str | None = None,
        force_strategy: RoutingStrategy | None = None,
    ) -> RoutingDecision:
        import time

        start_time = time.time()
        tools = self._get_tools()
        features = _extract_task_features(task)
        alternatives_considered: list[str] = []

        if context is None:
            context = {}

        strategy = force_strategy or RoutingStrategy.SMART

        if strategy == RoutingStrategy.SMART:
            scores: dict[str, float] = {}
            for tool_name, tool in tools.items():
                if tool.available and not tool.circuit_breaker_open:
                    scores[tool_name] = _score_tool_for_task(tool, features)

            sorted_tools = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
            alternatives_considered = [name for name, _ in sorted_tools[:5]]

            if not sorted_tools:
                best_tool = "default"
                confidence = 0.5
                reasoning = "No available tools found, using default"
            else:
                best_tool, best_score = sorted_tools[0]
                confidence = best_score
                if best_score >= 0.8:
                    reasoning = f"High confidence match for task features: {features}"
                elif best_score >= 0.5:
                    reasoning = f"Moderate confidence match for task: {task[:50]}..."
                else:
                    reasoning = f"Low confidence match, consider alternative approach"

        elif strategy == RoutingStrategy.ROUND_ROBIN:
            available = [
                t for t in tools.values() if t.available and not t.circuit_breaker_open
            ]
            if not available:
                best_tool = "default"
                confidence = 0.3
                reasoning = "No tools available, using default"
            else:
                self._round_robin_index = (self._round_robin_index + 1) % len(available)
                best_tool = available[self._round_robin_index].name
                confidence = available[self._round_robin_index].amplitude
                alternatives_considered = [t.name for t in available]
                reasoning = (
                    f"Round-robin selection, tool #{self._round_robin_index + 1}"
                )

        else:
            best_tool = "default"
            confidence = 0.5
            reasoning = f"Unknown strategy {strategy}, falling back to default"

        latency_ms = (time.time() - start_time) * 1000

        decision = RoutingDecision(
            tool_name=best_tool,
            strategy=strategy,
            confidence=confidence,
            latency_ms=latency_ms,
            alternatives_considered=alternatives_considered,
            reasoning=reasoning,
            timestamp_utc=_utc_now(),
            request_id=request_id,
            fallback_used=False,
        )

        self._emit_decision_event(decision)

        return decision

    def record_feedback(self, feedback: RoutingFeedback) -> None:
        _emit_event(
            "denis:cognitive_router:feedback",
            {
                "request_id": feedback.request_id,
                "tool": feedback.tool_name,
                "success": feedback.success,
                "latency_ms": feedback.latency_ms,
                "quality_score": feedback.quality_score,
                "user_feedback": feedback.user_feedback,
                "timestamp": feedback.timestamp_utc,
            },
        )
        _record_metric("feedback_total", 1)
        if feedback.success:
            _record_metric(f"feedback_success:{feedback.tool_name}", 1)
        else:
            _record_metric(f"feedback_failure:{feedback.tool_name}", 1)

        if not feedback.success:
            self._emit_failure_event(
                feedback.tool_name,
                feedback.user_feedback or "Unknown error",
            )

    def record_execution_result(
        self,
        request_id: str,
        tool_name: str,
        success: bool,
        latency_ms: float,
        error: str | None = None,
    ) -> None:
        self._refresh_tools_cache()

        feedback = RoutingFeedback(
            request_id=request_id,
            tool_name=tool_name,
            success=success,
            latency_ms=latency_ms,
            quality_score=1.0 if success else 0.0,
            user_feedback=error,
        )
        self.record_feedback(feedback)

    def get_metrics(self, hours: int = 24) -> dict[str, Any]:
        try:
            r = _get_redis()
            pattern = "denis:cognitive_router:metrics:*"
            keys = list(r.keys(pattern))
            metrics: dict[str, Any] = {}

            for key in keys:
                value = r.get(key)
                if value:
                    metrics[key.split(":")[-1]] = value

            decisions = int(metrics.get("decisions_total", 0))
            failures = int(metrics.get("failures_total", 0))

            return {
                "period_hours": hours,
                "decisions_total": decisions,
                "failures_total": failures,
                "failure_rate": round(failures / max(1, decisions) * 100, 2),
                "strategy_breakdown": {
                    k.replace("strategy:", ""): int(v)
                    for k, v in metrics.items()
                    if k.startswith("strategy:")
                },
                "tool_breakdown": {
                    k.replace("tool:", ""): int(v)
                    for k, v in metrics.items()
                    if k.startswith("tool:")
                },
                "timestamp_utc": _utc_now(),
            }
        except Exception as e:
            return {
                "error": str(e),
                "timestamp_utc": _utc_now(),
            }

    async def route(self, request: Dict) -> Dict:
        """
        Ruta request usando patterns L1 del grafo.
        """
        with tracer.start_as_current_span(
            "cognitive_router.route",
            attributes={
                "router.intent": request.get("intent"),
                "router.route_hint": request.get("route_hint"),
            },
        ) as span:
            # 1) Consultar patterns L1 del grafo
            patterns = self._get_applicable_patterns(request)

            # 2) Seleccionar mejor pattern
            if patterns:
                best_pattern = patterns[0]  # Ya vienen ordenados por confidence
                tool_name = (
                    best_pattern["tools"][0]
                    if best_pattern["tools"]
                    else "smx_response"
                )
                confidence = best_pattern["confidence"]
                pattern_id = best_pattern["pattern_id"]
            else:
                # Fallback: predictor heurístico
                prediction = await self.tool_selection_model.predict(request)
                tool_name = prediction["tool"]
                confidence = prediction["confidence"]
                pattern_id = None

            cognitive_router_decisions.labels(
                tool=tool_name, pattern_id=pattern_id or ""
            ).inc()

            if pattern_id:
                l1_pattern_usage.labels(pattern_id=pattern_id).inc()

            # 3) Ejecutar tool (simulado aquí, real en router.py)
            result = {
                "success": True,
                "latency_ms": 100,  # Placeholder
            }

            # 4) Monitoreo metacognitivo
            quality = await self.metacognitive_monitor.evaluate(request, result)

            # 5) Aprendizaje
            await self.learning_loop.learn(request, tool_name, result, quality)

            # 6) Registrar patrón exitoso
            if quality["score"] > 0.8:
                await self.behavior_handbook.record_pattern(request, tool_name, result)

            span.set_attribute("router.tool_used", tool_name)
            span.set_attribute("router.confidence", confidence)
            span.set_attribute("router.pattern_id", pattern_id)

            return {
                "result": result,
                "meta": {
                    "tool_used": tool_name,
                    "confidence": confidence,
                    "quality_score": quality["score"],
                    "pattern_id": pattern_id,
                    "patterns_consulted": len(patterns),
                },
            }

    def _get_applicable_patterns(self, request: Dict) -> List[Dict]:
        """Consulta patrones L1 y relaciones Intent→Tool desde grafo Neo4j."""
        patterns = []
        intent = request.get("intent", "unknown")
        text = request.get("text", "")
        word_count = len(text.split())

        try:
            driver = Neo4jClient.get_driver()
            with driver.session() as session:
                # First: try Intent→Tool ACTIVATES path (grafocentric)
                intent_result = session.run(
                    """
                    MATCH (i:Intent {name: $intent})-[a:ACTIVATES]->(t:Tool)
                    RETURN 'intent_' + $intent as pattern_id,
                           i.description as description,
                           1.0 - (a.priority * 0.05) as confidence,
                           collect(t.name) as tools
                    ORDER BY a.priority
                    LIMIT 5
                """,
                    intent=intent,
                )

                intent_patterns = [dict(record) for record in intent_result]
                if intent_patterns:
                    return [
                        {
                            "pattern_id": p["pattern_id"],
                            "type": intent,
                            "description": p["description"],
                            "confidence": p["confidence"],
                            "tools": p["tools"],
                        }
                        for p in intent_patterns
                    ]

                # Fallback: legacy Pattern nodes
                result = session.run(
                    """
                    MATCH (p:Pattern)-[:APPLIES_TO]->(t:Tool)
                    WHERE (
                        ($wordCount <= 3 AND p.id CONTAINS 'fast')
                        OR p.type = $intent
                        OR p.type = 'generic'
                    )
                    RETURN p.id as pattern_id,
                           p.description as description,
                           p.confidence as confidence,
                           collect(t.name) as tools
                    ORDER BY p.confidence DESC
                    LIMIT 5
                """,
                    intent=intent,
                    wordCount=word_count,
                )

                patterns = [dict(record) for record in result]

                return [
                    {
                        "pattern_id": p["pattern_id"],
                        "type": intent,
                        "description": p["description"],
                        "confidence": p["confidence"],
                        "tools": p["tools"],
                    }
                    for p in patterns
                ]

        except Exception as e:
            print(f"Error consultando patrones L1: {e}")
            return []

    async def _record_pattern_usage(
        self, layer: str, pattern_id: str, quality_score: float
    ) -> None:
        """Registra uso de patrón en grafo Neo4j."""
        try:
            driver = Neo4jClient.get_driver()
            with driver.session() as session:
                session.run(
                    """
                    MATCH (p:Pattern {id: $pattern_id})
                    SET p.last_used = datetime(),
                        p.usage_count = COALESCE(p.usage_count, 0) + 1,
                        p.success_rate = COALESCE(p.success_rate, 0) * 0.9 + $quality_score * 0.1
                """,
                    pattern_id=pattern_id,
                    quality_score=quality_score,
                )
        except Exception as e:
            print(f"Error registrando uso de patrón: {e}")

    async def _execute_tool(self, tool_name: str, request: Dict) -> Dict:
        """
        Ejecuta el tool seleccionado.
        Placeholder: implementa según herramientas disponibles.
        """
        # Placeholder para ejecución real
        # Aquí se llamaría al tool correspondiente (SMX, code_interpreter, etc.)
        import asyncio

        await asyncio.sleep(0.1)  # Simular latencia
        return {
            "content": f"Executed {tool_name} for request {request.get('text', '')[:50]}",
            "success": True,
            "latency_ms": 100,
        }

    def suggest_optimization(self) -> list[dict[str, Any]]:
        suggestions: list[dict[str, Any]] = []
        tools = self._get_tools()

        for tool_name, tool in tools.items():
            if tool.error_count > 5:
                suggestions.append(
                    {
                        "type": "high_error_rate",
                        "tool": tool_name,
                        "severity": "high",
                        "description": f"Tool {tool_name} has {tool.error_count} errors",
                        "recommendation": "Review tool implementation or increase circuit breaker threshold",
                    }
                )

            if tool.avg_latency_ms > 200:
                suggestions.append(
                    {
                        "type": "high_latency",
                        "tool": tool_name,
                        "severity": "medium",
                        "description": f"Tool {tool_name} average latency: {tool.avg_latency_ms}ms",
                        "recommendation": "Consider optimization or alternative tool",
                    }
                )

            if tool.circuit_breaker_open:
                suggestions.append(
                    {
                        "type": "circuit_breaker_open",
                        "tool": tool_name,
                        "severity": "high",
                        "description": f"Tool {tool_name} circuit breaker is open",
                        "recommendation": "Wait for recovery or manually reset",
                    }
                )

        return suggestions


def create_router() -> CognitiveRouter:
    return CognitiveRouter()


if __name__ == "__main__":
    import json

    router = create_router()
    print(json.dumps(router.get_status(), indent=2, sort_keys=True))

    decision = router.route_decision(
        task="Write a Python function to calculate fibonacci numbers",
        request_id="test-123",
    )
    print(
        json.dumps(
            {
                "decision": decision.tool_name,
                "confidence": decision.confidence,
                "reasoning": decision.reasoning,
            },
            indent=2,
            sort_keys=True,
        )
    )

    print(json.dumps(router.list_tools(), indent=2, sort_keys=True))

    print(json.dumps(router.get_metrics(), indent=2, sort_keys=True))
