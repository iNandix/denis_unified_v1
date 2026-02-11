#!/usr/bin/env python3
"""Phase-7 inference router smoke (selection + fallback + metrics)."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from denis_unified_v1.inference.router import InferenceRouter


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run phase-7 inference router smoke")
    parser.add_argument(
        "--out-json",
        default="/home/jotah/denis_unified_v1/phase7_inference_smoke.json",
        help="Output json path",
    )
    return parser.parse_args()


async def run_smoke() -> dict[str, Any]:
    os.environ["DENIS_USE_INFERENCE_ROUTER"] = "true"
    router = InferenceRouter()
    status = router.get_status()

    primary = await router.route_chat(
        messages=[{"role": "user", "content": "resume el estado actual de denis en una frase"}],
        request_id=f"phase7-primary-{int(datetime.now(timezone.utc).timestamp())}",
        latency_budget_ms=2500,
    )

    # Force fallback path by preferring unreachable vLLM port first.
    old_vllm_url = os.getenv("DENIS_VLLM_URL")
    os.environ["DENIS_VLLM_URL"] = "http://127.0.0.1:1/v1/chat/completions"
    forced_router = InferenceRouter(provider_order=["vllm", "legacy_core"])
    forced = await forced_router.route_chat(
        messages=[{"role": "user", "content": "explica el fallback del router"}],
        request_id=f"phase7-fallback-{int(datetime.now(timezone.utc).timestamp())}",
        latency_budget_ms=2200,
    )
    if old_vllm_url is None:
        del os.environ["DENIS_VLLM_URL"]
    else:
        os.environ["DENIS_VLLM_URL"] = old_vllm_url

    checks = [
        {
            "check": "status_providers_loaded",
            "ok": bool(status.get("providers")),
            "providers_count": len(status.get("providers") or []),
        },
        {
            "check": "primary_response_non_empty",
            "ok": bool(primary.get("response")),
            "llm_used": primary.get("llm_used"),
            "fallback_used": primary.get("fallback_used"),
        },
        {
            "check": "fallback_path_exercised",
            "ok": bool(forced.get("fallback_used")) or forced.get("llm_used") in {"legacy_core", "local_fallback"},
            "llm_used": forced.get("llm_used"),
            "attempts": forced.get("attempts"),
            "errors_count": len(forced.get("errors") or []),
        },
    ]
    result_status = "ok" if all(item.get("ok") for item in checks) else "error"
    return {
        "status": result_status,
        "timestamp_utc": _utc_now(),
        "router_status": status,
        "primary": primary,
        "forced_fallback": forced,
        "checks": checks,
    }


def main() -> int:
    args = parse_args()
    payload = asyncio.run(run_smoke())
    out = Path(args.out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote json: {out}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
