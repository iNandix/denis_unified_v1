#!/usr/bin/env python3
"""Smoke test: Streaming SSE + TTFT."""
import asyncio, httpx, json, time

async def test_streaming():
    start = time.time()
    ttft = None
    chunks = 0
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream("POST", "http://localhost:8085/v1/chat/completions/stream", json={
                "messages": [{"role": "user", "content": "hola"}],
                "model": "denis",
                "max_tokens": 50
            }) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data = json.loads(line[6:])
                        if data["type"] == "ttft" and ttft is None:
                            ttft = data["latency_ms"]
                        if data["type"] == "chunk":
                            chunks += 1
    except Exception as e:
        return {
            "ttft_ms": None,
            "total_ms": int((time.time() - start) * 1000),
            "chunks": 0,
            "status": "error",
            "error": str(e),
        }
    
    total = int((time.time() - start) * 1000)
    
    return {
        "ttft_ms": ttft,
        "total_ms": total,
        "chunks": chunks,
        "status": "pass" if ttft and ttft < 1000 else "fail",
    }

async def main():
    result = await test_streaming()
    
    with open("smoke_streaming.json", "w") as f:
        json.dump(result, f, indent=2)
    
    print(json.dumps(result, indent=2))
    print(f"\n{'✅' if result['status'] == 'pass' else '❌'} TTFT: {result.get('ttft_ms', 'N/A')}ms")

if __name__ == "__main__":
    asyncio.run(main())
