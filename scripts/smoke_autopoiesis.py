#!/usr/bin/env python3
"""Smoke test: Autopoiesis."""
import asyncio, httpx, json

async def test_autopoiesis():
    async with httpx.AsyncClient(timeout=15.0) as client:
        # Ejecutar ciclo
        resp1 = await client.post("http://localhost:8085/metacognitive/autopoiesis/run")
        cycle_result = resp1.json()
        
        # Listar propuestas
        resp2 = await client.get("http://localhost:8085/metacognitive/autopoiesis/proposals")
        proposals = resp2.json()
        
        return {
            "cycle": cycle_result,
            "proposals": proposals,
            "status": "pass" if resp1.status_code == 200 and resp2.status_code == 200 else "fail",
        }

async def main():
    result = await test_autopoiesis()
    
    with open("smoke_autopoiesis.json", "w") as f:
        json.dump(result, f, indent=2)
    
    print(json.dumps(result, indent=2))
    print(f"\n{'✅' if result['status'] == 'pass' else '❌'} Autopoiesis")

if __name__ == "__main__":
    asyncio.run(main())