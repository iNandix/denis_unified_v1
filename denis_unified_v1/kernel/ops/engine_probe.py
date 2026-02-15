#!/usr/bin/env python3
"""Engine probe - diagnostic tool to check engine health.

Usage:
    python -m denis_unified_v1.kernel.ops.engine_probe --mode ping --timeout-ms 800
    python -m denis_unified_v1.kernel.ops.engine_probe --mode infer --timeout-ms 2000
    python -m denis_unified_v1.kernel.ops.engine_probe --allow-boosters
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime

from denis_unified_v1.kernel.engine_registry import get_engine_registry
from denis_unified_v1.kernel.internet_health import get_internet_health


async def probe_engine(
    engine_id: str,
    endpoint: str,
    provider_key: str,
    mode: str,
    timeout_ms: int,
    allow_boosters: bool,
    internet_ok: bool,
) -> dict:
    """Probe a single engine."""
    start = time.perf_counter()
    result = {
        "engine_id": engine_id,
        "endpoint": endpoint,
        "provider_key": provider_key,
        "mode": mode,
        "ok": False,
        "latency_ms": 0,
        "error": None,
    }

    # Check if should skip booster
    if "internet_required" in get_engine_registry().get(engine_id, {}).get("tags", []):
        if not allow_boosters:
            result["skipped"] = True
            result["reason"] = "booster_disabled"
            result["ok"] = True
            return result
        if not internet_ok:
            result["skipped"] = True
            result["reason"] = "internet_down"
            result["ok"] = True
            return result

    try:
        if provider_key == "llamacpp":
            result.update(await probe_llamacpp(endpoint, mode, timeout_ms))
        elif provider_key == "groq":
            if not internet_ok:
                result["skipped"] = True
                result["reason"] = "internet_down"
                result["ok"] = True
                return result
            result.update(await probe_groq(endpoint, mode, timeout_ms))
        else:
            result["error"] = f"Unknown provider: {provider_key}"
    except Exception as e:
        result["error"] = str(e)[:200]

    result["latency_ms"] = int((time.perf_counter() - start) * 1000)
    return result


async def probe_llamacpp(endpoint: str, mode: str, timeout_ms: int) -> dict:
    """Probe llama.cpp server."""
    import aiohttp

    url = endpoint.rstrip("/")
    if not url.endswith("/v1/chat/completions"):
        url = f"{url}/v1/chat/completions"

    timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000)

    if mode == "ping":
        # Just check if endpoint responds
        payload = {
            "model": "local",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
        }
    else:
        # Inference mode
        payload = {
            "model": "local",
            "messages": [{"role": "user", "content": "What is 1+1?"}],
            "max_tokens": 5,
        }

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload) as resp:
            if resp.status >= 400:
                return {"ok": False, "error": f"HTTP {resp.status}"}
            data = await resp.json()
            if "choices" in data and data["choices"]:
                return {"ok": True}
            return {"ok": False, "error": "No choices in response"}


async def probe_groq(endpoint: str, mode: str, timeout_ms: int) -> dict:
    """Probe Groq endpoint (requires internet)."""
    import aiohttp

    # Groq needs API key - just check connectivity
    url = endpoint.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = f"{url}/chat/completions"

    timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000)
    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1,
    }

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload) as resp:
            if resp.status >= 400:
                return {"ok": False, "error": f"HTTP {resp.status}"}
            return {"ok": True}


async def main():
    parser = argparse.ArgumentParser(description="Engine probe")
    parser.add_argument("--mode", choices=["ping", "infer"], default="ping")
    parser.add_argument("--timeout-ms", type=int, default=800)
    parser.add_argument("--allow-boosters", action="store_true")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    registry = get_engine_registry()
    internet = get_internet_health()
    internet_ok = internet.is_internet_ok()

    print(f"=== Engine Probe ({args.mode}) ===")
    print(f"Internet: {internet_ok} | Allow boosters: {args.allow_boosters}")
    print(f"Timeout: {args.timeout_ms}ms")
    print()

    results = []
    for engine_id, info in sorted(
        registry.items(), key=lambda x: x[1].get("priority", 99)
    ):
        result = await probe_engine(
            engine_id=engine_id,
            endpoint=info.get("endpoint", ""),
            provider_key=info.get("provider_key", ""),
            mode=args.mode,
            timeout_ms=args.timeout_ms,
            allow_boosters=args.allow_boosters,
            internet_ok=internet_ok,
        )
        results.append(result)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        # Table output
        print(
            f"{'Engine ID':<22} {'Endpoint':<28} {'Provider':<10} {'Latency':<10} {'Status':<12}"
        )
        print("-" * 85)

        ok_count = 0
        for r in results:
            status = "OK" if r.get("ok") else "ERROR"
            if r.get("skipped"):
                status = f"SKIP ({r.get('reason')})"
            latency = f"{r.get('latency_ms', 0)}ms"

            endpoint = r.get("endpoint", "")[:26]
            if len(r.get("endpoint", "")) > 26:
                endpoint = endpoint[:23] + "..."

            print(
                f"{r['engine_id']:<22} {endpoint:<28} {r['provider_key']:<10} {latency:<10} {status:<12}"
            )

            if r.get("ok"):
                ok_count += 1
            elif r.get("error"):
                print(f"  Error: {r['error']}")

        print()
        print(
            f"Total: {len(results)} | OK: {ok_count} | Failed: {len(results) - ok_count}"
        )

    return 0 if ok_count > 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
