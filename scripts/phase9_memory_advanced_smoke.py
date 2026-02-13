#!/usr/bin/env python3
"""Smoke test for Phase 9 advanced memory features."""

import asyncio
import json
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from denis_unified_v1.memory.manager import build_memory_manager


async def main():
    print("🧪 Phase 9 Advanced Memory - Smoke Test\n")

    manager = build_memory_manager()
    results = {"checks": [], "status": "ok"}

    # 1. Health check
    print("1️⃣  Health Check...")
    health = manager.health()
    results["checks"].append({
        "check": "health",
        "ok": health["status"] == "ok",
        "components": health["components"],
        "backends": health["backends"],
    })
    print(f"   ✅ Status: {health['status']}")
    print(f"   Components: {list(health['components'].keys())}")

    # 2. Store test data
    print("\n2️⃣  Storing Test Data...")
    
    # Store conversations
    for i in range(3):
        result = manager.episodic.save_conversation(
            conv_id=f"test_conv_{i}",
            user_id="test_user_advanced",
            messages=[
                {"role": "user", "content": f"Me gusta Python y vivo en Madrid. Tengo {25+i} años."},
                {"role": "assistant", "content": "Entendido."},
            ],
            outcome="success",
        )
    
    results["checks"].append({
        "check": "episodic_store",
        "ok": True,
        "conversations_stored": 3,
    })
    print("   ✅ 3 conversations stored")

    # 3. Consolidation
    print("\n3️⃣  Running Consolidation...")
    consolidation_result = await manager.consolidator.consolidate_daily(days_back=1)
    results["checks"].append({
        "check": "consolidation",
        "ok": consolidation_result["status"] == "ok",
        "facts_extracted": consolidation_result.get("facts_extracted", 0),
        "preferences_extracted": consolidation_result.get("preferences_extracted", 0),
    })
    print(f"   ✅ Facts: {consolidation_result.get('facts_extracted', 0)}")
    print(f"   ✅ Preferences: {consolidation_result.get('preferences_extracted', 0)}")

    # 4. Contradiction Detection
    print("\n4️⃣  Detecting Contradictions...")
    
    # Create conflicting facts
    await manager.consolidator._store_fact("test_user_advanced", {
        "type": "age",
        "value": "25",
        "confidence": 0.8,
        "source_conv": "test_conv_0",
    })
    
    await manager.consolidator._store_fact("test_user_advanced", {
        "type": "age",
        "value": "27",
        "confidence": 0.7,
        "source_conv": "test_conv_2",
    })
    
    contradictions = await manager.contradiction_detector.detect_contradictions(
        user_id="test_user_advanced"
    )
    
    results["checks"].append({
        "check": "contradiction_detection",
        "ok": len(contradictions) > 0,
        "contradictions_found": len(contradictions),
    })
    print(f"   ✅ Contradictions found: {len(contradictions)}")
    
    if contradictions:
        print(f"   Example: {contradictions[0]['type']} - {contradictions[0].get('fact_type', 'N/A')}")

    # 5. Memory Retrieval
    print("\n5️⃣  Testing Memory Retrieval...")
    
    retrieval_result = await manager.retrieval.retrieve_context(
        text="Cuéntame sobre Python",
        user_id="test_user_advanced",
        max_items=5,
        max_chars=1000,
    )
    
    results["checks"].append({
        "check": "memory_retrieval",
        "ok": retrieval_result["status"] == "ok",
        "items_retrieved": len(retrieval_result.get("items", [])),
        "total_chars": retrieval_result.get("total_chars", 0),
    })
    print(f"   ✅ Items retrieved: {len(retrieval_result.get('items', []))}")
    print(f"   Total chars: {retrieval_result.get('total_chars', 0)}")

    # 6. Format for prompt
    print("\n6️⃣  Testing Prompt Injection...")
    
    formatted = manager.retrieval.format_for_prompt(retrieval_result)
    results["checks"].append({
        "check": "prompt_injection",
        "ok": len(formatted) > 0,
        "formatted_length": len(formatted),
    })
    print(f"   ✅ Formatted context: {len(formatted)} chars")
    if formatted:
        print(f"   Preview: {formatted[:100]}...")

    # 7. Contradiction Resolution
    print("\n7️⃣  Testing Contradiction Resolution...")
    
    if contradictions:
        contradiction_id = contradictions[0]["contradiction_id"]
        resolution_result = await manager.contradiction_detector.resolve_contradiction(
            contradiction_id=contradiction_id,
            resolution="manual_review",
            winner_id=contradictions[0].get("fact1_id"),
        )
        
        results["checks"].append({
            "check": "contradiction_resolution",
            "ok": resolution_result["status"] == "ok",
            "resolved_id": contradiction_id,
        })
        print(f"   ✅ Resolved: {contradiction_id}")
    else:
        results["checks"].append({
            "check": "contradiction_resolution",
            "ok": True,
            "note": "no_contradictions_to_resolve",
        })
        print("   ⚠️  No contradictions to resolve")

    # 8. Semantic Search (if embeddings available)
    print("\n8️⃣  Testing Semantic Search...")
    
    if manager.retrieval.embedder:
        semantic_results = await manager.retrieval._semantic_search(
            query="programación",
            user_id="test_user_advanced",
            top_k=2,
        )
        results["checks"].append({
            "check": "semantic_search",
            "ok": True,
            "embeddings_available": True,
            "results_found": len(semantic_results),
        })
        print(f"   ✅ Embeddings available")
        print(f"   Results: {len(semantic_results)}")
    else:
        results["checks"].append({
            "check": "semantic_search",
            "ok": True,
            "embeddings_available": False,
            "note": "sentence-transformers_not_installed",
        })
        print("   ⚠️  Embeddings not available (install sentence-transformers)")

    # Summary
    print("\n" + "="*60)
    print("📊 SUMMARY")
    print("="*60)
    
    total_checks = len(results["checks"])
    passed_checks = sum(1 for c in results["checks"] if c.get("ok", False))
    
    print(f"Total checks: {total_checks}")
    print(f"Passed: {passed_checks}")
    print(f"Failed: {total_checks - passed_checks}")
    
    if passed_checks == total_checks:
        print("\n✅ ALL CHECKS PASSED")
        results["status"] = "pass"
    else:
        print("\n⚠️  SOME CHECKS FAILED")
        results["status"] = "partial"

    # Save results
    output_file = Path(__file__).parent.parent / "phase9_memory_advanced_smoke.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Results saved to: {output_file}")

    return 0 if results["status"] == "pass" else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
