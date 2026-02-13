#!/usr/bin/env python3
"""Observability smoke test: verify tracing/metrics fail-open."""

import json
import sys
import time
from pathlib import Path
import subprocess
import threading
import socket
import requests

def main():
    artifact = {
        "ok": False,
        "reason": None,
        "server_boot": False,
        "observability_endpoint": False,
        "tracing_enabled": None,
        "metrics_enabled": None,
        "timestamp_utc": time.time(),
        "overall_success": False,
    }

    try:
        # Find free port
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()

        # Start server
        def run_server():
            subprocess.run(
                [sys.executable, "-m", "uvicorn", "api.fastapi_server:create_app", "--factory", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
                capture_output=True,
            )

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()

        base_url = f"http://127.0.0.1:{port}"
        
        # Wait for server
        for _ in range(30):
            try:
                resp = requests.get(f"{base_url}/status", timeout=1)
                if resp.status_code == 200:
                    artifact["server_boot"] = True
                    break
            except Exception:
                time.sleep(0.1)
        else:
            artifact["reason"] = "Server failed to start"
            artifact["overall_success"] = False
            artifact["ok"] = artifact["overall_success"]
            with Path(sys.argv[1]).open("w") as f:
                json.dump(artifact, f, indent=2)
            sys.exit(1)

        # Test /observability endpoint
        try:
            resp = requests.get(f"{base_url}/observability", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "observability" in data:
                    obs = data["observability"]
                    artifact["observability_endpoint"] = True
                    artifact["tracing_enabled"] = obs.get("tracing_enabled")
                    artifact["metrics_enabled"] = obs.get("metrics_enabled")
        except Exception as e:
            artifact["reason"] = f"Observability endpoint failed: {str(e)}"

    except Exception as e:
        artifact["reason"] = f"Exception: {str(e)}"

    artifact["overall_success"] = artifact["server_boot"] and artifact["observability_endpoint"]
    artifact["ok"] = artifact["overall_success"]

    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts/observability_smoke.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(artifact, f, indent=2)

    sys.exit(0 if artifact["ok"] else 1)

if __name__ == "__main__":
    main()
