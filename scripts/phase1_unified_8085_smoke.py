#!/usr/bin/env python3
"""Smoke test for Unified V1 FastAPI server on port 8085."""

import asyncio
import json
import time
from typing import Any, Dict

import aiohttp


async def test_health_endpoint(base_url: str) -> Dict[str, Any]:
    """Test the /health endpoint."""
    try:
        async with aiohttp.ClientSession() as session:
            start_time = time.time()
            async with session.get(f"{base_url}/health") as response:
                latency_ms = int((time.time() - start_time) * 1000)
                if response.status == 200:
                    data = await response.json()
                    return {
                        "test": "health",
                        "status": "pass",
                        "status_code": response.status,
                        "latency_ms": latency_ms,
                        "data": data,
                        "checks": {
                            "status_ok": data.get("status") == "ok",
                            "version_unified_v1": data.get("version") == "unified-v1",
                            "has_components": "components" in data,
                            "has_timestamp": "timestamp_utc" in data,
                        }
                    }
                else:
                    return {
                        "test": "health",
                        "status": "fail",
                        "status_code": response.status,
                        "latency_ms": latency_ms,
                        "error": f"HTTP {response.status}",
                    }
    except Exception as e:
        return {
            "test": "health",
            "status": "fail",
            "error": str(e),
        }


async def test_chat_completions_endpoint(base_url: str) -> Dict[str, Any]:
    """Test the /v1/chat/completions endpoint with a simple message."""
    try:
        payload = {
            "messages": [{"role": "user", "content": "Hola"}],
            "model": "denis-unified-v1",
            "max_tokens": 50
        }

        async with aiohttp.ClientSession() as session:
            start_time = time.time()
            async with session.post(
                f"{base_url}/v1/chat/completions",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                latency_ms = int((time.time() - start_time) * 1000)
                if response.status == 200:
                    data = await response.json()
                    content = ""
                    if "choices" in data and data["choices"]:
                        choice = data["choices"][0]
                        if "message" in choice and "content" in choice["message"]:
                            content = choice["message"]["content"]

                    return {
                        "test": "chat_completions",
                        "status": "pass" if content.strip() else "fail",
                        "status_code": response.status,
                        "latency_ms": latency_ms,
                        "data": data,
                        "checks": {
                            "has_id": "id" in data,
                            "has_choices": "choices" in data and len(data["choices"]) > 0,
                            "has_content": bool(content.strip()),
                            "has_model": "model" in data,
                            "has_usage": "usage" in data,
                            "latency_under_10s": latency_ms < 10000,
                        }
                    }
                else:
                    error_text = await response.text()
                    return {
                        "test": "chat_completions",
                        "status": "fail",
                        "status_code": response.status,
                        "latency_ms": latency_ms,
                        "error": error_text,
                    }
    except Exception as e:
        return {
            "test": "chat_completions",
            "status": "fail",
            "error": str(e),
        }


async def main():
    """Run smoke tests against Unified V1 server on port 8085."""
    base_url = "http://localhost:8085"

    print("🚀 Running Phase 1 Unified V1 8085 Smoke Tests")
    print(f"Target: {base_url}")
    print("-" * 50)

    # Run tests
    health_result = await test_health_endpoint(base_url)
    chat_result = await test_chat_completions_endpoint(base_url)

    # Compile results
    results = {
        "timestamp": time.time(),
        "target_url": base_url,
        "tests": [health_result, chat_result],
        "summary": {
            "total_tests": 2,
            "passed": sum(1 for r in [health_result, chat_result] if r.get("status") == "pass"),
            "failed": sum(1 for r in [health_result, chat_result] if r.get("status") == "fail"),
        }
    }

    # Print results
    print(f"Health endpoint: {health_result['status'].upper()}")
    if health_result["status"] == "pass":
        print(f"  ✓ Status: {health_result['data'].get('status')}")
        print(f"  ✓ Version: {health_result['data'].get('version')}")
        print(f"  ✓ Latency: {health_result['latency_ms']}ms")
    else:
        print(f"  ✗ Error: {health_result.get('error', 'Unknown')}")

    print(f"\nChat completions: {chat_result['status'].upper()}")
    if chat_result["status"] == "pass":
        content = ""
        if "data" in chat_result and "choices" in chat_result["data"] and chat_result["data"]["choices"]:
            choice = chat_result["data"]["choices"][0]
            if "message" in choice and "content" in choice["message"]:
                content = choice["message"]["content"][:100] + "..." if len(choice["message"]["content"]) > 100 else choice["message"]["content"]
        print(f"  ✓ Model: {chat_result['data'].get('model', 'unknown')}")
        print(f"  ✓ Content: {content}")
        print(f"  ✓ Latency: {chat_result['latency_ms']}ms")
    else:
        print(f"  ✗ Error: {chat_result.get('error', 'Unknown')}")

    print(f"\nSummary: {results['summary']['passed']}/{results['summary']['total_tests']} tests passed")

    # Save results
    with open("phase1_unified_8085_smoke.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to: phase1_unified_8085_smoke.json")
    # Exit with appropriate code
    exit(0 if results["summary"]["passed"] == results["summary"]["total_tests"] else 1)


if __name__ == "__main__":
    asyncio.run(main())
