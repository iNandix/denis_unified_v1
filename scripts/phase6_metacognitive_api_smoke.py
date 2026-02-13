#!/usr/bin/env python3
"""Phase 6 Metacognitive API Unified Smoke Test - Status, SSE Events & Capabilities."""

import argparse
import json
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
# Also add denis_unified_v1 package to path
denis_pkg = PROJECT_ROOT / "denis_unified_v1"
if str(denis_pkg) not in sys.path:
    sys.path.insert(0, str(denis_pkg))


def test_status_endpoint(client) -> dict:
    """Test GET /metacognitive/status endpoint."""
    try:
        start_time = time.time()
        response = client.get("/metacognitive/status")
        latency_ms = (time.time() - start_time) * 1000

        return {
            "ok": response.status_code == 200,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "has_response": len(response.text.strip()) > 0
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "status_code": None,
            "latency_ms": 0
        }


def test_sse_events_endpoint(client) -> dict:
    """Test GET /metacognitive/events SSE endpoint."""
    try:
        start_time = time.time()
        # Test SSE endpoint with streaming
        with client.stream("GET", "/metacognitive/events") as response:
            latency_ms = (time.time() - start_time) * 1000

            if response.status_code != 200:
                return {
                    "ok": False,
                    "status_code": response.status_code,
                    "latency_ms": latency_ms,
                    "first_chunk_present": False
                }

            # Try to read at least one chunk within timeout
            chunk_timeout = time.time() + 3.0  # 3 second timeout
            first_chunk_received = False

            try:
                for line in response.iter_lines():
                    if line:
                        first_chunk_received = True
                        break
                    if time.time() > chunk_timeout:
                        break
            except Exception:
                pass

            return {
                "ok": response.status_code == 200,
                "status_code": response.status_code,
                "latency_ms": latency_ms,
                "first_chunk_present": first_chunk_received
            }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "status_code": None,
            "latency_ms": 0,
            "first_chunk_present": False
        }


def test_capabilities_endpoint(client) -> dict:
    """Test GET /metacognitive/capabilities endpoint."""
    try:
        start_time = time.time()
        response = client.get("/metacognitive/capabilities")
        latency_ms = (time.time() - start_time) * 1000

        json_valid = False
        if response.status_code == 200:
            try:
                data = response.json()
                json_valid = isinstance(data, dict)
            except Exception:
                json_valid = False

        return {
            "ok": response.status_code == 200 and json_valid,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "json_valid": json_valid,
            "has_response": len(response.text.strip()) > 0
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "status_code": None,
            "latency_ms": 0,
            "json_valid": False
        }


def run_unified_smoke() -> dict:
    """Run unified metacognitive API smoke test."""
    try:
        # Import only what we need for minimal app
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        
        # Import metacognitive router directly
        import api.metacognitive_api as meta
        
        # Create minimal app with just metacognitive router
        app = FastAPI()
        app.include_router(meta.router)
        
        client = TestClient(app)

        # Run all tests
        status_check = test_status_endpoint(client)
        sse_check = test_sse_events_endpoint(client)
        capabilities_check = test_capabilities_endpoint(client)

        # Calculate global OK status
        ok = (
            status_check.get("ok", False) and
            sse_check.get("ok", False) and
            capabilities_check.get("ok", False)
        )

        # Calculate total latency
        total_latency = (
            status_check.get("latency_ms", 0) +
            sse_check.get("latency_ms", 0) +
            capabilities_check.get("latency_ms", 0)
        )

        result = {
            "ok": ok,
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "latency_ms_total": total_latency,
            "status_check": status_check,
            "sse_check": sse_check,
            "capabilities_check": capabilities_check
        }

        return result

    except Exception as e:
        return {
            "ok": False,
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "error": str(e),
            "status_check": {"ok": False, "error": "setup_failed"},
            "sse_check": {"ok": False, "error": "setup_failed"},
            "capabilities_check": {"ok": False, "error": "setup_failed"}
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run phase-6 metacognitive API unified smoke")
    parser.add_argument(
        "--out-json",
        default="artifacts/api/phase6_metacognitive_api_smoke.json",
        help="Output artifact path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    print("Running unified metacognitive API smoke test...")
    result = run_unified_smoke()

    # Write artifact
    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)

    print(f"Artifact written to: {out_path}")
    print(json.dumps(result, indent=2))

    # Return exit code
    return 0 if result.get("ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
