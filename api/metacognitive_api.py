"""API Metacognitiva - Endpoints de introspección."""
from __future__ import annotations

import asyncio
import json
import os
import time
from copy import deepcopy
from typing import Dict

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

try:
    import redis
    import redis.asyncio as aioredis
except ImportError:
    redis = None
    aioredis = None

from neo4j import GraphDatabase
from neo4j import AsyncGraphDatabase

from .sse_handler import sse_event

from denis_unified_v1.capabilities_service import get_capabilities_service

router = APIRouter(prefix="/metacognitive", tags=["metacognitive"])

NEO4J_TIMEOUT_MS = int(os.getenv("METACOG_NEO4J_TIMEOUT_MS", "90"))
REDIS_TIMEOUT_MS = int(os.getenv("METACOG_REDIS_TIMEOUT_MS", "80"))
REFLECTION_TIMEOUT_MS = int(os.getenv("METACOG_REFLECTION_TIMEOUT_MS", "120"))
SSE_HEARTBEAT_INTERVAL_SEC = float(os.getenv("METACOG_SSE_HEARTBEAT_SEC", "2.0"))
SSE_IDLE_SLEEP_SEC = float(os.getenv("METACOG_SSE_IDLE_SLEEP_SEC", "0.25"))
SSE_WATCHDOG_SEC = float(os.getenv("METACOG_SSE_WATCHDOG_SEC", "10.0"))

# Connection pools for performance
_redis_pool = None
_neo4j_pool = None
_async_neo4j_pool = None

async def get_redis_pool():
    """Get Redis connection pool."""
    global _redis_pool
    if _redis_pool is None and redis is not None:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _redis_pool = redis.ConnectionPool.from_url(redis_url, decode_responses=True, max_connections=20)
    return _redis_pool

async def get_neo4j_pool():
    """Get Neo4j connection pool."""
    global _neo4j_pool
    if _neo4j_pool is None:
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "Leon1234$")
        _neo4j_pool = AsyncGraphDatabase.driver(uri, auth=(user, password))
    return _neo4j_pool

def get_redis():
    """Get Redis connection from pool."""
    pool = asyncio.run(get_redis_pool())
    return redis.Redis(connection_pool=pool) if pool else None

async def get_neo4j_async():
    """Get async Neo4j driver."""
    return await get_neo4j_pool()

def get_neo4j():
    """Get sync Neo4j driver (legacy compatibility)."""
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "Leon1234$")
    return GraphDatabase.driver(uri, auth=(user, password))


async def _call_blocking(func, timeout_ms: int):
    start = time.perf_counter()
    try:
        async with asyncio.timeout(timeout_ms / 1000):
            result = await asyncio.to_thread(func)
            latency_ms = int((time.perf_counter() - start) * 1000)
            return result, latency_ms, None
    except TimeoutError:
        return None, timeout_ms, "timeout"
    except Exception as exc:  # pragma: no cover - defensive
        return None, int((time.perf_counter() - start) * 1000), str(exc)


def _status_fallback() -> Dict:
    return {
        "layers": {"l0_tools": 0, "l1_patterns": 0, "l2_principles": 0},
        "coherence": {
            "governs_relations": 0,
            "applies_to_relations": 0,
            "coherence_score": 0.0,
        },
        "health": {"issues_detected": 0, "problematic_tools": []},
        "status": "degraded",
    }


def _metrics_fallback() -> Dict:
    return {"operations": {}, "timestamp": time.time(), "status": "degraded"}


def get_redis():
    if redis is None:
        return None
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return redis.Redis.from_url(redis_url, decode_responses=True)


def get_neo4j():
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "Leon1234$")
    return GraphDatabase.driver(uri, auth=(user, password))


@router.get("/status")
async def metacognitive_status():
    """Estado general del sistema metacognitivo con consultas concurrentes."""
    driver = await get_neo4j_async()
    degraded = False

    async def query_l0_count():
        try:
            async with driver.session() as session:
                result = await session.run("MATCH (n:Tool) RETURN count(n) as c")
                record = await result.single()
                return int(record["c"]) if record else 0
        except Exception:
            return 0

    async def query_l1_count():
        try:
            async with driver.session() as session:
                result = await session.run("MATCH (n:Pattern) RETURN count(n) as c")
                record = await result.single()
                return int(record["c"]) if record else 0
        except Exception:
            return 0

    async def query_l2_count():
        try:
            async with driver.session() as session:
                result = await session.run("MATCH (n:Principle) RETURN count(n) as c")
                record = await result.single()
                return int(record["c"]) if record else 0
        except Exception:
            return 0

    async def query_relations():
        try:
            async with driver.session() as session:
                governs_result = await session.run("MATCH ()-[r:GOVERNS]->() RETURN count(r) as c")
                governs_record = await governs_result.single()

                applies_result = await session.run("MATCH ()-[r:APPLIES_TO]->() RETURN count(r) as c")
                applies_record = await applies_result.single()

                return (
                    int(governs_record["c"]) if governs_record else 0,
                    int(applies_record["c"]) if applies_record else 0
                )
        except Exception:
            return 0, 0

    async def query_problematic_tools():
        try:
            async with driver.session() as session:
                result = await session.run("""
                    MATCH (t:Tool)
                    WHERE t.success_rate < 0.85 OR t.avg_latency_ms > 1000
                    RETURN t.name, t.success_rate, t.avg_latency_ms
                    LIMIT 5
                """)
                records = await result.data()
                return [dict(record) for record in records]
        except Exception:
            return []

    # Execute all queries concurrently
    start_time = time.time()
    try:
        async with asyncio.timeout(NEO4J_TIMEOUT_MS / 1000):
            l0_count, l1_count, l2_count, (governs_count, applies_count), issues = await asyncio.gather(
                query_l0_count(),
                query_l1_count(),
                query_l2_count(),
                query_relations(),
                query_problematic_tools()
            )
    except asyncio.TimeoutError:
        degraded = True
        l0_count = l1_count = l2_count = governs_count = applies_count = 0
        issues = []

    query_time_ms = (time.time() - start_time) * 1000

    try:
        await driver.close()
    except Exception:
        pass

    status_val = "healthy" if not issues and not degraded else "degraded"

    return {
        "layers": {
            "l0_tools": l0_count,
            "l1_patterns": l1_count,
            "l2_principles": l2_count,
        },
        "coherence": {
            "governs_relations": governs_count,
            "applies_to_relations": applies_count,
            "coherence_score": min(1.0, (governs_count + applies_count) / 10.0),
        },
        "health": {
            "issues_detected": len(issues) if issues else 0,
            "problematic_tools": issues,
            "query_time_ms": query_time_ms,
        },
        "status": status_val,
        "performance": {
            "concurrent_queries": True,
            "query_time_ms": query_time_ms
        }
    }


