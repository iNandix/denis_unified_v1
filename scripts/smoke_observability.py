#!/usr/bin/env python3
"""Smoke test: Observabilidad."""
import asyncio, httpx, json

async def test_observability():
    results = {}
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Prometheus metrics
        try:
            resp = await client.get("http://localhost:8085/metrics")
            results["prometheus"] = {
                "status": "pass" if resp.status_code == 200 else "fail",
                "metrics_count": len(resp.text.split('\n')),
            }
        except Exception as e:
            results["prometheus"] = {"status": "fail", "error": str(e)}
        
        # Alerting
        try:
            resp = await client.get("http://localhost:8085/metacognitive/alerts")
            data = resp.json()
            results["alerting"] = {
                "status": "pass" if resp.status_code == 200 else "fail",
                "anomalies": data.get("anomalies", 0),
            }
        except Exception as e:
            results["alerting"] = {"status": "fail", "error": str(e)}
        
        # Jaeger (check if running)
        try:
            resp = await client.get("http://localhost:16686/")
            results["jaeger"] = {"status": "pass" if resp.status_code == 200 else "fail"}
        except:
            results["jaeger"] = {"status": "fail", "message": "Jaeger not running"}
    
    return results

async def main():
    results = await test_observability()
    
    with open("smoke_observability.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(json.dumps(results, indent=2))
    all_pass = all(r.get("status") == "pass" for r in results.values())
    print(f"\n{'✅' if all_pass else '❌'} Observability")

if __name__ == "__main__":
    asyncio.run(main())
