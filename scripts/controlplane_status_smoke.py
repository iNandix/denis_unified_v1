#!/usr/bin/env python3
"""Control Plane status smoke test."""

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
        "controlplane_endpoint": False,
        "schema_valid": False,
        "releaseable": None,
        "degraded_count": 0,
        "top_reasons": [],
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

        # Test /controlplane/status endpoint
        try:
            resp = requests.get(f"{base_url}/controlplane/status", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "releaseable" in data and "degraded_reasons" in data:
                    artifact["controlplane_endpoint"] = True
                    artifact["schema_valid"] = True
                    artifact["releaseable"] = data.get("releaseable")
                    artifact["degraded_count"] = len(data.get("degraded_reasons", []))
                    # Top reasons (first 3)
                    degraded = data.get("degraded_reasons", [])
                    artifact["top_reasons"] = [r.get("reason", "unknown") for r in degraded[:3]]
                else:
                    artifact["reason"] = "Invalid response schema"
            else:
                artifact["reason"] = f"HTTP {resp.status_code}"
        except Exception as e:
            artifact["reason"] = f"Controlplane endpoint failed: {str(e)}"

    except Exception as e:
        artifact["reason"] = f"Exception: {str(e)}"

    artifact["overall_success"] = (
        artifact["server_boot"] and 
        artifact["controlplane_endpoint"] and 
        artifact["schema_valid"]
    )
    artifact["ok"] = artifact["overall_success"]

    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts/control_plane/controlplane_status_smoke.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(artifact, f, indent=2)

    sys.exit(0 if artifact["ok"] else 1)

if __name__ == "__main__":
    main()