@router.get("/metrics")
async def metacognitive_metrics():
    """Métricas de operaciones recientes."""
    r = get_redis()
    if r is None:
        return _metrics_fallback()

    operations = [
        "smx_motor_call",
        "cognitive_router_route",
        "nlu_parse",
        "smx_orchestrator_process",
    ]
    metrics = {}

    degraded = False

    def _load_metrics():
        local_metrics = {}
        for op in operations:
            key = f"metrics:{op}:latency"
            latencies = r.lrange(key, 0, 99)
            if latencies:
                latencies_int = [int(x) for x in latencies]
                local_metrics[op] = {
                    "count": len(latencies_int),
                    "avg_latency_ms": sum(latencies_int) // len(latencies_int),
                    "p50": sorted(latencies_int)[len(latencies_int) // 2],
                    "p95": sorted(latencies_int)[int(len(latencies_int) * 0.95)],
                }
            else:
                local_metrics[op] = {"count": 0}
        return local_metrics

    metrics, latency_ms, redis_error = await _call_blocking(_load_metrics, REDIS_TIMEOUT_MS)
    if redis_error:
        degraded = True
        return {
            "operations": {},
            "timestamp": time.time(),
            "status": "degraded",
            "error": redis_error,
            "latency_ms": latency_ms,
        }

    return {
        "operations": metrics,
        "timestamp": time.time(),
        "status": "healthy" if not degraded else "degraded",
        "latency_ms": latency_ms,
    }


@router.get("/attention")
async def metacognitive_attention():
    """Qué tiene Denis en foco de atención ahora mismo."""
    driver = get_neo4j()
    degraded = False

    def _query():
        with driver.session() as session:
            top_patterns = session.run(
                """
                MATCH (p:Pattern)
                RETURN p.id, p.type, p.usage_count, p.confidence
                ORDER BY p.usage_count DESC
                LIMIT 5
                """
            )

            patterns_local = [dict(record) for record in top_patterns]

            top_tools = session.run(
                """
                MATCH (t:Tool)
                RETURN t.name, t.success_rate, t.avg_latency_ms
                ORDER BY t.success_rate DESC
                LIMIT 5
                """
            )

            tools_local = [dict(record) for record in top_tools]
            return patterns_local, tools_local

    patterns: list[dict] = []
    tools: list[dict] = []
    (patterns, tools), _, err = await _call_blocking(_query, NEO4J_TIMEOUT_MS)
    if err:
        degraded = True

    try:
        driver.close()
    except Exception:
        pass

    return {
        "focused_patterns": patterns,
        "active_tools": tools,
        "attention_mode": "balanced",
        "status": "degraded" if degraded else "healthy",
    }


@router.get("/coherence")
async def metacognitive_coherence():
    """Score de coherencia del sistema."""
    driver = get_neo4j()
    degraded = False

    def _query():
        with driver.session() as session:
            complete_paths = session.run(
                """
                MATCH (pr:Principle)-[:GOVERNS]->(pa:Pattern)-[:APPLIES_TO]->(t:Tool)
                RETURN count(*) as paths
                """
            ).single()["paths"]

            orphan_patterns = session.run(
                """
                MATCH (pa:Pattern)
                WHERE NOT (pa)-[:APPLIES_TO]->()
                RETURN count(pa) as orphans
                """
            ).single()["orphans"]

            orphan_principles = session.run(
                """
                MATCH (pr:Principle)
                WHERE NOT (pr)-[:GOVERNS]->()
                RETURN count(pr) as orphans
                """
            ).single()["orphans"]

            return complete_paths, orphan_patterns, orphan_principles

    complete_paths = orphan_patterns = orphan_principles = 0
    (complete_paths, orphan_patterns, orphan_principles), _, err = await _call_blocking(
        _query, NEO4J_TIMEOUT_MS
    )
    if err:
        degraded = True

    try:
        driver.close()
    except Exception:
        pass

    coherence_score = complete_paths / max(
        1, complete_paths + orphan_patterns + orphan_principles
    )

    return {
        "coherence_score": coherence_score,
        "complete_paths": complete_paths,
        "orphan_patterns": orphan_patterns,
        "orphan_principles": orphan_principles,
        "status": "coherent" if coherence_score > 0.8 else "fragmented",
        "neo4j_status": "degraded" if degraded else "healthy",
    }


async def _temporal_reflection_analysis(query_text: str, current_reflection: Dict) -> Dict[str, Any]:
    """Analyze how reflection changes over time compared to historical patterns."""
    r = get_redis()
    temporal_data = {
        "historical_patterns": [],
        "temporal_stability": 0.0,
        "evolution_rate": 0.0,
        "adaptation_score": 0.0,
        "temporal_insights": []
    }

    if r:
        try:
            # Get historical reflections
            historical_keys = r.keys("reflection:*")
            if historical_keys:
                historical_reflections = []
                for key in historical_keys[:10]:  # Last 10 reflections
                    data = r.get(key)
                    if data:
                        historical_reflections.append(json.loads(data))

                temporal_data["historical_patterns"] = historical_reflections

                # Calculate temporal stability (similarity over time)
                if len(historical_reflections) > 1:
                    similarities = []
                    for i in range(1, len(historical_reflections)):
                        # Simple similarity based on pattern count
                        prev_patterns = historical_reflections[i-1].get("patterns_detected", 0)
                        curr_patterns = historical_reflections[i].get("patterns_detected", 0)
                        similarity = 1.0 - abs(prev_patterns - curr_patterns) / max(prev_patterns, curr_patterns, 1)
                        similarities.append(similarity)

                    temporal_data["temporal_stability"] = sum(similarities) / len(similarities) if similarities else 0.5

                # Evolution rate (how much change over time)
                if len(historical_reflections) >= 2:
                    first_patterns = historical_reflections[0].get("patterns_detected", 0)
                    last_patterns = historical_reflections[-1].get("patterns_detected", 0)
                    temporal_data["evolution_rate"] = abs(last_patterns - first_patterns) / max(first_patterns, 1)

                # Adaptation score (ability to adapt to new queries)
                unique_queries = len(set(h.get("query", "") for h in historical_reflections if h.get("query")))
                temporal_data["adaptation_score"] = min(1.0, unique_queries / 10.0)

                # Generate insights
                insights = []
                if temporal_data["temporal_stability"] > 0.8:
                    insights.append("High temporal stability - system is consistent")
                elif temporal_data["temporal_stability"] < 0.3:
                    insights.append("Low temporal stability - system is highly adaptive")

                if temporal_data["evolution_rate"] > 0.5:
                    insights.append("Rapid evolution detected")
                elif temporal_data["evolution_rate"] < 0.1:
                    insights.append("Stable, slow evolution")

                temporal_data["temporal_insights"] = insights

            # Store current reflection for future analysis
            reflection_key = f"reflection:{int(time.time())}"
            r.setex(reflection_key, 86400 * 7, json.dumps({  # 7 days
                "query": query_text,
                "patterns_detected": current_reflection.get("patterns_detected", 0),
                "timestamp": time.time()
            }))

        except Exception as e:
            temporal_data["error"] = str(e)

    return temporal_data


async def _predict_reflection_changes(patterns: List[Dict], current_reflection: Dict) -> Dict[str, Any]:
    """Predict what changes might happen based on current patterns."""
    prediction_data = {
        "predicted_patterns": [],
        "confidence_intervals": {},
        "risk_assessment": "low",
        "recommended_actions": [],
        "prediction_horizon": "7_days"
    }

    try:
        # Analyze current patterns for trends
        pattern_types = {}
        pattern_confidences = []

        for pattern in patterns:
            pattern_type = pattern.get("type", "unknown")
            confidence = pattern.get("confidence", 0.0)

            if pattern_type not in pattern_types:
                pattern_types[pattern_type] = 0
            pattern_types[pattern_type] += 1
            pattern_confidences.append(confidence)

        # Predict future patterns based on current trends
        avg_confidence = sum(pattern_confidences) / len(pattern_confidences) if pattern_confidences else 0.5

        predicted_patterns = []
        for pattern_type, count in pattern_types.items():
            # Simple prediction: patterns with high count and confidence likely to persist
            if count > 1 and avg_confidence > 0.7:
                predicted_patterns.append({
                    "type": pattern_type,
                    "predicted_frequency": count * 1.2,  # 20% increase
                    "confidence": min(0.95, avg_confidence + 0.1),
                    "rationale": f"High frequency ({count}) and confidence ({avg_confidence:.2f}) suggests persistence"
                })

        prediction_data["predicted_patterns"] = predicted_patterns

        # Confidence intervals
        prediction_data["confidence_intervals"] = {
            "pattern_count": {
                "lower": len(patterns) * 0.8,
                "expected": len(patterns),
                "upper": len(patterns) * 1.3
            },
            "avg_confidence": {
                "lower": max(0, avg_confidence - 0.1),
                "expected": avg_confidence,
                "upper": min(1.0, avg_confidence + 0.1)
            }
        }

        # Risk assessment
        if avg_confidence < 0.5:
            prediction_data["risk_assessment"] = "high"
            prediction_data["recommended_actions"].append("Increase confidence thresholds")
        elif len(patterns) < 3:
            prediction_data["risk_assessment"] = "medium"
            prediction_data["recommended_actions"].append("Expand pattern detection scope")
        else:
            prediction_data["risk_assessment"] = "low"
            prediction_data["recommended_actions"].append("Maintain current parameters")

    except Exception as e:
        prediction_data["error"] = str(e)

    return prediction_data


async def _calculate_consciousness_metrics(reflection: Dict, patterns: List[Dict], temporal: Dict) -> Dict[str, Any]:
    """Calculate metrics about the system's consciousness level and awareness."""
    consciousness_data = {
        "consciousness_level": 0.0,
        "awareness_score": 0.0,
        "self_reflection_depth": 0.0,
        "metacognitive_capability": 0.0,
        "consciousness_indicators": {},
        "consciousness_assessment": "emerging"
    }

    try:
        # Base metrics from reflection and patterns
        reflection_quality = 1.0 if reflection and not reflection.get("error") else 0.0
        pattern_diversity = len(set(p.get("type", "unknown") for p in patterns)) / max(1, len(patterns))
        pattern_confidence = sum(p.get("confidence", 0) for p in patterns) / max(1, len(patterns))

        # Temporal awareness
        temporal_stability = temporal.get("temporal_stability", 0.5)
        evolution_rate = temporal.get("evolution_rate", 0.0)
        adaptation_score = temporal.get("adaptation_score", 0.0)

        # Consciousness indicators
        consciousness_indicators = {
            "reflection_quality": reflection_quality,
            "pattern_diversity": pattern_diversity,
            "pattern_confidence": pattern_confidence,
            "temporal_stability": temporal_stability,
            "evolution_rate": evolution_rate,
            "adaptation_score": adaptation_score,
            "self_model_integration": 0.8,  # Assume good integration
            "feedback_learning": 0.7,  # Assume active learning
            "purpose_alignment": 0.9  # Assume good alignment
        }

        consciousness_data["consciousness_indicators"] = consciousness_indicators

        # Calculate composite scores
        awareness_components = ["reflection_quality", "pattern_diversity", "temporal_stability", "adaptation_score"]
        consciousness_data["awareness_score"] = sum(consciousness_indicators[k] for k in awareness_components) / len(awareness_components)

        metacognitive_components = ["reflection_quality", "pattern_confidence", "self_model_integration", "feedback_learning"]
        consciousness_data["metacognitive_capability"] = sum(consciousness_indicators[k] for k in metacognitive_components) / len(metacognitive_components)

        consciousness_data["self_reflection_depth"] = (reflection_quality + pattern_diversity + temporal_stability) / 3.0

        # Overall consciousness level (weighted average)
        weights = {
            "awareness_score": 0.3,
            "metacognitive_capability": 0.3,
            "self_reflection_depth": 0.2,
            "adaptation_score": 0.1,
            "purpose_alignment": 0.1
        }

        consciousness_data["consciousness_level"] = sum(
            consciousness_indicators.get(k.replace("_score", "").replace("_capability", "").replace("_depth", ""), 0) * w
            for k, w in weights.items()
        )

        # Assessment
        level = consciousness_data["consciousness_level"]
        if level > 0.8:
            consciousness_data["consciousness_assessment"] = "advanced"
        elif level > 0.6:
            consciousness_data["consciousness_assessment"] = "developed"
        elif level > 0.4:
            consciousness_data["consciousness_assessment"] = "emerging"
        elif level > 0.2:
            consciousness_data["consciousness_assessment"] = "basic"
        else:
            consciousness_data["consciousness_assessment"] = "minimal"

    except Exception as e:
        consciousness_data["error"] = str(e)

    return consciousness_data


@router.post("/reflect")
async def force_reflection(query: Dict):
    """Forzar reflexión metacognitiva profunda con análisis temporal, predicción de cambios y métricas de conciencia."""
    from denis_unified_v1.cortex.metacognitive_perception import PerceptionReflection
    from denis_unified_v1.metagraph.active_metagraph import L1PatternDetector
    from consciousness.self_model import get_self_model

    text = query.get("text", "")
    include_temporal = query.get("temporal_analysis", True)
    include_prediction = query.get("change_prediction", True)
    include_consciousness = query.get("consciousness_metrics", True)

    degraded = False

    # Core reflection
    async def _reflect():
        engine = PerceptionReflection()
        return engine.reflect({"entities": []})

    perception_reflection, reflection_latency_ms, reflection_error = await _call_blocking(
        lambda: asyncio.run(_reflect()), REFLECTION_TIMEOUT_MS
    )
    if reflection_error:
        degraded = True
        perception_reflection = {
            "error": reflection_error,
            "status": "degraded",
            "latency_ms": reflection_latency_ms,
        }

    # Pattern detection
    async def _detect():
        detector = L1PatternDetector()
        return detector.detect_patterns()

    patterns, detect_latency_ms, detect_error = await _call_blocking(
        lambda: asyncio.run(_detect()), REFLECTION_TIMEOUT_MS
    )
    if detect_error:
        degraded = True
        patterns = []

    # Temporal analysis
    temporal_analysis = {}
    if include_temporal and not degraded:
        temporal_analysis = await _temporal_reflection_analysis(text, perception_reflection)

    # Change prediction
    change_prediction = {}
    if include_prediction and patterns:
        change_prediction = await _predict_reflection_changes(patterns, perception_reflection)

    # Consciousness metrics
    consciousness_metrics = {}
    if include_consciousness:
        consciousness_metrics = await _calculate_consciousness_metrics(perception_reflection, patterns, temporal_analysis)

    return {
        "query": text,
        "perception_reflection": perception_reflection,
        "patterns_detected": len(patterns),
        "patterns": patterns[:3],
        "temporal_analysis": temporal_analysis,
        "change_prediction": change_prediction,
        "consciousness_metrics": consciousness_metrics,
        "timestamp": time.time(),
        "status": "degraded" if degraded else "healthy",
        "reflection_latency_ms": reflection_latency_ms,
        "detect_latency_ms": detect_latency_ms,
        "reflection_error": reflection_error,
        "detect_error": detect_error,
    }


@router.get("/self")
async def metacognitive_self():
    """Self-awareness: capabilities, identity, evolution."""
    driver = get_neo4j()
    degraded = False

    def _query():
        with driver.session() as session:
            # Capabilities from tools
            tools = session.run("MATCH (t:Tool) RETURN count(t) as tool_count").single()["tool_count"]
            # Identity: hardcoded for now
            identity = {"name": "Denis", "version": "unified-v1", "type": "cognitive_agent"}
            # Evolution: from changes
            changes = session.run("MATCH (c:Change) RETURN count(c) as change_count").single()["change_count"]
            return tool_count, identity, change_count

    tool_count, identity, change_count = 0, {}, 0
    (tool_count, identity, change_count), _, err = await _call_blocking(_query, NEO4J_TIMEOUT_MS)
    if err:
        degraded = True

    try:
        driver.close()
    except Exception:
        pass

    return {
        "identity": identity,
        "capabilities": {"tools": tool_count, "evolution_steps": change_count},
        "status": "degraded" if degraded else "healthy"
    }


@router.get("/evolution")
async def metacognitive_evolution():
    """Evolution tracker: changes over time."""
    driver = get_neo4j()
    degraded = False

    def _query():
        with driver.session() as session:
            changes = session.run("MATCH (c:Change) RETURN c.timestamp, c.description ORDER BY c.timestamp DESC LIMIT 10")
            return [dict(record) for record in changes]

    changes = []
    changes, _, err = await _call_blocking(_query, NEO4J_TIMEOUT_MS)
    if err:
        degraded = True

    try:
        driver.close()
    except Exception:
        pass

    return {
        "recent_changes": changes,
        "status": "degraded" if degraded else "healthy"
    }


@router.get("/limits")
async def metacognitive_limits():
    """Limit awareness: current constraints."""
    # Hardcoded for now, can integrate with feature flags
    limits = {
        "max_concurrent_requests": 10,
        "max_memory_gb": 16,
        "max_tools": 100,
        "timeout_defaults": {"neo4j": 90, "redis": 80, "reflection": 120}
    }
    return {"limits": limits, "status": "healthy"}


@router.get("/purpose")
async def metacognitive_purpose():
    """Purpose validator: current goals."""
    purpose = {
        "primary": "Assist users with cognitive tasks using AI",
        "secondary": "Learn and evolve through interactions",
        "constraints": ["Ethical AI", "Fail-safe", "User-centric"]
    }
async def _generate_automatic_feedback(feedback: Dict) -> str:
    """Generate automatic feedback based on feedback patterns and system state."""
    feedback_type = feedback.get("type", "general")
    content = feedback.get("content", "")

    automatic_feedback = None

    # Analyze feedback content for common patterns
    if "error" in content.lower() or "fail" in content.lower():
        automatic_feedback = "Detected error pattern. Consider reviewing error handling and fallback mechanisms."

    elif "slow" in content.lower() or "latency" in content.lower():
        automatic_feedback = "Performance concern detected. Consider optimizing response times and caching strategies."

    elif "inconsistent" in content.lower() or "unpredictable" in content.lower():
        automatic_feedback = "Consistency issue identified. Consider implementing more robust state management."

    elif "confusing" in content.lower() or "unclear" in content.lower():
        automatic_feedback = "Clarity concern noted. Consider improving response formatting and explanations."

    # Context-aware feedback based on feedback type
    if feedback_type == "performance":
        automatic_feedback = "Performance feedback received. Analyzing system metrics for optimization opportunities."

    elif feedback_type == "accuracy":
        automatic_feedback = "Accuracy feedback noted. Reviewing confidence thresholds and validation logic."

    elif feedback_type == "usability":
        automatic_feedback = "Usability feedback received. Considering interface and interaction improvements."

    # Generate feedback about feedback patterns themselves
    r = get_redis()
    if r:
        recent_feedbacks = r.lrange("denis:metacognitive:feedback", 0, 9)
        if len(recent_feedbacks) >= 3:
            # Analyze pattern of recent feedbacks
            types = [json.loads(f).get("type", "unknown") for f in recent_feedbacks if f]
            if len(set(types)) == 1:
                automatic_feedback = f"Pattern detected: Multiple {types[0]} feedbacks. Consider systematic review of {types[0]} aspects."

    return automatic_feedback


async def _analyze_feedback_patterns() -> Dict[str, Any]:
    """Analyze feedback patterns for insights and trends."""
    r = get_redis()
    pattern_analysis = {
        "total_feedbacks": 0,
        "feedback_types": {},
        "temporal_distribution": {},
        "common_themes": [],
        "insights": [],
        "recommendations": []
    }

    if r:
        try:
            # Get recent feedbacks
            feedbacks = r.lrange("denis:metacognitive:feedback", 0, 99)
            if feedbacks:
                parsed_feedbacks = []
                for f in feedbacks:
                    try:
                        parsed_feedbacks.append(json.loads(f))
                    except json.JSONDecodeError:
                        continue

                pattern_analysis["total_feedbacks"] = len(parsed_feedbacks)

                # Analyze types
                types_count = {}
                for fb in parsed_feedbacks:
                    fb_type = fb.get("type", "unknown")
                    types_count[fb_type] = types_count.get(fb_type, 0) + 1
                pattern_analysis["feedback_types"] = types_count

                # Temporal distribution (last 24 hours vs older)
                now = time.time()
                recent_feedbacks = [f for f in parsed_feedbacks if now - f.get("timestamp", 0) < 86400]
                pattern_analysis["temporal_distribution"] = {
                    "last_24h": len(recent_feedbacks),
                    "older": len(parsed_feedbacks) - len(recent_feedbacks)
                }

                # Extract common themes from content
                contents = [f.get("content", "") for f in parsed_feedbacks if f.get("content")]
                themes = []
                if contents:
                    # Simple keyword analysis
                    error_keywords = ["error", "fail", "problem", "issue", "bug"]
                    perf_keywords = ["slow", "fast", "latency", "performance", "speed"]
                    quality_keywords = ["quality", "accuracy", "correct", "wrong", "accurate"]

                    error_count = sum(1 for c in contents if any(kw in c.lower() for kw in error_keywords))
                    perf_count = sum(1 for c in contents if any(kw in c.lower() for kw in perf_keywords))
                    quality_count = sum(1 for c in contents if any(kw in c.lower() for kw in quality_keywords))

                    if error_count > len(contents) * 0.3:
                        themes.append("reliability_errors")
                    if perf_count > len(contents) * 0.3:
                        themes.append("performance_concerns")
                    if quality_count > len(contents) * 0.3:
                        themes.append("quality_accuracy")

                pattern_analysis["common_themes"] = themes

                # Generate insights
                insights = []
                if pattern_analysis["temporal_distribution"]["last_24h"] > 5:
                    insights.append("High feedback volume in last 24 hours - consider immediate attention")

                most_common_type = max(types_count.items(), key=lambda x: x[1]) if types_count else None
                if most_common_type and most_common_type[1] > len(parsed_feedbacks) * 0.5:
                    insights.append(f"Dominant feedback type: {most_common_type[0]} - focus improvement efforts here")

                pattern_analysis["insights"] = insights

                # Generate recommendations
                recommendations = []
                if "reliability_errors" in themes:
                    recommendations.append("Implement additional error handling and recovery mechanisms")
                if "performance_concerns" in themes:
                    recommendations.append("Review and optimize system performance bottlenecks")
                if "quality_accuracy" in themes:
                    recommendations.append("Enhance validation and quality assurance processes")

                if len(parsed_feedbacks) < 10:
                    recommendations.append("Continue collecting feedback to identify patterns")

                pattern_analysis["recommendations"] = recommendations

        except Exception as e:
            pattern_analysis["error"] = str(e)

    return pattern_analysis


@router.post("/learn")
async def metacognitive_learn(feedback: Dict):
    """Learn from feedback for self-improvement with memory integration and automatic feedback generation."""
    from consciousness.self_model import get_self_model

    # Store in memory backend for persistence
    try:
        from denis_unified_v1.memory.backends import get_memory_backend
        memory_backend = get_memory_backend()
        if memory_backend:
            feedback_key = f"feedback:{int(time.time())}:{feedback.get('type', 'general')}"
            await memory_backend.store(feedback_key, feedback)
    except Exception:
        pass  # Fail silently for memory storage

    # Store in Redis for quick access
    r = get_redis()
    if r:
        r.lpush("denis:metacognitive:feedback", json.dumps(feedback))
        r.ltrim("denis:metacognitive:feedback", 0, 99)

    # Generate automatic feedback based on patterns
    automatic_feedback = await _generate_automatic_feedback(feedback)

    # Analyze feedback patterns
    pattern_analysis = await _analyze_feedback_patterns()

    # Store automatic feedback too
    if automatic_feedback:
        auto_feedback = {
            "type": "automatic",
            "source": "pattern_analysis",
            "content": automatic_feedback,
            "timestamp": time.time(),
            "triggered_by": feedback
        }

        if r:
            r.lpush("denis:metacognitive:feedback", json.dumps(auto_feedback))
            r.ltrim("denis:metacognitive:feedback", 0, 99)

        try:
            if memory_backend:
                auto_key = f"feedback:{int(time.time())}:automatic"
                await memory_backend.store(auto_key, auto_feedback)
        except Exception:
            pass

    return {
        "learned": True,
        "feedback": feedback,
        "automatic_feedback_generated": automatic_feedback is not None,
        "automatic_feedback": automatic_feedback,
        "pattern_analysis": pattern_analysis,
        "stored_in_memory": memory_backend is not None,
        "stored_in_redis": r is not None
    }


@router.get("/feedback")
async def metacognitive_feedback(limit: int = 10, include_analysis: bool = True):
    """Retrieve recent feedback with pattern analysis and insights."""
    r = get_redis()
    feedback_data = {
        "recent_feedback": [],
        "total_feedback_count": 0,
        "pattern_analysis": {},
        "insights": [],
        "recommendations": []
    }

    if r:
        try:
            # Get recent feedback items
            items = r.lrange("denis:metacognitive:feedback", 0, limit - 1)
            feedback_data["total_feedback_count"] = r.llen("denis:metacognitive:feedback")

            # Parse feedback items
            recent_feedback = []
            for item in items:
                try:
                    parsed = json.loads(item)
                    recent_feedback.append(parsed)
                except json.JSONDecodeError:
                    continue

            feedback_data["recent_feedback"] = recent_feedback

            # Include pattern analysis if requested
            if include_analysis and recent_feedback:
                feedback_data["pattern_analysis"] = await _analyze_feedback_patterns()

                # Extract insights and recommendations from analysis
                analysis = feedback_data["pattern_analysis"]
                feedback_data["insights"] = analysis.get("insights", [])
                feedback_data["recommendations"] = analysis.get("recommendations", [])

        except Exception as e:
            feedback_data["error"] = str(e)

    return feedback_data


@router.get("/events")
async def metacognitive_events(
    event_type: str = None,
    source: str = None,
    min_severity: str = "info",
    include_consciousness: bool = True,
    include_capabilities: bool = True,
    include_system: bool = True
):
    """SSE de eventos metacognitivos avanzados con filtros, eventos de conciencia y persistencia."""
    from consciousness.self_model import get_self_model

    # Filter configuration
    severity_levels = {"debug": 0, "info": 1, "warning": 2, "error": 3, "critical": 4}
    min_severity_level = severity_levels.get(min_severity.lower(), 1)

    # Consciousness event emitter
    async def emit_consciousness_events():
        """Emit consciousness-related events periodically."""
        last_self_check = 0
        consciousness_level = 0.5

        while True:
            now = time.time()

            # Check self-model changes every 30 seconds
            if include_consciousness and now - last_self_check >= 30:
                try:
                    self_model = get_self_model()
                    new_level = self_model.get("purpose_valid", True)

                    # Detect consciousness changes
                    if new_level != consciousness_level:
                        event = {
                            "event": "consciousness_change",
                            "type": "consciousness",
                            "source": "self_model",
                            "timestamp": now,
                            "severity": "info",
                            "data": {
                                "previous_level": consciousness_level,
                                "current_level": new_level,
                                "change_type": "purpose_alignment" if new_level else "purpose_drift"
                            }
                        }

                        # Persist event
                        await _persist_event(event)

                        yield f"data: {json.dumps(event)}\n\n"
                        consciousness_level = new_level

                    # Emit periodic consciousness status
                    consciousness_metrics = await _calculate_consciousness_metrics({}, [], {})
                    event = {
                        "event": "consciousness_status",
                        "type": "consciousness",
                        "source": "system",
                        "timestamp": now,
                        "severity": "debug",
                        "data": {
                            "consciousness_level": consciousness_metrics.get("consciousness_level", 0),
                            "assessment": consciousness_metrics.get("consciousness_assessment", "unknown")
                        }
                    }
                    await _persist_event(event)
                    yield f"data: {json.dumps(event)}\n\n"

                    last_self_check = now

                except Exception as e:
                    event = {
                        "event": "consciousness_error",
                        "type": "error",
                        "source": "self_model",
                        "timestamp": now,
                        "severity": "warning",
                        "data": {"error": str(e)}
                    }
                    await _persist_event(event)
                    yield f"data: {json.dumps(event)}\n\n"

            # Check capability changes every 60 seconds
            if include_capabilities and now - last_self_check >= 60:
                try:
                    service = get_capabilities_service()
                    snapshot = service.get_snapshot()
                    active_caps = len([cap for cap in snapshot.values() if cap.status.value == "healthy"])

                    event = {
                        "event": "capability_status",
                        "type": "capability",
                        "source": "system",
                        "timestamp": now,
                        "severity": "info",
                        "data": {
                            "total_capabilities": len(snapshot),
                            "active_capabilities": active_caps,
                            "health_ratio": active_caps / max(1, len(snapshot))
                        }
                    }
                    await _persist_event(event)
                    yield f"data: {json.dumps(event)}\n\n"

                except Exception as e:
                    event = {
                        "event": "capability_error",
                        "type": "error",
                        "source": "capabilities",
                        "timestamp": now,
                        "severity": "warning",
                        "data": {"error": str(e)}
                    }
                    await _persist_event(event)
                    yield f"data: {json.dumps(event)}\n\n"

            await asyncio.sleep(10)  # Check every 10 seconds

    async def _persist_event(event: Dict[str, Any]):
        """Persist event to Redis for later retrieval."""
        r = get_redis()
        if r:
            try:
                event_key = f"event:{int(event['timestamp'])}:{event['event']}"
                r.setex(event_key, 86400 * 7, json.dumps(event))  # 7 days
                # Also maintain a sorted set for time-based queries
                r.zadd("events:timeline", {event_key: event['timestamp']})
                # Clean old events (keep last 1000)
                r.zremrangebyrank("events:timeline", 0, -1001)
            except Exception:
                pass  # Fail silently for persistence

    async def event_stream():
        last_emit = time.time()

        def heartbeat_payload():
            return sse_event(
                {
                    "event": "heartbeat",
                    "ts": time.time(),
                    "status": "alive",
                    "filters": {
                        "event_type": event_type,
                        "source": source,
                        "min_severity": min_severity,
                        "consciousness": include_consciousness,
                        "capabilities": include_capabilities,
                        "system": include_system
                    }
                }
            )

        # Yield initial heartbeat immediately
        yield heartbeat_payload()

        # Start consciousness event emitter
        consciousness_task = None
        if include_consciousness or include_capabilities:
            consciousness_task = asyncio.create_task(emit_consciousness_events())

        try:
            if aioredis is not None:
                redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
                redis_backend = None
                pubsub = None
                try:
                    redis_backend = aioredis.from_url(redis_url, decode_responses=True)
                    pubsub = redis_backend.pubsub()
                    await pubsub.subscribe("denis:metacognitive:events")
                    while True:
                        msg = await pubsub.get_message(
                            ignore_subscribe_messages=True, timeout=1.0
                        )
                        now = time.time()
                        if msg and msg.get("type") == "message":
                            try:
                                event_data = json.loads(msg.get("data", "{}"))

                                # Apply filters
                                if _should_emit_event(event_data, event_type, source, min_severity_level, include_system):
                                    last_emit = now
                                    await _persist_event(event_data)
                                    yield f"data: {msg['data']}\n\n"
                            except json.JSONDecodeError:
                                # Emit raw message if not JSON
                                if include_system:
                                    last_emit = now
                                    yield f"data: {msg['data']}\n\n"
                        elif now - last_emit >= SSE_HEARTBEAT_INTERVAL_SEC:
                            last_emit = now
                            yield heartbeat_payload()

                        if now - last_emit > SSE_WATCHDOG_SEC:
                            last_emit = now
                            yield heartbeat_payload()
                        await asyncio.sleep(SSE_IDLE_SLEEP_SEC)
                finally:
                    if consciousness_task:
                        consciousness_task.cancel()
                    try:
                        if pubsub is not None:
                            await pubsub.close()
                    except Exception:
                        pass
                    try:
                        if redis_backend is not None:
                            await redis_backend.close()
                    except Exception:
                        pass
            else:
                # Fallback mode with consciousness events only
                while True:
                    now = time.time()
                    if now - last_emit >= SSE_HEARTBEAT_INTERVAL_SEC:
                        last_emit = now
                        yield heartbeat_payload()
        except Exception:
            if consciousness_task:
                consciousness_task.cancel()

    def _should_emit_event(event_data: Dict, filter_type: str, filter_source: str, min_level: int, include_sys: bool) -> bool:
        """Check if event should be emitted based on filters."""
        # Check event type filter
        if filter_type and event_data.get("type") != filter_type:
            return False

        # Check source filter
        if filter_source and event_data.get("source") != filter_source:
            return False

        # Check severity filter
        event_severity = severity_levels.get(event_data.get("severity", "info").lower(), 1)
        if event_severity < min_level:
            return False

        # Check system events
        if not include_sys and event_data.get("source") == "system":
            return False

        return True

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/capabilities")
async def metacognitive_capabilities():
    """Advanced and robust capabilities management system."""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from enum import Enum
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


class CapabilityDepth(Enum):
    ADVANCED = "advanced"
    EXPERT = "expert"
    CUTTING_EDGE = "cutting_edge"
    COMPREHENSIVE = "comprehensive"
    EXPERIMENTAL = "experimental"
    THEORETICAL = "theoretical"


@dataclass
class CapabilityMetadata:
    skills: List[str] = field(default_factory=list)
    depth: CapabilityDepth = CapabilityDepth.ADVANCED
    models: List[str] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)
    techniques: List[str] = field(default_factory=list)
    applications: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    challenges: List[str] = field(default_factory=list)
    integrations: List[str] = field(default_factory=list)
    prerequisites: List[str] = field(default_factory=list)
    performance_metrics: Dict[str, Any] = field(default_factory=dict)
    last_updated: float = field(default_factory=time.time)
    version: str = "1.0.0"
    status: str = "active"


