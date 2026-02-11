#!/usr/bin/env python3
"""Phase-6 API smoke via FastAPI TestClient."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from denis_unified_v1.api.fastapi_server import create_app


def run_smoke() -> dict[str, Any]:
    app = create_app()
    out: dict[str, Any] = {"status": "ok", "checks": []}
    with TestClient(app) as client:
        health = client.get("/health")
        out["checks"].append(
            {
                "check": "health",
                "status_code": health.status_code,
                "ok": health.status_code == 200 and health.json().get("status") == "ok",
            }
        )

        models = client.get("/v1/models")
        models_json = models.json() if models.status_code == 200 else {}
        model_count = len(models_json.get("data", [])) if isinstance(models_json, dict) else 0
        out["checks"].append(
            {
                "check": "models",
                "status_code": models.status_code,
                "ok": models.status_code == 200 and model_count >= 1,
                "model_count": model_count,
            }
        )

        chat_req = {
            "model": "denis-cognitive",
            "messages": [{"role": "user", "content": "hola denis"}],
            "stream": False,
        }
        chat = client.post("/v1/chat/completions", json=chat_req)
        chat_json = chat.json() if chat.status_code == 200 else {}
        finish_reason = None
        if isinstance(chat_json, dict):
            choices = chat_json.get("choices") or []
            if choices and isinstance(choices[0], dict):
                finish_reason = choices[0].get("finish_reason")
        out["checks"].append(
            {
                "check": "chat_completion",
                "status_code": chat.status_code,
                "ok": chat.status_code == 200 and finish_reason in {"stop", "tool_calls"},
                "finish_reason": finish_reason,
            }
        )

        chat_tools_req = {
            "model": "denis-cognitive",
            "messages": [{"role": "user", "content": "usa tool para percibir"}],
            "stream": False,
            "tools": [{"type": "function", "function": {"name": "perceive_node2"}}],
        }
        chat_tools = client.post("/v1/chat/completions", json=chat_tools_req)
        tools_json = chat_tools.json() if chat_tools.status_code == 200 else {}
        tools_finish = None
        if isinstance(tools_json, dict):
            choices = tools_json.get("choices") or []
            if choices and isinstance(choices[0], dict):
                tools_finish = choices[0].get("finish_reason")
        out["checks"].append(
            {
                "check": "chat_tools",
                "status_code": chat_tools.status_code,
                "ok": chat_tools.status_code == 200 and tools_finish == "tool_calls",
                "finish_reason": tools_finish,
            }
        )

        stream_req = {
            "model": "denis-cognitive",
            "messages": [{"role": "user", "content": "stream test"}],
            "stream": True,
        }
        with client.stream("POST", "/v1/chat/completions", json=stream_req) as response:
            lines = [line for line in response.iter_lines() if line]
            preview = lines[:6]
            has_done = any("[DONE]" in str(line) for line in lines)
        out["checks"].append(
            {
                "check": "chat_stream",
                "status_code": 200,
                "ok": len(preview) > 0 and has_done,
                "preview_lines": [str(x) for x in preview[:3]],
                "has_done": has_done,
            }
        )

        ws_route_exists = any(
            getattr(route, "path", "") == "/v1/events"
            for route in app.routes
        )
        out["checks"].append(
            {
                "check": "websocket_events_route",
                "ok": ws_route_exists,
                "route": "/v1/events",
            }
        )

    out["status"] = "ok" if all(check.get("ok") for check in out["checks"]) else "error"
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Run phase-6 API smoke")
    parser.add_argument(
        "--out-json",
        default="/home/jotah/denis_unified_v1/phase6_api_smoke.json",
        help="Output json path",
    )
    args = parser.parse_args()

    payload = run_smoke()
    out = Path(args.out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Wrote json: {out}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
