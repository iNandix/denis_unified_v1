#!/usr/bin/env python3
"""Smoke test: Cognitive Router + Metacognitive Hooks funcionando."""
import asyncio, httpx, json, redis

async def test_cognitive_routing():
    """Test que Cognitive Router está activo en 8085."""
    payload = {"messages": [{"role": "user", "content": "Explica quantum"}], "model": "denis"}
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post("http://localhost:8085/v1/chat/completions", json=payload)
        data = resp.json()
    
    # Verificar que meta contiene info de routing
    routing_meta = data.get("meta", {}).get("routing", {})
    
    return {
        "cognitive_router_active": "tool_used" in routing_meta,
        "quality_score": routing_meta.get("quality_score", 0),
        "tool_used": routing_meta.get("tool_used"),
        "status": "pass" if routing_meta else "fail",
    }

async def test_metacognitive_events():
    """Test que eventos metacognitivos fluyen a Redis."""
    r = redis.Redis()
    
    # Suscribirse a eventos
    pubsub = r.pubsub()
    pubsub.subscribe("denis:metacognitive:events")
    
    # Hacer request para generar eventos
    async with httpx.AsyncClient() as client:
        await client.post("http://localhost:8085/v1/chat/completions", json={
            "messages": [{"role": "user", "content": "Test"}],
            "model": "denis",
        })
    
    # Esperar eventos
    await asyncio.sleep(1)
    messages = []
    for msg in pubsub.listen():
        if msg["type"] == "message":
            messages.append(json.loads(msg["data"]))
        if len(messages) >= 3:  # entry + exit + más
            break
    
    pubsub.close()
    
    return {
        "events_received": len(messages),
        "event_types": [m["type"] for m in messages],
        "status": "pass" if len(messages) >= 2 else "fail",
    }

async def main():
    results = {
        "cognitive_routing": await test_cognitive_routing(),
        "metacognitive_events": await test_metacognitive_events(),
    }
    
    results["summary"] = {
        "passed": all(r["status"] == "pass" for r in results.values()),
    }
    
    with open("phase4_metacognitive_smoke.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
