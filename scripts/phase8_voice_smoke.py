#!/usr/bin/env python3
"""Phase-8 voice pipeline smoke using unified API TestClient."""

from __future__ import annotations

import argparse
import asyncio
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from denis_unified_v1.api.fastapi_server import create_app


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run phase-8 voice smoke")
    parser.add_argument(
        "--out-json",
        default="/home/jotah/denis_unified_v1/phase8_voice_smoke.json",
        help="Output json path",
    )
    return parser.parse_args()


def _silent_wav_base64() -> str:
    # Minimal wav-like placeholder bytes for smoke path.
    payload = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x10\x00\x00\x00\x01\x00\x01\x00" + b"\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    return base64.b64encode(payload).decode("ascii")


async def run_smoke() -> dict[str, Any]:
    os.environ["DENIS_USE_VOICE_PIPELINE"] = "true"
    os.environ.setdefault("DENIS_VOICE_CHAT_URL", "http://127.0.0.1:8084/v1/chat")
    app = create_app()
    payload: dict[str, Any] = {"status": "ok", "timestamp_utc": _utc_now(), "checks": []}
    audio_b64 = _silent_wav_base64()

    with TestClient(app) as client:
        health = client.get("/v1/voice/health")
        payload["checks"].append(
            {
                "check": "voice_health",
                "status_code": health.status_code,
                "ok": health.status_code == 200 and health.json().get("status") == "ok",
            }
        )

        req = {
            "audio_base64": audio_b64,
            "language": "es",
            "model": "denis-cognitive",
        }
        process = client.post("/v1/voice/process", json=req)
        process_json = process.json() if process.status_code == 200 else {}
        payload["checks"].append(
            {
                "check": "voice_process",
                "status_code": process.status_code,
                "ok": process.status_code == 200 and isinstance(process_json.get("response_text"), str),
                "latency_total_ms": process_json.get("latency_total_ms"),
                "tts_provider": process_json.get("provider"),
            }
        )

        ws_route_exists = any(
            getattr(route, "path", "") == "/v1/voice/stream"
            for route in app.routes
        )
        payload["checks"].append(
            {
                "check": "voice_ws_route",
                "ok": ws_route_exists,
                "route": "/v1/voice/stream",
            }
        )

        ws_events: list[dict[str, Any]] = []
        with client.websocket_connect("/v1/voice/stream") as ws:
            ws.send_json(req)
            for _ in range(6):
                event = ws.receive_json()
                ws_events.append(event)
                if event.get("type") == "done":
                    break
        event_types = [str(evt.get("type") or evt.get("event")) for evt in ws_events]
        payload["checks"].append(
            {
                "check": "voice_ws_stream_flow",
                "ok": "stt" in event_types and "done" in event_types,
                "event_types": event_types,
            }
        )

        payload["sample"] = process_json
        payload["ws_events_preview"] = ws_events[:4]

    payload["status"] = "ok" if all(item.get("ok") for item in payload["checks"]) else "error"
    return payload


def main() -> int:
    args = parse_args()
    result = asyncio.run(run_smoke())
    out = Path(args.out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote json: {out}")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
