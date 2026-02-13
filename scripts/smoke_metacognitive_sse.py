#!/usr/bin/env python3
"""SSE Smoke Test - Verify /metacognitive/events is true SSE."""

import argparse
import json
import sys
import time
import threading
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args():
    parser = argparse.ArgumentParser(description="SSE smoke test")
    parser.add_argument(
        "--out-json",
        default="artifacts/api/metacognitive_sse_smoke.json",
        help="Output artifact path",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=18767,
        help="Port for test server",
    )
    return parser.parse_args()


def run_smoke(port: int):
    """Run SSE smoke test."""
    import subprocess
    import requests

    proc = None
    try:
        # Start server
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "api.fastapi_server:app",
        ]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(PROJECT_ROOT),
        )

        # Wait for server
        for _ in range(30):
            try:
                r = requests.get(f"http://127.0.0.1:{port}/health", timeout=1)
                if r.status_code == 200:
                    break
            except:
                pass
            time.sleep(0.5)
        else:
            return {
                "ok": False,
                "server_started": False,
                "error": "Server didn't start",
            }

        base_url = f"http://127.0.0.1:{port}"

        # Test SSE endpoint
        print(f"Testing {base_url}/metacognitive/events...")

        r = requests.get(
            f"{base_url}/metacognitive/events",
            headers={"Accept": "text/event-stream"},
            stream=True,
            timeout=5,
        )

        http_status = r.status_code
        content_type = r.headers.get("content-type", "")

        # Read first chunk
        first_chunk = b""
        try:
            first_chunk = r.raw.read(300)
        except Exception as e:
            pass

        first_chunk_text = (
            first_chunk.decode("utf-8", errors="replace") if first_chunk else ""
        )

        # Check for SSE indicators
        handshake_ok = "event: hello" in first_chunk_text or "data:" in first_chunk_text
        heartbeats_seen = first_chunk_text.count("event: heartbeat")

        # Determine status
        ok = http_status == 200 and "text/event-stream" in content_type and handshake_ok

        return {
            "ok": ok,
            "http_status": http_status,
            "content_type": content_type,
            "handshake_ok": handshake_ok,
            "first_chunk_present": len(first_chunk) > 0,
            "heartbeats_seen": heartbeats_seen,
            "bytes_read": len(first_chunk),
            "evidence_first_200_bytes": first_chunk_text[:200],
            "server_started": True,
            "port": port,
            "timestamp_utc": _utc_now(),
        }

    except Exception as e:
        import traceback

        return {
            "ok": False,
            "server_started": proc is not None,
            "error": str(e)[:200],
            "traceback": traceback.format_exc()[:300],
            "timestamp_utc": _utc_now(),
        }
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except:
                proc.kill()


def main():
    args = parse_args()
    result = run_smoke(args.port)

    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))
    return 0 if result.get("ok", False) else 1


if __name__ == "__main__":
    sys.exit(main())