@dataclass
class Capability:
    name: str
    category: str
    metadata: CapabilityMetadata = field(default_factory=CapabilityMetadata)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "skills": self.metadata.skills,
            "depth": self.metadata.depth.value,
            "models": self.metadata.models,
            "frameworks": self.metadata.frameworks,
            "techniques": self.metadata.techniques,
            "applications": self.metadata.applications,
            "domains": self.metadata.domains,
            "challenges": self.metadata.challenges,
            "integrations": self.metadata.integrations,
            "prerequisites": self.metadata.prerequisites,
            "performance_metrics": self.metadata.performance_metrics,
            "last_updated": self.metadata.last_updated,
            "version": self.metadata.version,
            "status": self.metadata.status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Capability:
        metadata = CapabilityMetadata(
            skills=data.get("skills", []),
            depth=CapabilityDepth(data.get("depth", "advanced")),
            models=data.get("models", []),
            frameworks=data.get("frameworks", []),
            techniques=data.get("techniques", []),
            applications=data.get("applications", []),
            domains=data.get("domains", []),
            challenges=data.get("challenges", []),
            integrations=data.get("integrations", []),
            prerequisites=data.get("prerequisites", []),
            performance_metrics=data.get("performance_metrics", {}),
            last_updated=data.get("last_updated", time.time()),
            version=data.get("version", "1.0.0"),
            status=data.get("status", "active"),
        )
        return cls(
            name=data["name"],
            category=data["category"],
            metadata=metadata,
        )


