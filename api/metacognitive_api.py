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
        
        governs_count = session.run("MATCH ()-[r:GOVERNS]->() RETURN count(r) as c").single()["c"]
        applies_count = session.run("MATCH ()-[r:APPLIES_TO]->() RETURN count(r) as c").single()["c"]
        
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
        return {"operations": {}, "timestamp": time.time(), "error": "Redis not available"}
    
    operations = ["smx_motor_call", "cognitive_router_route", "nlu_parse", "smx_orchestrator_process"]
    metrics = {}
    
    for op in operations:
        key = f"metrics:{op}:latency"
        latencies = r.lrange(key, 0, 99)
        
        if latencies:
            latencies_int = [int(x) for x in latencies]
            metrics[op] = {
                "count": len(latencies_int),
                "avg_latency_ms": sum(latencies_int) // len(latencies_int),
                "p50": sorted(latencies_int)[len(latencies_int)//2],
                "p95": sorted(latencies_int)[int(len(latencies_int)*0.95)],
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
    
    coherence_score = complete_paths / max(1, complete_paths + orphan_patterns + orphan_principles)
    
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
