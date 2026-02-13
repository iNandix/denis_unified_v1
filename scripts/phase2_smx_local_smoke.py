#!/usr/bin/env python3
"""Smoke test: Unified V1 8085 usando SMX local (no Groq)."""
import asyncio, httpx, json, os

async def main():
    # 1) Health check de 6 motores SMX
    motors = [
        ("nodo2", 8003), ("nodo2", 8006), ("nodo2", 8007), ("nodo2", 8008),
        ("localhost", 9997), ("localhost", 9998),
    ]

    results = {"motors_health": {}}
    async with httpx.AsyncClient(timeout=5.0) as client:
        for node, port in motors:
            host = "http://10.10.10.2" if node == "nodo2" else "http://localhost"
            try:
                resp = await client.get(f"{host}:{port}/health")
                results["motors_health"][f"{node}:{port}"] = resp.status_code == 200
            except:
                results["motors_health"][f"{node}:{port}"] = False

    # 2) Test chat con SMX local
    payload = {
        "messages": [{"role": "user", "content": "Hola"}],
        "model": "denis",
        "max_tokens": 30,
    }

    # Set environment variable for SMX local
    os.environ["USE_SMX_LOCAL"] = "true"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post("http://localhost:8085/v1/chat/completions", json=payload)
            if resp.status_code == 200:
                chat_data = resp.json()
                results["chat_test"] = {
                    "status": "pass" if "smx_local_unified" in chat_data.get("model", "") else "fail",
                    "model_used": chat_data.get("model"),
                    "response_length": len(chat_data.get("choices", [{}])[0].get("message", {}).get("content", "")),
                    "latency_ms": chat_data.get("usage", {}).get("total_tokens", 0) * 50,  # Estimate
                }
            else:
                results["chat_test"] = {
                    "status": "fail",
                    "error": f"HTTP {resp.status_code}",
                    "response": await resp.text(),
                }
        except Exception as e:
            results["chat_test"] = {
                "status": "fail",
                "error": str(e),
            }

    # Guardar resultados
    with open("phase2_smx_local_smoke.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
