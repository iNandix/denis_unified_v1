#!/usr/bin/env python3
"""Smoke test: API Metacognitiva."""
import asyncio, httpx, json

async def test_endpoints():
    endpoints = ["/status", "/metrics", "/attention", "/coherence"]
    results = {}
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for endpoint in endpoints:
            try:
                resp = await client.get(f"http://localhost:8085/metacognitive{endpoint}")
                data = resp.json()
                results[endpoint] = {
                    "status": "pass" if resp.status_code == 200 else "fail",
                    "data_keys": list(data.keys()),
                }
            except Exception as e:
                results[endpoint] = {"status": "fail", "error": str(e)}
    
    return results

async def main():
    results = await test_endpoints()
    
    with open("smoke_metacognitive_api.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(json.dumps(results, indent=2))
    all_pass = all(r["status"] == "pass" for r in results.values())
    print(f"\n{'✅' if all_pass else '❌'} API Metacognitiva")

if __name__ == "__main__":
    asyncio.run(main())
