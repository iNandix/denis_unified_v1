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


def test_capabilities_events_endpoint(base_url: str) -> dict[str, Any]:
    """Test the capabilities events endpoint with timeout."""
    print(f"Testing capabilities events endpoint: {base_url}/metacognitive/capabilities/events")
    try:
        start_time = time.time()
        resp = requests.get(f"{base_url}/metacognitive/capabilities/events", timeout=5, stream=True)
        latency_ms = (time.time() - start_time) * 1000

        print(f"Response status: {resp.status_code}")
        print(f"Response headers: {dict(resp.headers)}")
        
        if resp.status_code == 200:
            # Check if it's SSE stream or JSON
            content_type = resp.headers.get("content-type", "").lower()
            if "text/event-stream" in content_type:
                # Read first few lines to verify SSE format
                lines = []
                for i, line in enumerate(resp.iter_lines(decode_unicode=True)):
                    lines.append(line)
                    if i >= 2:  # Read first 3 lines
                        break
                
                sse_valid = any("event:" in line for line in lines) and any("data:" in line for line in lines)
                return {
                    "ok": True,
                    "status_code": 200,
                    "latency_ms": latency_ms,
                    "stream_type": "sse",
                    "sse_valid": sse_valid,
                    "first_lines": lines
                }
            else:
                # Try to parse as JSON
                try:
                    data = resp.json()
                    return {
                        "ok": True,
                        "status_code": 200,
                        "latency_ms": latency_ms,
                        "stream_type": "json",
                        "data": data
                    }
                except Exception as e:
                    return {
                        "ok": True,
                        "status_code": 200,
                        "latency_ms": latency_ms,
                        "stream_type": "unknown",
                        "parse_error": str(e)
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


def run_self_hosted_smoke(port: int = 0) -> dict[str, Any]:
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
            
            # Check if the port is still free
            try:
                s2 = socket.socket()
                s2.bind(("127.0.0.1", port))
                s2.close()
            except OSError:
                # Port not free, choose another
                s2 = socket.socket()
                s2.bind(("127.0.0.1", 0))
                port = s2.getsockname()[1]
                s2.close()
        
        print(f"Starting server on port {port}...")
        
        # Test create_app in main thread
        try:
            from api.fastapi_server import create_app
            app = create_app()
            print("create_app() succeeded")
        except Exception as e:
            print(f"create_app() failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                "ok": False,
                "endpoint_status": "create_app_failed",
                "error": str(e),
                "port": port
            }
        
        # Start uvicorn server in a thread
        import threading
        server_thread = None
        
        def run_server():
            try:
                import uvicorn
                uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning')
            except Exception as e:
                print(f"Server thread failed: {e}")
                import traceback
                traceback.print_exc()
        
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        
        try:
            # Wait for server to be ready
            base_url = f"http://127.0.0.1:{port}"
            if not wait_for_server_ready(base_url, timeout_sec=30):
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
            # Test capabilities events endpoint
            capabilities_events_result = test_capabilities_events_endpoint(base_url)
            
            # Check if status endpoint worked but capabilities failed (indicates router mounting issue)
            router_mounted = True
            if health_result["ok"] and not (capabilities_result["ok"] and capabilities_events_result["ok"]):
                router_mounted = False
            
            if capabilities_result["ok"] and capabilities_events_result["ok"]:
                # Validate schema if we got data for main capabilities endpoint
                data = capabilities_result.get("data")
                if data and isinstance(data, dict):
                    schema_validation = validate_capabilities_schema(data)
                else:
                    schema_validation = {"schema_valid": False, "errors": ["No data returned"]}
                
                return {
                    "ok": True,
                    "endpoint_status": "success",
                    "port": port,
                    "server_started": True,
                    "status_endpoint_code": 200,
                    "capabilities_endpoint_code": capabilities_result.get("status_code", None),
                    "capabilities_events_endpoint_code": capabilities_events_result.get("status_code", None),
                    "router_mounted": router_mounted,
                    "capabilities_result": capabilities_result,
                    "capabilities_events_result": capabilities_events_result,
                    "schema_validation": schema_validation,
                    "overall_success": schema_validation.get("schema_valid", False)
                }
            else:
                # Fail with evidence if router mounting issue detected
                evidence = {
                    "health_ok": health_result["ok"],
                    "capabilities_ok": capabilities_result["ok"],
                    "capabilities_events_ok": capabilities_events_result["ok"],
                    "router_mounted": router_mounted,
                    "capabilities_error": capabilities_result.get("error"),
                    "capabilities_events_error": capabilities_events_result.get("error")
                }
                
                return {
                    "ok": False,
                    "endpoint_status": "capabilities_failed",
                    "port": port,
                    "server_started": True,
                    "status_endpoint_code": 200,
                    "capabilities_endpoint_code": capabilities_result.get("status_code", None),
                    "capabilities_events_endpoint_code": capabilities_events_result.get("status_code", None),
                    "router_mounted": router_mounted,
                    "evidence": evidence,
                    "capabilities_error": capabilities_result.get("error"),
                    "capabilities_events_error": capabilities_events_result.get("error")
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
        default=0,
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