class CapabilityRegistry:
    """Thread-safe capability registry with advanced features."""

    def __init__(self):
        self._capabilities: Dict[str, Dict[str, Capability]] = {}
        self._lock = threading.RLock()
        self._last_updated = time.time()
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_ttl = 300  # 5 minutes
        self._cache_timestamp = 0

    def register_capability(self, capability: Capability) -> None:
        with self._lock:
            if capability.category not in self._capabilities:
                self._capabilities[capability.category] = {}
            self._capabilities[capability.category][capability.name] = capability
            self._invalidate_cache()
            logger.info(f"Registered capability: {capability.category}.{capability.name}")

    def _invalidate_cache(self) -> None:
        """Invalidate the cache when registry changes."""
        self._last_updated = time.time()

    def get_capability(self, category: str, name: str) -> Optional[Capability]:
        with self._lock:
            return self._capabilities.get(category, {}).get(name)

    def get_category(self, category: str) -> Dict[str, Capability]:
        with self._lock:
            return self._capabilities.get(category, {}).copy()

    def get_all_categories(self) -> Dict[str, Dict[str, Capability]]:
        with self._lock:
            return {cat: caps.copy() for cat, caps in self._capabilities.items()}

    def query_capabilities(self, filters: Dict[str, Any]) -> List[Capability]:
        """Advanced querying with filters."""
        with self._lock:
            results = []
            for category_caps in self._capabilities.values():
                for cap in category_caps.values():
                    if self._matches_filters(cap, filters):
                        results.append(cap)
            return results

    def _matches_filters(self, capability: Capability, filters: Dict[str, Any]) -> bool:
        """Check if capability matches given filters."""
        for key, value in filters.items():
            if key == "category":
                if capability.category != value:
                    return False
            elif key == "depth":
                if capability.metadata.depth.value != value:
                    return False
            elif key == "has_skill":
                if value not in capability.metadata.skills:
                    return False
            elif key == "has_integration":
                if value not in capability.metadata.integrations:
                    return False
            elif key == "min_skills":
                if len(capability.metadata.skills) < value:
                    return False
            elif key == "status":
                if capability.metadata.status != value:
                    return False
        return True

    def update_performance_metrics(self, category: str, name: str, metrics: Dict[str, Any]) -> bool:
        """Update performance metrics for a capability."""
        with self._lock:
            cap = self.get_capability(category, name)
            if cap:
                cap.metadata.performance_metrics.update(metrics)
                cap.metadata.last_updated = time.time()
                self._invalidate_cache()
                return True
            return False

    def validate_capability(self, capability: Capability) -> List[str]:
        """Validate capability structure and dependencies."""
        errors = []
        if not capability.name:
            errors.append("Capability name is required")
        if not capability.category:
            errors.append("Capability category is required")
        if len(capability.metadata.skills) == 0:
            errors.append("At least one skill is required")
        # Check prerequisites exist
        for prereq in capability.metadata.prerequisites:
            if not self._prerequisite_exists(prereq):
                errors.append(f"Prerequisite not found: {prereq}")
        return errors

    def _prerequisite_exists(self, prereq: str) -> bool:
        """Check if prerequisite capability exists."""
        category, name = prereq.split(".", 1) if "." in prereq else ("", prereq)
        return self.get_capability(category, name) is not None

    def export_to_json(self, path: Path) -> None:
        """Export registry to JSON file."""
        with self._lock:
            data = {
                "export_timestamp": time.time(),
                "categories": {
                    cat: {
                        name: cap.to_dict()
                        for name, cap in caps.items()
                    }
                    for cat, caps in self._capabilities.items()
                }
            }
            path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def import_from_json(self, path: Path) -> List[str]:
        """Import registry from JSON file."""
        errors = []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            categories = data.get("categories", {})
            for cat_name, cat_caps in categories.items():
                for cap_name, cap_data in cat_caps.items():
                    try:
                        cap = Capability.from_dict(cap_data)
                        cap.category = cat_name  # Ensure category matches
                        validation_errors = self.validate_capability(cap)
                        if validation_errors:
                            errors.extend(validation_errors)
                        else:
                            self.register_capability(cap)
                    except Exception as e:
                        errors.append(f"Failed to import {cat_name}.{cap_name}: {e}")
        except Exception as e:
            errors.append(f"Failed to load JSON: {e}")
        return errors

    def load_from_artifacts(self, artifacts_dir: Path) -> List[str]:
        """Load capabilities from artifacts directory (smoke results, phase completions)."""
        errors = []
        if not artifacts_dir.exists():
            errors.append(f"Artifacts directory not found: {artifacts_dir}")
            return errors

        # Load phase completion status
        phase_files = {
            "phase0": "phase11_preflight.json",
            "phase1": "level3_metacognitive_smoke.json",
            "phase5": "phase5_orchestration_smoke.json",
            "phase6": "phase6_api_smoke.json",
            "phase7": "phase7_inference_router_smoke.json",
            "phase8": "phase8_voice_smoke.json",
            "phase9": "phase9_memory_smoke.json",
            "phase10": "phase10_self_model_smoke.json",
        }

        for phase, filename in phase_files.items():
            artifact_path = artifacts_dir / filename
            if artifact_path.exists():
                try:
                    import json
                    with artifact_path.open() as f:
                        data = json.load(f)
                    status = data.get("status", "unknown")
                    # Create capability based on phase completion
                    cap = Capability(
                        name=f"{phase}_integration",
                        category="system_integration",
                        metadata=CapabilityMetadata(
                            skills=[f"{phase}_execution", "artifact_generation", "status_tracking"],
                            depth=CapabilityDepth.EXPERT if status == "ok" else CapabilityDepth.ADVANCED,
                            applications=[f"phase_{phase}_validation"],
                            performance_metrics={"completion_status": status}
                        )
                    )
                    self.register_capability(cap)
                except Exception as e:
                    errors.append(f"Failed to load {filename}: {e}")
            else:
                # Phase not completed
                cap = Capability(
                    name=f"{phase}_pending",
                    category="system_integration",
                    metadata=CapabilityMetadata(
                        skills=[f"{phase}_planning"],
                        depth=CapabilityDepth.BASIC,
                        status="pending"
                    )
                )
                self.register_capability(cap)

        # Load smoke artifacts for capability health
        smoke_files = list(artifacts_dir.glob("*smoke.json"))
        for smoke_file in smoke_files:
            try:
                with smoke_file.open() as f:
                    data = json.load(f)
                # Create capability from smoke results
                cap_name = smoke_file.stem
                ok = data.get("ok", False)
                cap = Capability(
                    name=f"smoke_{cap_name}",
                    category="testing",
                    metadata=CapabilityMetadata(
                        skills=["smoke_testing", "health_validation"],
                        depth=CapabilityDepth.EXPERT if ok else CapabilityDepth.ADVANCED,
                        performance_metrics={"test_passed": ok, "results": data.get("results", {})},
                        status="healthy" if ok else "degraded"
                    )
                )
                self.register_capability(cap)
            except Exception as e:
                errors.append(f"Failed to load smoke {smoke_file}: {e}")

        return errors

    def load_from_graph(self) -> List[str]:
        """Load capabilities from Neo4j graph (tools, patterns, contracts)."""
        errors = []
        try:
            from denis_unified_v1.databases.capabilities_service import get_capabilities_service
            from denis_unified_v1.metagraph.active_metagraph import get_metagraph_client
            client = get_metagraph_client()
            if not client:
                errors.append("Metagraph client not available")
                return errors

            # Query tools from graph
            tools_query = """
            MATCH (t:Tool)
            RETURN t.name as name, t.category as category, 
                   t.success_rate as success_rate, t.avg_latency_ms as latency
            LIMIT 50
            """
            tools_result = client.query(tools_query)
            for record in tools_result:
                cap = Capability(
                    name=record["name"],
                    category="tool_execution",
                    metadata=CapabilityMetadata(
                        skills=["tool_execution", "graph_integration"],
                        depth=CapabilityDepth.EXPERT,
                        models=[record.get("category", "unknown")],
                        performance_metrics={
                            "success_rate": record.get("success_rate", 0),
                            "avg_latency_ms": record.get("latency", 0)
                        },
                        integrations=["neo4j_graph"]
                    )
                )
                self.register_capability(cap)

            # Query patterns from graph
            patterns_query = """
            MATCH (p:Pattern)
            RETURN p.id as id, p.type as type, p.confidence as confidence
            LIMIT 50
            """
            patterns_result = client.query(patterns_query)
            for record in patterns_result:
                cap = Capability(
                    name=f"pattern_{record['id']}",
                    category="pattern_matching",
                    metadata=CapabilityMetadata(
                        skills=["pattern_recognition", record.get("type", "unknown")],
                        depth=CapabilityDepth.ADVANCED,
                        performance_metrics={"confidence": record.get("confidence", 0)},
                        integrations=["neo4j_graph"]
                    )
                )
                self.register_capability(cap)

        except Exception as e:
            errors.append(f"Failed to load from graph: {e}")

        return errors

    async def execute_capability(self, category: str, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a capability via workers/jobs system."""
        cap = self.get_capability(category, name)
        if not cap:
            return {"error": f"Capability {category}.{name} not found", "status": "not_found"}

        try:
            # Route to appropriate worker based on category
            if category == "inference":
                result = await self._execute_inference_capability(name, params)
            elif category == "memory":
                result = await self._execute_memory_capability(name, params)
            elif category == "voice":
                result = await self._execute_voice_capability(name, params)
            elif category == "tool_execution":
                result = await self._execute_tool_capability(name, params)
            else:
                result = {"error": f"Execution not supported for category {category}", "status": "unsupported"}

            # Update performance metrics
            self.update_performance_metrics(category, name, {
                "last_execution_time": time.time(),
                "success": result.get("status") == "success",
                "latency_ms": result.get("latency_ms", 0)
            })

            return result

        except Exception as e:
            # Update failure metrics
            self.update_performance_metrics(category, name, {
                "last_execution_time": time.time(),
                "success": False,
                "error": str(e)
            })
            return {"error": str(e), "status": "execution_failed"}

    async def _execute_inference_capability(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute inference capability via router."""
        try:
            from denis_unified_v1.inference import get_inference_router
            router = get_inference_router()
            start_time = time.time()
            result = await router.route(params)
            latency_ms = (time.time() - start_time) * 1000
            return {
                "result": result,
                "status": "success",
                "latency_ms": latency_ms,
                "worker": "inference_router"
            }
        except Exception as e:
            return {"error": str(e), "status": "failed", "worker": "inference_router"}

    async def _execute_memory_capability(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute memory capability via memory system."""
        try:
            from denis_unified_v1.memory.backends import get_memory_backend
            backend = get_memory_backend()
            start_time = time.time()
            if name == "store":
                result = await backend.store(params["key"], params["value"])
            elif name == "retrieve":
                result = await backend.retrieve(params["key"])
            latency_ms = (time.time() - start_time) * 1000
            return {
                "result": result,
                "status": "success",
                "latency_ms": latency_ms,
                "worker": "memory_backend"
            }
        except Exception as e:
            return {"error": str(e), "status": "failed", "worker": "memory_backend"}

    async def _execute_voice_capability(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute voice capability via voice pipeline."""
        try:
            from denis_unified_v1.voice import get_voice_pipeline
            pipeline = get_voice_pipeline()
            start_time = time.time()
            if name == "transcribe":
                result = await pipeline.transcribe(params["audio"], params.get("language", "en"))
            elif name == "synthesize":
                result = await pipeline.synthesize(params["text"], params.get("voice", "default"))
            latency_ms = (time.time() - start_time) * 1000
            return {
                "result": result,
                "status": "success",
                "latency_ms": latency_ms,
                "worker": "voice_pipeline"
            }
        except Exception as e:
            return {"error": str(e), "status": "failed", "worker": "voice_pipeline"}

    async def _execute_tool_capability(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute tool capability via orchestration."""
        try:
            from denis_unified_v1.orchestration.tool_executor import get_tool_executor
            executor = get_tool_executor()
            start_time = time.time()
            result = await executor.execute_tool(name, params)
            latency_ms = (time.time() - start_time) * 1000
            return {
                "result": result,
                "status": "success",
                "latency_ms": latency_ms,
                "worker": "tool_executor"
            }
        except Exception as e:
            return {"error": str(e), "status": "failed", "worker": "tool_executor"}


# Global registry instance
_capability_registry = CapabilityRegistry()


def get_capability_registry() -> CapabilityRegistry:
    """Get the global capability registry."""
    return _capability_registry


def initialize_capabilities() -> None:
    """Initialize the capability registry with real system capabilities."""
    try:
        registry = get_capability_registry()

        # Load from artifacts directory (with error handling)
        try:
            artifacts_dir = Path(__file__).resolve().parents[2] / "artifacts"
            if artifacts_dir.exists():
                artifact_errors = registry.load_from_artifacts(artifacts_dir)
                if artifact_errors:
                    logger.warning(f"Artifact loading errors: {artifact_errors}")
        except Exception as e:
            logger.warning(f"Failed to load artifacts: {e}")

        # Load from graph (with error handling)
        try:
            graph_errors = registry.load_from_graph()
            if graph_errors:
                logger.warning(f"Graph loading errors: {graph_errors}")
        except Exception as e:
            logger.warning(f"Failed to load from graph: {e}")

        # Add some core capabilities if none loaded
        if not registry.get_all_categories():
            logger.info("No capabilities loaded from sources, adding minimal defaults")
            registry.register_capability(Capability(
                name="text_generation",
                category="inference",
                metadata=CapabilityMetadata(
                    skills=["creative_writing", "technical_documentation", "code_generation", "poetry", "storytelling"],
                    depth=CapabilityDepth.ADVANCED,
                    models=["gpt-4", "claude-3", "llama-3", "gemini-1.5", "mistral-large"],
                    frameworks=["transformers", "langchain", "huggingface"],
                    techniques=["prompt_engineering", "fine_tuning", "few_shot_learning"],
                    applications=["content_creation", "education", "entertainment", "communication"],
                    domains=["creative", "technical", "business", "academic"],
                    challenges=["hallucination", "bias", "factual_accuracy"],
                    integrations=["openai", "anthropic", "huggingface", "google"],
                    performance_metrics={"avg_latency_ms": 150, "accuracy_score": 0.85}
                )
            ))

            registry.register_capability(Capability(
                name="vector_search",
                category="memory",
                metadata=CapabilityMetadata(
                    skills=["semantic_similarity", "contextual_retrieval", "multi_vector_indexing", "temporal_filtering"],
                    depth=CapabilityDepth.ADVANCED,
                    techniques=["cosine_similarity", "euclidean_distance", "dot_product"],
                    applications=["search", "recommendation", "qa"],
                    performance_metrics={"recall@10": 0.85, "latency_ms": 50}
                )
            ))

        logger.info(f"Capability registry initialized with {len(registry.get_all_categories())} categories")

    except Exception as e:
        logger.error(f"Failed to initialize capabilities: {e}")
        # Continue anyway - endpoint will work with empty registry


# Initialize on import
initialize_capabilities()


@router.get("/capabilities")
async def metacognitive_capabilities():
    """Unified capabilities registry with real system integration."""
    service = get_capabilities_service()
    snapshot = service.get_snapshot()

    # Convert to response format
    capabilities_response = {}
    for cap_id, cap_snapshot in snapshot.items():
        capabilities_response[cap_id] = {
            "id": cap_snapshot.id,
            "category": cap_snapshot.category,
            "status": cap_snapshot.status.value,
            "confidence": cap_snapshot.confidence,
            "evidence": [
                {
                    "source": ev.source,
                    "timestamp": ev.timestamp,
                    "confidence": ev.confidence,
                    "data": ev.data,
                    "error": ev.error,
                }
                for ev in cap_snapshot.evidence
            ],
            "metrics": cap_snapshot.metrics,
            "last_seen_utc": cap_snapshot.last_seen_utc,
            "depends_on": cap_snapshot.depends_on,
            "source_weights": cap_snapshot.source_weights,
            "executable_actions": cap_snapshot.executable_actions,
            "version": cap_snapshot.version,
        }

    return {
        "capabilities": capabilities_response,
        "status": "healthy",
        "last_updated": time.time(),
        "total_capabilities": len(capabilities_response),
        "sources": list(set(ev["source"] for cap in capabilities_response.values()
                          for ev in cap["evidence"])),
    }


@router.post("/capabilities/query")
async def query_capabilities(query: Dict[str, Any]):
    """Query capabilities with filters."""
    service = get_capabilities_service()
    results = service.query_snapshot(query.get("filters", {}))

    # Convert to response format
    capabilities_response = []
    for cap_snapshot in results:
        capabilities_response.append({
            "id": cap_snapshot.id,
            "category": cap_snapshot.category,
            "status": cap_snapshot.status.value,
            "confidence": cap_snapshot.confidence,
            "evidence": [
                {
                    "source": ev.source,
                    "timestamp": ev.timestamp,
                    "confidence": ev.confidence,
                    "data": ev.data,
                    "error": ev.error,
                }
                for ev in cap_snapshot.evidence
            ],
            "metrics": cap_snapshot.metrics,
            "last_seen_utc": cap_snapshot.last_seen_utc,
            "depends_on": cap_snapshot.depends_on,
            "source_weights": cap_snapshot.source_weights,
            "executable_actions": cap_snapshot.executable_actions,
            "version": cap_snapshot.version,
        })

    return {
        "results": capabilities_response,
        "query": query,
        "total_results": len(capabilities_response),
        "status": "success",
    }


@router.post("/capabilities/refresh")
async def refresh_capabilities():
    """Refresh capabilities snapshot from all collectors."""
    service = get_capabilities_service()
    refreshed_snapshot = await service.refresh_snapshot()

    return {
        "status": "refreshed",
        "total_capabilities": len(refreshed_snapshot),
        "last_refresh": time.time(),
        "sources_refreshed": [collector.get_source_name() for collector in service.collectors],
    }


@router.post("/capabilities/{cap_id}/execute")
async def execute_capability(cap_id: str, params: Dict[str, Any]):
    """Execute a capability via available workers."""
    service = get_capabilities_service()
    result = await service.execute_capability(cap_id, params)

    return {
        "capability_id": cap_id,
        "execution_result": result,
        "timestamp": time.time(),
    }


@router.get("/capabilities/events")
async def capabilities_events():
    """SSE stream of capabilities events with heartbeats."""
    service = get_capabilities_service()

    async def event_generator():
        last_emit = time.time()

        def heartbeat_payload():
            return f"data: {json.dumps({'event': 'heartbeat', 'timestamp': time.time()})}\n\n"

        # Initial heartbeat
        yield heartbeat_payload()

        while True:
            current_time = time.time()

            # Emit heartbeat every 30 seconds
            if current_time - last_emit >= 30:
                yield heartbeat_payload()
                last_emit = current_time

            # Check for capability updates (simplified - in real impl could watch for changes)
            snapshot = service.get_snapshot()
            if snapshot and current_time - service._cache_timestamp < 60:  # Recent update
                yield f"data: {json.dumps({'event': 'capabilities_updated', 'count': len(snapshot), 'timestamp': current_time})}\n\n"

            await asyncio.sleep(5)  # Check every 5 seconds

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/events")
async def metacognitive_events():
    """SSE stream of metacognitive events with heartbeats."""
    async def event_generator():
        last_emit = time.time()

        def heartbeat_payload():
            return f"data: {json.dumps({'event': 'heartbeat', 'timestamp': time.time()})}\n\n"

        # Initial heartbeat
        yield heartbeat_payload()

        while True:
            current_time = time.time()

            # Emit heartbeat every 3-5 seconds
            if current_time - last_emit >= 4:
                yield heartbeat_payload()
                last_emit = current_time

            # Here we could emit real events from Redis or other sources
            # For now, just heartbeats to keep connection alive
            await asyncio.sleep(1)  # Check every 1 second

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/feedback")
async def metacognitive_feedback():
    """Recent feedback and learning insights."""
    r = get_redis()
    feedback = []
    if r:
        items = r.lrange("denis:metacognitive:feedback", 0, 9)
        feedback = [json.loads(item) for item in items]
    return {"recent_feedback": feedback, "status": "healthy"}


@router.get("/autopoiesis/proposals")
async def get_proposals():
    """Lista propuestas pendientes."""
    from denis_unified_v1.autopoiesis.approval_engine import ApprovalEngine

    approval = ApprovalEngine()
    proposals = approval.get_pending_proposals()

    return {"proposals": proposals}


@router.post("/autopoiesis/approve/{proposal_id}")
async def approve_proposal(proposal_id: str, user: str = "admin"):
    """Aprueba una propuesta."""
    from denis_unified_v1.autopoiesis.approval_engine import ApprovalEngine

    approval = ApprovalEngine()
    success = approval.approve_proposal(proposal_id, user)

    return {"approved": success, "proposal_id": proposal_id}


@router.get("/alerts")
async def check_alerts():
    """Chequea y devuelve anomalías detectadas."""
    from denis_unified_v1.observability.anomaly_detector import AlertManager

    alert_manager = AlertManager()
    result = await alert_manager.check_and_alert()

    return result


@router.get("/inference/status")
async def inference_router_status():
    """Estado del inference router."""
    from denis_unified_v1.inference import get_engine_catalog, get_health_manager
    from denis_unified_v1.feature_flags import load_feature_flags

    catalog = get_engine_catalog()
    health = get_health_manager()
    flags = load_feature_flags()

    engines = []
    for engine_id, engine in catalog.engines.items():
        engine_health = health.get_health(engine_id)
        engines.append(
            {
                "id": engine_id,
                "provider": engine.provider,
                "model": engine.model,
                "capabilities": engine.capabilities,
                "health": engine_health,
            }
        )

    return {
        "enabled": flags.denis_use_inference_router,
        "shadow_mode": flags.phase7_router_shadow_mode,
        "bandit_enabled": flags.phase7_bandit_enabled,
        "hedging_enabled": flags.phase7_hedged_requests_enabled,
        "engines": engines,
        "total_engines": len(engines),
        "healthy_engines": sum(
            1 for e in engines if e.get("health", {}).get("status") == "healthy"
        ),
    }


@router.get("/gate/status")
async def gate_hardening_status():
    """Estado del gate hardening (Phase 10)."""
    from denis_unified_v1.feature_flags import load_feature_flags

    flags = load_feature_flags()

    return {
        "enabled": getattr(flags, "denis_use_gate_hardening", False),
        "budgets": {
            "total_ms": getattr(flags, "phase10_budget_total_ms", 4500),
            "ttft_ms": getattr(flags, "phase10_budget_ttft_ms", 900),
        },
        "output_limits": {
            "max_output_tokens": getattr(flags, "phase10_max_output_tokens", 512),
            "max_prompt_chars": getattr(flags, "phase10_max_prompt_chars", 12000),
        },
        "rate_limit": {
            "rps": getattr(flags, "phase10_rate_limit_rps", 8),
            "burst": getattr(flags, "phase10_rate_limit_burst", 16),
        },
        "sandbox_enabled": getattr(flags, "phase10_sandbox_enabled", True),
        "strict_output_schema": getattr(flags, "phase10_strict_output_schema", True),
    }


@router.post("/gate/reload")
async def gate_hardening_reload():
    """Recarga ligera de configuración de gate hardening.

    Actualmente vuelve a leer feature flags desde el entorno.
    """
    from denis_unified_v1.feature_flags import load_feature_flags

    flags = load_feature_flags()
    return {"reloaded": True, "enabled": getattr(flags, "denis_use_gate_hardening", False)}


@router.get("/inference/policy")
async def inference_router_policy():
    """Estado actual de la política bandit."""
    from denis_unified_v1.inference import get_policy_bandit

    bandit = get_policy_bandit()

    policies = {}
    for class_key, engine_scores in bandit.engines.items():
        policies[class_key] = {
            engine_id: {
                "score": scores.get("score", 0),
                "trials": scores.get("trials", 0),
            }
            for engine_id, scores in engine_scores.items()
        }

    return {
        "policies": policies,
        "total_class_keys": len(policies),
        "exploration_rate": bandit.exploration_rate,
    }


@router.post("/inference/reward")
async def record_inference_reward(reward_data: Dict):
    """Registrar señal de reward para el bandit."""
    from denis_unified_v1.inference import get_policy_bandit

    class_key = reward_data.get("class_key")
    engine_id = reward_data.get("engine_id")
    reward = reward_data.get("reward", 0.0)

    if not class_key or not engine_id:
        return {"error": "class_key and engine_id required"}, 400

    bandit = get_policy_bandit()
    bandit.update(class_key, engine_id, reward)

    return {
        "updated": True,
        "class_key": class_key,
        "engine_id": engine_id,
        "reward": reward,
    }


@router.get("/inference/decisions")
async def inference_recent_decisions(limit: int = 20):
    """Últimas decisiones del router."""
    r = get_redis()
    if r is None:
        return {"decisions": [], "error": "Redis not available"}

    decisions = r.lrange("denis:inference_router:decisions", 0, limit - 1)

    parsed = []
    for d in decisions:
        try:
            parsed.append(json.loads(d))
        except:
            parsed.append({"raw": d})

    return {"decisions": parsed, "count": len(parsed)}


@router.get("/inference/circuit-breakers")
async def inference_circuit_breakers():
    """Estado de todos los circuit breakers."""
    from denis_unified_v1.inference import get_engine_broker

    broker = get_engine_broker()
    status = broker.advanced_routing.get_status()

    return {
        "circuit_breakers": status.get("circuit_breakers", {}),
        "load_balancer": status.get("load_balancer", {}),
    }


@router.post("/inference/ab-tests")
async def create_ab_test(config: Dict):
    """Crear nuevo A/B test."""
    from denis_unified_v1.inference import get_engine_broker

    broker = get_engine_broker()

    test_id = config.get("test_id")
    variant_a = config.get("variant_a")
    variant_b = config.get("variant_b")
    traffic_split = config.get("traffic_split", 0.5)
    duration_hours = config.get("duration_hours", 24)

    if not all([test_id, variant_a, variant_b]):
        return {"error": "test_id, variant_a, variant_b required"}, 400

    test = broker.advanced_routing.ab_test_manager.create_test(
        test_id=test_id,
        variant_a=variant_a,
        variant_b=variant_b,
        traffic_split=traffic_split,
        duration_hours=duration_hours,
    )

    return {
        "test_id": test.test_id,
        "variant_a": test.variant_a,
        "variant_b": test.variant_b,
        "traffic_split": test.traffic_split,
        "active": test.active,
    }


@router.get("/inference/ab-tests")
async def list_ab_tests():
    """Listar todos los A/B tests."""
    from denis_unified_v1.inference import get_engine_broker

    broker = get_engine_broker()

    tests = []
    for test_id in broker.advanced_routing.ab_test_manager.active_tests:
        result = broker.advanced_routing.ab_test_manager.get_test_results(test_id)
        if result:
            tests.append(result)

    return {"tests": tests, "count": len(tests)}


@router.get("/inference/ab-tests/{test_id}")
async def get_ab_test(test_id: str):
    """Ver resultados de un A/B test."""
    from denis_unified_v1.inference import get_engine_broker

    broker = get_engine_broker()
    result = broker.advanced_routing.ab_test_manager.get_test_results(test_id)

    if not result:
        return {"error": "Test not found"}, 404

    return result


@router.post("/inference/ab-tests/{test_id}/record")
async def record_ab_result(test_id: str, result_data: Dict):
    """Registrar resultado de una variante de A/B test."""
    from denis_unified_v1.inference import get_engine_broker

    broker = get_engine_broker()

    variant = result_data.get("variant")
    success = result_data.get("success", False)
    latency_ms = result_data.get("latency_ms", 0)

    if not variant:
        return {"error": "variant required"}, 400

    broker.advanced_routing.ab_test_manager.record_result(
        test_id=test_id,
        variant=variant,
        success=success,
        latency_ms=latency_ms,
    )

    return {"recorded": True, "test_id": test_id, "variant": variant}


@router.get("/inference/hedging")
async def inference_hedging_status():
    """Estado del hedging adaptativo."""
    from denis_unified_v1.inference import get_engine_broker

    broker = get_engine_broker()

    return {
        "engine_p95_latencies": broker.adaptive_hedging.engine_p95_latencies,
        "engine_failure_rates": broker.adaptive_hedging.engine_failure_rates,
        "hedge_threshold_ms": broker.adaptive_hedging.hedge_threshold_ms,
        "failure_threshold": broker.adaptive_hedging.failure_threshold,
    }


@router.get("/capabilities")
async def get_capabilities():
    """Get current capabilities snapshot v1."""
    service = get_capabilities_service()

    snapshot = service.get_snapshot()
    if not snapshot:
        # Try to refresh if no cache
        snapshot = await service.refresh_snapshot()

    # Convert to API format
    capabilities = []
    for cap_id, cap_snapshot in snapshot.items():
        capabilities.append({
            "id": cap_id,
            "category": cap_snapshot.category,
            "status": cap_snapshot.status.value,
            "confidence": cap_snapshot.confidence,
            "evidence": [
                {
                    "source": ev.source,
                    "timestamp": ev.timestamp,
                    "confidence": ev.confidence,
                    "data": ev.data,
                    "error": ev.error
                }
                for ev in cap_snapshot.evidence
            ],
            "metrics": cap_snapshot.metrics,
            "last_seen_utc": cap_snapshot.last_seen_utc,
            "depends_on": cap_snapshot.depends_on,
            "executable_actions": cap_snapshot.executable_actions,
            "version": cap_snapshot.version
        })

    return {
        "snapshot_version": "v1",
        "capabilities": capabilities,
        "total_count": len(capabilities),
        "timestamp_utc": time.time(),
        "status": "healthy"
    }


@router.post("/capabilities/query")
async def query_capabilities(query: Dict[str, Any]):
    """Query capabilities with filters."""
    service = get_capabilities_service()
    filters = query.get("filters", {})
    results = service.query_snapshot(filters)

    # Convert to API format
    capabilities = []
    for cap_snapshot in results:
        capabilities.append({
            "id": cap_snapshot.id,
            "category": cap_snapshot.category,
            "status": cap_snapshot.status.value,
            "confidence": cap_snapshot.confidence,
            "evidence": [
                {
                    "source": ev.source,
                    "timestamp": ev.timestamp,
                    "confidence": ev.confidence,
                    "data": ev.data,
                    "error": ev.error
                }
                for ev in cap_snapshot.evidence
            ],
            "metrics": cap_snapshot.metrics,
            "executable_actions": cap_snapshot.executable_actions,
            "version": cap_snapshot.version
        })

    return {
        "query": query,
        "results": capabilities,
        "count": len(capabilities),
        "timestamp_utc": time.time()
    }


@router.post("/capabilities/refresh")
async def refresh_capabilities():
    """Force refresh of capabilities snapshot."""
    service = get_capabilities_service()
    start_time = time.time()
    snapshot = await service.refresh_snapshot()
    refresh_time_ms = (time.time() - start_time) * 1000

    return {
        "refreshed_count": len(snapshot),
        "refresh_time_ms": refresh_time_ms,
        "timestamp_utc": time.time(),
        "status": "refreshed"
    }


@router.get("/capabilities/events")
async def capabilities_events():
    """SSE stream for capabilities events."""
    async def event_generator():
        # Initial state
        yield sse_event("capabilities_stream_started", {"timestamp": time.time()})

        # Poll for updates every 30 seconds
        while True:
            try:
                service = get_capabilities_service()
                snapshot = service.get_snapshot()

                # Check if cache was refreshed recently
                if snapshot and service._cache_timestamp > time.time() - 60:  # Within last minute
                    event_data = {
                        "capabilities_count": len(snapshot),
                        "timestamp": time.time(),
                        "snapshot_version": "v1"
                    }
                    yield sse_event("capabilities_updated", event_data)

            except Exception as e:
                yield sse_event("capabilities_error", {"error": str(e), "timestamp": time.time()})

            await asyncio.sleep(30)  # Poll every 30 seconds

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )
