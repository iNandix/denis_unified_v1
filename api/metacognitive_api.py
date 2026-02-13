"""API Metacognitiva - Endpoints de introspección."""

from fastapi import APIRouter
from typing import Dict, List
import json
import time
import os

try:
    import redis
except ImportError:
    redis = None

from neo4j import GraphDatabase

router = APIRouter(prefix="/metacognitive", tags=["metacognitive"])


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
    """Estado general del sistema metacognitivo."""
    driver = get_neo4j()

    with driver.session() as session:
        l0_count = session.run("MATCH (n:Tool) RETURN count(n) as c").single()["c"]
        l1_count = session.run("MATCH (n:Pattern) RETURN count(n) as c").single()["c"]
        l2_count = session.run("MATCH (n:Principle) RETURN count(n) as c").single()["c"]

        governs_count = session.run(
            "MATCH ()-[r:GOVERNS]->() RETURN count(r) as c"
        ).single()["c"]
        applies_count = session.run(
            "MATCH ()-[r:APPLIES_TO]->() RETURN count(r) as c"
        ).single()["c"]

        problematic = session.run("""
            MATCH (t:Tool)
            WHERE t.success_rate < 0.85 OR t.avg_latency_ms > 1000
            RETURN t.name, t.success_rate, t.avg_latency_ms
            LIMIT 5
        """)

        issues = [dict(record) for record in problematic]

    driver.close()

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
            "issues_detected": len(issues),
            "problematic_tools": issues,
        },
        "status": "healthy" if len(issues) == 0 else "degraded",
    }


@router.get("/metrics")
async def metacognitive_metrics():
    """Métricas de operaciones recientes."""
    r = get_redis()
    if r is None:
        return {
            "operations": {},
            "timestamp": time.time(),
            "error": "Redis not available",
        }

    operations = [
        "smx_motor_call",
        "cognitive_router_route",
        "nlu_parse",
        "smx_orchestrator_process",
    ]
    metrics = {}

    for op in operations:
        key = f"metrics:{op}:latency"
        latencies = r.lrange(key, 0, 99)

        if latencies:
            latencies_int = [int(x) for x in latencies]
            metrics[op] = {
                "count": len(latencies_int),
                "avg_latency_ms": sum(latencies_int) // len(latencies_int),
                "p50": sorted(latencies_int)[len(latencies_int) // 2],
                "p95": sorted(latencies_int)[int(len(latencies_int) * 0.95)],
            }
        else:
            metrics[op] = {"count": 0}

    return {
        "operations": metrics,
        "timestamp": time.time(),
    }


@router.get("/attention")
async def metacognitive_attention():
    """Qué tiene Denis en foco de atención ahora mismo."""
    driver = get_neo4j()

    with driver.session() as session:
        top_patterns = session.run("""
            MATCH (p:Pattern)
            RETURN p.id, p.type, p.usage_count, p.confidence
            ORDER BY p.usage_count DESC
            LIMIT 5
        """)

        patterns = [dict(record) for record in top_patterns]

        top_tools = session.run("""
            MATCH (t:Tool)
            RETURN t.name, t.success_rate, t.avg_latency_ms
            ORDER BY t.success_rate DESC
            LIMIT 5
        """)

        tools = [dict(record) for record in top_tools]

    driver.close()

    return {
        "focused_patterns": patterns,
        "active_tools": tools,
        "attention_mode": "balanced",
    }


@router.get("/coherence")
async def metacognitive_coherence():
    """Score de coherencia del sistema."""
    driver = get_neo4j()

    with driver.session() as session:
        complete_paths = session.run("""
            MATCH (pr:Principle)-[:GOVERNS]->(pa:Pattern)-[:APPLIES_TO]->(t:Tool)
            RETURN count(*) as paths
        """).single()["paths"]

        orphan_patterns = session.run("""
            MATCH (pa:Pattern)
            WHERE NOT (pa)-[:APPLIES_TO]->()
            RETURN count(pa) as orphans
        """).single()["orphans"]

        orphan_principles = session.run("""
            MATCH (pr:Principle)
            WHERE NOT (pr)-[:GOVERNS]->()
            RETURN count(pr) as orphans
        """).single()["orphans"]

    driver.close()

    coherence_score = complete_paths / max(
        1, complete_paths + orphan_patterns + orphan_principles
    )

    return {
        "coherence_score": coherence_score,
        "complete_paths": complete_paths,
        "orphan_patterns": orphan_patterns,
        "orphan_principles": orphan_principles,
        "status": "coherent" if coherence_score > 0.8 else "fragmented",
    }


@router.post("/reflect")
async def force_reflection(query: Dict):
    """Forzar reflexión metacognitiva sobre un query específico."""
    from denis_unified_v1.cortex.metacognitive_perception import PerceptionReflection
    from denis_unified_v1.metagraph.active_metagraph import L1PatternDetector

    text = query.get("text", "")

    reflection_engine = PerceptionReflection()
    perception_reflection = reflection_engine.reflect({"entities": []})

    pattern_detector = L1PatternDetector()
    patterns = pattern_detector.detect_patterns()

    return {
        "query": text,
        "perception_reflection": perception_reflection,
        "patterns_detected": len(patterns),
        "patterns": patterns[:3],
        "timestamp": time.time(),
    }


@router.post("/autopoiesis/run")
async def run_autopoiesis():
    """Ejecuta ciclo de auto-extensión."""
    from denis_unified_v1.autopoiesis.self_extension_engine import SelfExtensionEngine

    engine = SelfExtensionEngine()
    result = await engine.run_cycle()

    return result


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
