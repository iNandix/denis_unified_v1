#!/usr/bin/env python3
"""Phase-6 capabilities registry smoke test - Self-hosted server edition."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import requests
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
# Also add the denis_unified_v1 package to path
denis_pkg = PROJECT_ROOT / "denis_unified_v1"
if str(denis_pkg) not in sys.path:
    sys.path.insert(0, str(denis_pkg))


def _utc_now() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def wait_for_server_ready(base_url: str, timeout_sec: int = 20) -> bool:
    """Wait for server to be ready by polling health endpoint."""
    start_time = time.time()
    while time.time() - start_time < timeout_sec:
        try:
            resp = requests.get(f"{base_url}/health", timeout=2)
            if resp.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.5)
    return False


def test_simple_endpoint(base_url: str) -> dict[str, Any]:
    """Test a simple metacognitive endpoint to check if router is mounted."""
    print(f"Testing simple endpoint: {base_url}/metacognitive/status")
    try:
        start_time = time.time()
        resp = requests.get(f"{base_url}/metacognitive/status", timeout=5)
        latency_ms = (time.time() - start_time) * 1000

        print(f"Status response: {resp.status_code}")
        
        if resp.status_code == 200:
            return {
                "ok": True,
                "status_code": 200,
                "latency_ms": latency_ms
            }
        else:
            return {
                "ok": False,
                "status_code": resp.status_code,
                "latency_ms": latency_ms,
                "error": f"HTTP {resp.status_code}"
            }
    except requests.RequestException as e:
        print(f"Request exception: {e}")
        return {
            "ok": False,
            "status_code": None,
            "latency_ms": 5000,
            "error": str(e)
        }


def test_capabilities_endpoint(base_url: str) -> dict[str, Any]:
    """Test the capabilities endpoint with timeout."""
    print(f"Testing capabilities endpoint: {base_url}/metacognitive/capabilities")
    try:
        start_time = time.time()
        resp = requests.get(f"{base_url}/metacognitive/capabilities", timeout=5)
        latency_ms = (time.time() - start_time) * 1000

        print(f"Response status: {resp.status_code}")
        print(f"Response headers: {dict(resp.headers)}")
        
        if resp.status_code == 200:
            try:
                data = resp.json()
                print(f"Response data keys: {list(data.keys()) if isinstance(data, dict) else 'not dict'}")
                return {
                    "ok": True,
                    "status_code": 200,
                    "latency_ms": latency_ms,
                    "data": data
                }
            except Exception as e:
                print(f"Failed to parse JSON: {e}")
                return {
                    "ok": False,
                    "status_code": 200,
                    "latency_ms": latency_ms,
                    "error": f"Invalid JSON: {e}",
                    "data": None
                }
        else:
            print(f"Error response: {resp.text[:200]}")
            return {
                "ok": False,
                "status_code": resp.status_code,
                "latency_ms": latency_ms,
                "error": f"HTTP {resp.status_code}",
                "data": None
            }
    except requests.RequestException as e:
        print(f"Request exception: {e}")
        return {
            "ok": False,
            "status_code": None,
            "latency_ms": 5000,
            "error": str(e),
            "data": None
        }


def validate_capabilities_schema(data: dict) -> dict[str, Any]:
    """Validate CapabilitySnapshot v1 schema."""
    result = {
        "schema_valid": False,
        "snapshot_version_ok": False,
        "capabilities_present": False,
        "core_evidence": {},
        "errors": []
    }

    # Check snapshot version
    snapshot_version = data.get("snapshot_version")
    if snapshot_version == "v1":
        result["snapshot_version_ok"] = True
    else:
        result["errors"].append(f"Expected snapshot_version 'v1', got '{snapshot_version}'")

    # Check capabilities presence
    capabilities = data.get("capabilities", [])
    if isinstance(capabilities, list) and len(capabilities) > 0:
        result["capabilities_present"] = True
    elif isinstance(capabilities, dict) and len(capabilities) > 0:
        result["capabilities_present"] = True
        capabilities = list(capabilities.values())
    else:
        result["errors"].append("Capabilities array/dict is empty or missing")
        return result

    # Check core capabilities evidence
    core_ids = ["inference", "memory", "tools", "metacognition"]
    core_evidence = {}

    for cap in capabilities:
        cap_id = cap.get("id", "")
        if cap_id in core_ids:
            evidence_count = len(cap.get("evidence", []))
            core_evidence[cap_id] = evidence_count >= 1

    result["core_evidence"] = core_evidence

    # Schema is valid if we have the basics
    result["schema_valid"] = (
        result["snapshot_version_ok"] and
        result["capabilities_present"]
    )

    return result


def run_self_hosted_smoke(port: int = 8085) -> dict[str, Any]:
    """Run smoke test by starting actual uvicorn server and testing endpoints."""
    try:
        import socket
        import subprocess
        import time
        import signal
        import os
        
        # Find free port
        if port == 0:
            s = socket.socket()
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
            s.close()
        
        print(f"Starting server on port {port}...")
        
        # Start uvicorn server
        cmd = [
            sys.executable, "-m", "uvicorn",
            "api.fastapi_server:app",
            "--host", "127.0.0.1",
            "--port", str(port),
            "--log-level", "warning",
        ]
        
        server = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), 
                                stdout=subprocess.DEVNULL, 
                                stderr=subprocess.DEVNULL)
        
        try:
            # Wait for server to be ready
            base_url = f"http://127.0.0.1:{port}"
            if not wait_for_server_ready(base_url, timeout_sec=15):
                return {
                    "ok": False,
                    "endpoint_status": "server_not_ready",
                    "error": "Server failed to start within 15 seconds",
                    "port": port
                }
            
            print("Server ready, testing endpoints...")
            
            # Test health endpoint first
            health_result = test_simple_endpoint(base_url)
            if not health_result["ok"]:
                return {
                    "ok": False,
                    "endpoint_status": "health_failed",
                    "health_error": health_result.get("error"),
                    "port": port
                }
            
            # Test capabilities endpoint
            capabilities_result = test_capabilities_endpoint(base_url)
            
            if capabilities_result["ok"]:
                # Validate schema if we got data
                data = capabilities_result.get("data")
                if data and isinstance(data, dict):
                    schema_validation = validate_capabilities_schema(data)
                else:
                    schema_validation = {"schema_valid": False, "errors": ["No data returned"]}
                
                return {
                    "ok": True,
                    "endpoint_status": "success",
                    "port": port,
                    "capabilities_result": capabilities_result,
                    "schema_validation": schema_validation,
                    "overall_success": schema_validation.get("schema_valid", False)
                }
            else:
                return {
                    "ok": False,
                    "endpoint_status": "capabilities_failed",
                    "capabilities_error": capabilities_result.get("error"),
                    "port": port
                }
                
        finally:
            # Clean up server
            try:
                server.terminate()
                server.wait(timeout=5)
            except Exception:
                try:
                    server.kill()
                except Exception:
                    pass
                    
    except Exception as e:
        print(f"Error in self-hosted smoke test: {e}")
        import traceback
        traceback.print_exc()
        return {
            "ok": False,
            "error": str(e),
            "endpoint_status": "setup_error"
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run phase-6 capabilities registry smoke (self-hosted)")
    parser.add_argument(
        "--out-json",
        default="artifacts/api/phase6_capabilities_registry_smoke.json",
        help="Output artifact path",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8085,
        help="Port to run server on",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    print("Running self-hosted capabilities smoke test...")
    result = run_self_hosted_smoke(port=args.port)

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
