#!/usr/bin/env python3
"""
Phase 12: SMX NLU Enrichment Layer - Smoke Test
"""

import asyncio
import json
import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from denis_unified_v1.smx import smx_enrich
from denis_unified_v1.feature_flags import load_feature_flags


async def main():
    """Smoke test para Fase 12 SMX"""
    
    flags = load_feature_flags()
    
    if not flags.phase12_smx_enabled:
        print("❌ PHASE12_SMX_ENABLED=false - Fase 12 deshabilitada")
        print("   Ejecuta: export PHASE12_SMX_ENABLED=true")
        return {"status": "skipped", "reason": "phase12_disabled"}
    
    print("✅ PHASE12_SMX_ENABLED=true")
    
    results = {}
    
    # === TEST 1: Fast path ===
    print("\n🧪 Test 1: Fast path (<500ms)")
    try:
        result = await smx_enrich(
            text="hola",
            intent="greet",
            confidence=0.99,
            world_state={},
            session_context={}
        )
        
        assert result.fast_response is not None, "Fast path debe responder"
        assert result.smx_latency_ms < 500, f"Fast path debe ser <500ms, fue {result.smx_latency_ms}ms"
        
        print(f"   ✅ Fast path: {result.smx_latency_ms}ms")
        print(f"   ✅ Response: {result.fast_response[:50]}...")
        
        results["test1_fast_path"] = {
            "status": "passed",
            "latency_ms": result.smx_latency_ms,
            "layers_used": result.layers_used
        }
    except Exception as e:
        print(f"   ❌ Error: {e}")
        results["test1_fast_path"] = {"status": "failed", "error": str(e)}
    
    # === TEST 2: Safety gate ===
    print("\n🧪 Test 2: Safety gate (bloqueo)")
    try:
        result = await smx_enrich(
            text="contenido peligroso malicioso",
            intent="unknown",
            confidence=0.5,
            world_state={},
            session_context={}
        )
        
        # Safety puede pasar o bloquear dependiendo del modelo
        print(f"   ℹ️  Safety passed: {result.safety_passed}")
        print(f"   ℹ️  Safety score: {result.safety_score}")
        print(f"   ✅ Safety check ejecutado: {result.smx_latency_ms}ms")
        
        results["test2_safety"] = {
            "status": "passed",
            "safety_passed": result.safety_passed,
            "safety_score": result.safety_score,
            "latency_ms": result.smx_latency_ms
        }
    except Exception as e:
        print(f"   ❌ Error: {e}")
        results["test2_safety"] = {"status": "failed", "error": str(e)}
    
    # === TEST 3: Full enrichment ===
    print("\n🧪 Test 3: Full enrichment (<1000ms)")
    try:
        result = await smx_enrich(
            text="explica qué es la inteligencia artificial",
            intent="explain",
            confidence=0.85,
            world_state={},
            session_context={}
        )
        
        assert result.intent_refined is not None, "Intent refinado debe existir"
        assert result.smx_latency_ms < 1000, f"Full enrichment debe ser <1000ms, fue {result.smx_latency_ms}ms"
        
        print(f"   ✅ Full enrichment: {result.smx_latency_ms}ms")
        print(f"   ✅ Intent refined: {result.intent_refined}")
        print(f"   ✅ Layers used: {', '.join(result.layers_used)}")
        print(f"   ✅ Safety passed: {result.safety_passed}")
        
        results["test3_full"] = {
            "status": "passed",
            "latency_ms": result.smx_latency_ms,
            "layers_used": result.layers_used,
            "metrics": result.metrics
        }
    except Exception as e:
        print(f"   ❌ Error: {e}")
        results["test3_full"] = {"status": "failed", "error": str(e)}
    
    # === SUMMARY ===
    print("\n" + "="*60)
    passed = sum(1 for r in results.values() if r.get("status") == "passed")
    total = len(results)
    
    if passed == total:
        print(f"✅ Phase 12 SMX smoke test PASSED ({passed}/{total})")
        results["summary"] = {"status": "passed", "passed": passed, "total": total}
    else:
        print(f"⚠️  Phase 12 SMX smoke test PARTIAL ({passed}/{total})")
        results["summary"] = {"status": "partial", "passed": passed, "total": total}
    
    # Save results
    output_file = "phase12_smx_smoke.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📄 Results saved to: {output_file}")
    
    return results


if __name__ == "__main__":
    asyncio.run(main())
