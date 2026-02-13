#!/usr/bin/env python3
"""Smoke test: Streaming SSE + TTFT + paralelización."""
import asyncio, httpx, json, time

async def test_streaming():
    """Test endpoint streaming SSE."""
    results = {"streaming": {}, "performance": {}}

    payload = {"messages": [{"role": "user", "content": "Hola"}], "model": "denis", "max_tokens": 50}

    start = time.time()
    ttft = None
    chunks_received = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        async with client.stream("POST", "http://localhost:8085/v1/chat/completions/stream", json=payload) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    if data["type"] == "ttft" and ttft is None:
                        ttft = time.time() - start
                    if data["type"] == "chunk":
                        chunks_received += 1
                    if data["type"] == "final":
                        total = time.time() - start
                        results["streaming"] = {
                            "ttft_ms": int(ttft * 1000) if ttft else 0,
                            "total_ms": int(total * 1000),
                            "chunks": chunks_received,
                            "status": "pass" if ttft and ttft < 1.0 else "fail",
                        }

    return results

async def test_fast_path():
    """Test fast path optimization."""
    payload = {"messages": [{"role": "user", "content": "Hola"}], "model": "denis", "max_tokens": 20}

    start = time.time()
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post("http://localhost:8085/v1/chat/completions", json=payload)
        data = resp.json()

    latency = time.time() - start

    return {
        "latency_ms": int(latency * 1000),
        "model_used": data.get("model"),
        "used_fast_path": "fast" in data.get("model", ""),
        "status": "pass" if latency < 1.5 else "partial",
    }

async def main():
    results = {}

    # Test 1: Streaming
    results["streaming_test"] = await test_streaming()

    # Test 2: Fast path
    results["fast_path_test"] = await test_fast_path()

    # Summary
    results["summary"] = {
        "ttft_target": "< 1000ms",
        "ttft_actual": results["streaming_test"]["streaming"].get("ttft_ms", 0),
        "fast_path_latency": results["fast_path_test"]["latency_ms"],
        "passed": results["streaming_test"]["streaming"]["status"] == "pass",
    }

    with open("phase3_streaming_performance_smoke.json", "w") as f:
        json.dump(results, f, indent=2)

    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
