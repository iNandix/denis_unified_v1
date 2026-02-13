#!/usr/bin/env python3
"""Compara métricas 8084 vs 8085."""
import asyncio
import httpx
import statistics
import time

async def benchmark(port: int, queries: list) -> dict:
    """Ejecuta queries y mide métricas."""
    latencies = []
    errors = 0
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for query in queries:
            try:
                start = time.time()
                resp = await client.post(f"http://localhost:{port}/v1/chat/completions", json={
                    "messages": [{"role": "user", "content": query}],
                    "model": "denis",
                    "max_tokens": 50
                })
                latency = time.time() - start
                
                if resp.status_code == 200:
                    latencies.append(latency * 1000)
                else:
                    errors += 1
            except:
                errors += 1
    
    return {
        "port": port,
        "requests": len(queries),
        "errors": errors,
        "success_rate": (len(queries) - errors) / len(queries),
        "avg_latency_ms": statistics.mean(latencies) if latencies else 0,
        "p50_latency_ms": statistics.median(latencies) if latencies else 0,
        "p95_latency_ms": sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0,
    }

async def main():
    queries = ["hola", "qué hora es", "cuéntame un chiste", "explica Python"]
    
    results_8084 = await benchmark(8084, queries)
    results_8085 = await benchmark(8085, queries)
    
    print("=== COMPARACIÓN 8084 vs 8085 ===\n")
    print(f"8084: {results_8084['avg_latency_ms']:.0f}ms avg, {results_8084['success_rate']:.2%} success")
    print(f"8085: {results_8085['avg_latency_ms']:.0f}ms avg, {results_8085['success_rate']:.2%} success")
    
    improvement = ((results_8084['avg_latency_ms'] - results_8085['avg_latency_ms']) / results_8084['avg_latency_ms']) * 100
    print(f"\n{'✅' if improvement > 0 else '❌'} Mejora latencia: {improvement:+.1f}%")

if __name__ == "__main__":
    asyncio.run(main())
