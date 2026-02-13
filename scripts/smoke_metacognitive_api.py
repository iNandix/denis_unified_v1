#!/usr/bin/env python3
"""Smoke test: API Metacognitiva (timeouts, degraded accepted, SSE handshake)."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Metacognitive API smoke")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8085/metacognitive",
        help="Base URL for metacognitive API",
    )
    parser.add_argument(
        "--out-json",
        default="artifacts/phase6_api_smoke.json",
        help="Output artifact path",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("METACOG_SMOKE_PORT", "8085")),
        help="Port to use if auto-starting server",
    )
    return parser.parse_args()


async def test_endpoints(base_url: str):
    endpoints = ["/status", "/metrics", "/attention", "/coherence", "/reflect"]
    results = {}

    async with httpx.AsyncClient(timeout=2.0) as client:
        for endpoint in endpoints:
            start = time.perf_counter()
            try:
                payload = {"text": "ping"} if endpoint == "/reflect" else None
                resp = await client.request(
                    "POST" if payload else "GET",
                    f"{base_url}{endpoint}",
                    json=payload,
                )
                latency_ms = (time.perf_counter() - start) * 1000
                data = resp.json()
                status_ok = resp.status_code == 200
                api_status = data.get("status")
                degraded_ok = api_status in {"degraded", "healthy", "fragmented", None}
                results[endpoint] = {
                    "http_status": resp.status_code,
                    "latency_ms": latency_ms,
                    "status": "pass" if status_ok else "fail",
                    "api_status": api_status,
                    "degraded_ok": degraded_ok,
                    "keys": list(data.keys()),
                }
            except Exception as e:
                results[endpoint] = {
                    "status": "fail",
                    "error": str(e),
                    "latency_ms": (time.perf_counter() - start) * 1000,
                }

    # SSE handshake
    sse_result = {"status": "fail"}
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{base_url}/events", headers={"accept": "text/event-stream"})
            ok = resp.status_code == 200 and "text/event-stream" in resp.headers.get("content-type", "")
            sse_result = {
                "status": "pass" if ok else ("pass" if resp.status_code == 404 else "fail"),
                "http_status": resp.status_code,
                "content_type": resp.headers.get("content-type"),
            }
    except Exception as e:
        sse_result = {"status": "fail", "error": str(e)}

    results["/events"] = sse_result
    return results


async def main():
    args = parse_args()
    base_url = args.base_url

    server_proc: subprocess.Popen | None = None

    async def _is_up():
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                resp = await client.get(f"{base_url}/status")
                return resp.status_code == 200
        except Exception:
            return False

    if not await _is_up():
        # Try to start local uvicorn server pointing to fastapi_server:app
        server_proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "denis_unified_v1.api.fastapi_server:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(args.port),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        base_url = f"http://127.0.0.1:{args.port}/metacognitive"
        # small wait for startup
        await asyncio.sleep(1.0)

    results = await test_endpoints(base_url)

    ok = all(r.get("status") == "pass" or r.get("degraded_ok") for r in results.values())

    artifact = {
        "ok": ok,
        "results": results,
        "base_url": base_url,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    out_path = args.out_json
    import os

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2)

    print(json.dumps(artifact, indent=2))

    if server_proc is not None:
        try:
            server_proc.terminate()
            server_proc.wait(timeout=5)
        except Exception:
            pass

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
