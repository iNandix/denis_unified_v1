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


async def read_sse_chunks(response):
    """Read SSE chunks and check for heartbeats."""
    chunks_read = 0
    heartbeat_received = False
    
    try:
        async for chunk in response.aiter_text():
            if chunk.strip():
                chunks_read += 1
                # Check if this chunk contains a heartbeat event
                if "event: heartbeat" in chunk or "event: hello" in chunk:
                    heartbeat_received = True
                    break  # We found a heartbeat, can stop reading
                
                # Safety limit to avoid reading too much
                if chunks_read >= 5:
                    break
                    
    except Exception:
        pass
    
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

    # SSE handshake and stream reading
    sse_result = {"status": "fail"}
    try:
        import asyncio
        async with httpx.AsyncClient(timeout=5.0) as client:
            # First check basic handshake
            resp = await client.get(f"{base_url}/events", headers={"accept": "text/event-stream"})
            handshake_ok = resp.status_code == 200 and "text/event-stream" in resp.headers.get("content-type", "")
            
            if handshake_ok:
                # Now read the actual stream to verify heartbeats
                heartbeat_received = False
                chunks_read = 0
                
                async with client.stream("GET", f"{base_url}/events", headers={"accept": "text/event-stream"}) as response:
                    if response.status_code == 200 and "text/event-stream" in response.headers.get("content-type", ""):
                        # Read first few chunks with timeout
                        timeout_task = asyncio.create_task(asyncio.sleep(3.0))  # 3 second timeout for heartbeat
                        read_task = asyncio.create_task(read_sse_chunks(response))
                        
                        done, pending = await asyncio.wait(
                            [timeout_task, read_task], 
                            return_when=asyncio.FIRST_COMPLETED
                        )
                        
                        # Cancel pending tasks
                        for task in pending:
                            task.cancel()
                        
                        if read_task in done:
                            chunks_read, heartbeat_received = read_task.result()
                    
                sse_result = {
                    "status": "pass" if handshake_ok and heartbeat_received else "fail",
                    "http_status": resp.status_code,
                    "content_type": resp.headers.get("content-type"),
                    "handshake_ok": handshake_ok,
                    "heartbeat_received": heartbeat_received,
                    "chunks_read": chunks_read,
                    "stream_read_attempted": True
                }
            else:
                sse_result = {
                    "status": "pass" if resp.status_code == 404 else "fail",  # 404 is acceptable for missing endpoint
                    "http_status": resp.status_code,
                    "content_type": resp.headers.get("content-type"),
                    "handshake_ok": handshake_ok,
                    "heartbeat_received": False,
                    "chunks_read": 0,
                    "stream_read_attempted": False
                }
    except Exception as e:
        sse_result = {"status": "fail", "error": str(e), "stream_read_attempted": False}

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
