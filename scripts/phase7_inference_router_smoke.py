#!/usr/bin/env python3
"""Smoke test: Phase 7 - Inference Router."""

import asyncio
import json
import os
import sys

sys.path.insert(0, "/media/jotah/SSD_denis/home_jotah")

os.environ["DENIS_USE_INFERENCE_ROUTER"] = "true"
os.environ["PHASE7_ROUTER_SHADOW_MODE"] = "true"


async def test_inference_router():
    results = {}

    from denis_unified_v1.inference.router_v2 import create_inference_router

    router = create_inference_router()

    test_cases = [
        {
            "name": "greet_short",
            "text": "hola",
            "intent": "greet",
            "expected_engines": ["smx_fast_check", "smx_response"],
        },
        {
            "name": "code_intent",
            "text": "escribe una función en python",
            "intent": "code",
            "expected_engines": ["smx_macro", "openai_coder"],
        },
        {
            "name": "ops_intent",
            "text": "reinicia tailscale",
            "intent": "ops",
            "expected_engines": ["smx_response", "smx_macro"],
        },
    ]

    for tc in test_cases:
        request = {
            "text": tc["text"],
            "intent": tc["intent"],
            "messages": [{"role": "user", "content": tc["text"]}],
        }

        try:
            decision = await router.route(request)
            results[tc["name"]] = {
                "status": "pass",
                "engine_id": decision.get("engine_id"),
                "class_key": decision.get("class_key"),
                "reason": decision.get("reason"),
                "shadow_mode": decision.get("shadow_mode"),
            }
        except Exception as e:
            results[tc["name"]] = {
                "status": "fail",
                "error": str(e),
            }

    try:
        from denis_unified_v1.inference.engine_catalog import get_engine_catalog

        catalog = get_engine_catalog()
        engines = catalog.list_all()
        results["catalog"] = {
            "status": "pass",
            "engine_count": len(engines),
            "engines": [e.id for e in engines],
        }
    except Exception as e:
        results["catalog"] = {"status": "fail", "error": str(e)}

    return results


async def main():
    print("=== Phase 7 Inference Router Smoke Test ===\n")

    results = await test_inference_router()

    print(json.dumps(results, indent=2))

    with open("phase7_inference_router_smoke.json", "w") as f:
        json.dump(results, f, indent=2)

    all_pass = all(
        r.get("status") == "pass"
        for r in results.values()
        if isinstance(r, dict) and "status" in r
    )
    print(f"\n{'✅' if all_pass else '❌'} Phase 7 Inference Router")


if __name__ == "__main__":
    asyncio.run(main())
