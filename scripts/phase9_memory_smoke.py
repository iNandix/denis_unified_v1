#!/usr/bin/env python3
"""Phase-9 unified memory smoke."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any
import uuid

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from denis_unified_v1.api.fastapi_server import create_app


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run phase-9 memory smoke")
    parser.add_argument(
        "--out-json",
        default="/home/jotah/denis_unified_v1/phase9_memory_smoke.json",
        help="Output json path",
    )
    return parser.parse_args()


def run_smoke() -> dict[str, Any]:
    os.environ["DENIS_USE_MEMORY_UNIFIED"] = "true"
    os.environ["DENIS_USE_ATLAS"] = "true"
    app = create_app()
    out: dict[str, Any] = {"status": "ok", "timestamp_utc": _utc_now(), "checks": [], "graph_loading_errors": []}

    conv_id = f"phase9-{uuid.uuid4().hex[:10]}"

    with TestClient(app) as client:
        health = client.get("/v1/memory/health")
        health_json = health.json() if health.status_code == 200 else {}
        out["checks"].append(
            {
                "check": "memory_health",
                "ok": health.status_code == 200 and health_json.get("status") == "ok",
                "status_code": health.status_code,
                "legacy_bridge": health_json.get("legacy_bridge"),
            }
        )

        episodic_req = {
            "conv_id": conv_id,
            "user_id": "jotah",
            "messages": [{"role": "user", "content": "test memoria fase9"}],
            "outcome": "ok",
        }
        episodic_post = client.post("/v1/memory/episodic", json=episodic_req)
        episodic_post_json = episodic_post.json() if episodic_post.status_code == 200 else {}
        out["checks"].append(
            {
                "check": "episodic_store",
                "ok": episodic_post.status_code == 200 and episodic_post_json.get("status") == "ok",
                "status_code": episodic_post.status_code,
                "legacy_mirror": (episodic_post_json.get("legacy_mirror") or {}).get("status"),
            }
        )

        episodic_get = client.get(f"/v1/memory/episodic/{conv_id}")
        out["checks"].append(
            {
                "check": "episodic_fetch",
                "ok": episodic_get.status_code == 200 and episodic_get.json().get("conv_id") == conv_id,
                "status_code": episodic_get.status_code,
            }
        )

        neuro_layers = client.get("/v1/memory/neuro/layers")
        neuro_json = neuro_layers.json() if neuro_layers.status_code == 200 else {}
        out["checks"].append(
            {
                "check": "neuro_layers_bridge",
                "ok": neuro_layers.status_code == 200 and int(neuro_json.get("total_layers", 0)) >= 12,
                "status_code": neuro_layers.status_code,
                "total_layers": neuro_json.get("total_layers"),
            }
        )

        mental = client.get("/v1/memory/mental-loop/levels")
        mental_json = mental.json() if mental.status_code == 200 else {}
        out["checks"].append(
            {
                "check": "mental_loop_levels",
                "ok": mental.status_code == 200 and len(mental_json.get("levels", [])) == 4,
                "status_code": mental.status_code,
            }
        )

        cot = client.post(
            "/v1/memory/cot/adaptive",
            json={
                "query": "compara estrategias de persistencia de memoria en denis",
                "latency_budget_ms": 1800,
                "context_window_tokens": 12000,
            },
        )
        cot_json = cot.json() if cot.status_code == 200 else {}
        out["checks"].append(
            {
                "check": "adaptive_cot",
                "ok": cot.status_code == 200 and cot_json.get("mode") == "adaptive_cot",
                "status_code": cot.status_code,
                "depth": cot_json.get("depth"),
            }
        )

        atlas = client.get("/v1/memory/atlas/projects")
        out["checks"].append(
            {
                "check": "atlas_bridge",
                "ok": atlas.status_code == 200,
                "status_code": atlas.status_code,
            }
        )

        out["sample"] = {
            "health": health_json,
            "episodic_store": episodic_post_json,
            "neuro_layers": neuro_json,
            "adaptive_cot": cot_json,
            "atlas_projects": atlas.json() if atlas.status_code == 200 else {},
        }

    # Check for artifacts directory and graph client issues
    artifacts_dir = Path(PROJECT_ROOT) / "artifacts"
    if not artifacts_dir.exists():
        out["checks"].append({
            "check": "artifacts_directory",
            "ok": False,
            "status": "skipped",
            "reason": "Artifacts directory not found",
        })
    else:
        out["checks"].append({
            "check": "artifacts_directory",
            "ok": True,
            "status": "available",
        })

    # Try to import graph client and check for issues
    try:
        from denis_unified_v1.metagraph.active_metagraph import get_metagraph_client
        client = get_metagraph_client()
        if client is None:
            out["graph_loading_errors"].append("get_metagraph_client returned None")
        else:
            out["checks"].append({
                "check": "graph_client",
                "ok": True,
                "status": "available",
            })
    except Exception as e:
        out["graph_loading_errors"].append(f"Graph client import failed: {str(e)}")
        out["checks"].append({
            "check": "graph_client",
            "ok": False,
            "status": "skipped",
            "reason": f"Graph client unavailable: {str(e)}",
        })

    out["status"] = "ok" if all(check.get("ok") for check in out["checks"]) else "skipped_dependency" if any("skipped" in str(check.get("status", "")) for check in out["checks"]) else "error"
    return out


def main() -> int:
    args = parse_args()
    payload = run_smoke()
    out = Path(args.out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote json: {out}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
