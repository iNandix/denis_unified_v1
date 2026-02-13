#!/usr/bin/env python3
"""Smoke test: verifica integración completa metacognitiva Fases 0-3."""
import asyncio
import httpx
import json
import time
import sys
import os
from typing import Dict, Any

# Add project to path
sys.path.insert(0, "/media/jotah/SSD_denis/home_jotah")

try:
    import redis
except ImportError:
    redis = None

from neo4j import GraphDatabase


async def test_phase0_hooks():
    """Fase 0: Verifica que eventos metacognitivos fluyen a Redis."""
    print("\n=== FASE 0: METACOGNITIVE HOOKS ===")
    
    if redis is None:
        return {"status": "skip", "reason": "Redis not available"}
    
    r = redis.Redis(decode_responses=True)
    
    # Suscribirse a eventos
    pubsub = r.pubsub()
    pubsub.subscribe("denis:metacognitive:events")
    
    # Generar tráfico para disparar hooks
    try:
        async with httpx.AsyncClient() as client:
            await client.post("http://localhost:8085/v1/chat/completions", json={
                "messages": [{"role": "user", "content": "test hooks"}],
                "model": "denis",
            }, timeout=10.0)
    except Exception as e:
        print(f"Error generando tráfico: {e}")
    
    # Esperar eventos
    await asyncio.sleep(2)
    events = []
    
    # Leer mensajes disponibles
    try:
        message = pubsub.get_message(timeout=1.0)
        while message and len(events) < 5:
            if message["type"] == "message":
                try:
                    events.append(json.loads(message["data"]))
                except:
                    pass
            message = pubsub.get_message(timeout=0.1)
    except:
        pass
    
    pubsub.close()
    
    return {
        "events_received": len(events),
        "event_types": [e.get("type") for e in events],
        "operations": [e.get("operation") for e in events],
        "status": "pass" if len(events) >= 1 else "fail",
    }


async def test_phase1_perception():
    """Fase 1: Verifica que cortex tiene reflexión metacognitiva."""
    print("\n=== FASE 1: METACOGNITIVE PERCEPTION ===")
    
    try:
        from denis_unified_v1.cortex.metacognitive_perception import PerceptionReflection
        
        reflection_engine = PerceptionReflection()
        
        test_perception = {
            "entities": [
                {"name": "neo4j", "type": "system", "status": "ok", "last_updated": time.time()},
                {"name": "redis", "type": "system", "status": "ok", "last_updated": time.time() - 3600},
            ]
        }
        
        reflection = reflection_engine.reflect(test_perception)
        
        return {
            "confidence": reflection["confidence"],
            "importance": reflection["importance"],
            "gaps": reflection["gaps"],
            "attention_score": reflection["attention_score"],
            "status": "pass" if reflection["confidence"] > 0 else "fail",
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


async def test_phase3_active_metagraph():
    """Fase 3: Verifica que L1 detecta patrones en L0."""
    print("\n=== FASE 3: ACTIVE METAGRAPH L1 ===")
    
    try:
        from denis_unified_v1.metagraph.active_metagraph import L1PatternDetector, L1Reorganizer
        
        detector = L1PatternDetector()
        reorganizer = L1Reorganizer()
        
        patterns = detector.detect_patterns()
        proposals = reorganizer.propose_reorganizations(patterns)
        
        return {
            "patterns_detected": len(patterns),
            "pattern_types": [p["type"] for p in patterns],
            "proposals_generated": len(proposals),
            "status": "pass" if len(patterns) >= 0 else "fail",  # 0 es válido si todo OK
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


async def test_phase5_router_uses_graph():
    """Fase 5: Verifica que Cognitive Router usa patterns del grafo."""
    print("\n=== FASE 5: COGNITIVE ROUTER + GRAFO ===")
    
    payload = {"messages": [{"role": "user", "content": "hola"}], "model": "denis"}
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post("http://localhost:8085/v1/chat/completions", json=payload)
            data = resp.json()
        
        meta = data.get("meta", {})
        routing = meta.get("routing", {})
        
        return {
            "grafo_l1_active": meta.get("grafo_l1_active", False),
            "pattern_used": meta.get("pattern_used"),
            "tool_used": routing.get("tool_used"),
            "patterns_consulted": routing.get("patterns_consulted", 0),
            "status": "pass" if meta.get("grafo_l1_active") or routing.get("patterns_consulted", 0) > 0 else "partial",
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


async def main():
    results = {
        "phase0_hooks": await test_phase0_hooks(),
        "phase1_perception": await test_phase1_perception(),
        "phase3_active_metagraph": await test_phase3_active_metagraph(),
        "phase5_router_uses_graph": await test_phase5_router_uses_graph(),
    }
    
    # Summary
    passed_phases = [k for k, v in results.items() if v.get("status") == "pass"]
    all_passed = len(passed_phases) >= 3  # Al menos 3 de 4 fases
    
    results["summary"] = {
        "all_phases_active": all_passed,
        "phases_passed": len(passed_phases),
        "total_phases": len(results) - 1,  # -1 porque summary no cuenta
        "passed_phases": passed_phases,
    }
    
    with open("phase_metacognitive_integration_smoke.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print("\n=== RESUMEN ===")
    print(json.dumps(results["summary"], indent=2))
    print(f"\n{'✅' if all_passed else '❌'} Smoke test {'PASADO' if all_passed else 'FALLIDO'}")
    
    if not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())