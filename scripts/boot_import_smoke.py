#!/usr/bin/env python3
"""Boot import smoke: verify server starts without optional dependencies."""

import json
import subprocess
import sys
import time
from pathlib import Path

def main():
    artifact = {
        "ok": False,
        "reason": None,
        "boot_import": False,
        "create_app": False,
        "uvicorn_start": False,
        "status_endpoint": False,
        "timestamp_utc": time.time(),
    }

    try:
        # 1. Test import and create_app
        result = subprocess.run(
            [sys.executable, "-c", "from api.fastapi_server import create_app; create_app()"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            artifact["create_app"] = True
            artifact["boot_import"] = True
        else:
            artifact["reason"] = f"create_app failed: {result.stderr[:200]}"
            artifact["overall_success"] = False
            artifact["ok"] = artifact["overall_success"]
            with Path(sys.argv[2]).open("w") as f:
                json.dump(artifact, f, indent=2)
            sys.exit(1 if not artifact["ok"] else 0)

        # 2. Start uvicorn and test /status
        import threading
        import socket
        import requests

        # Find free port
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()

        def run_server():
            subprocess.run(
                [sys.executable, "-m", "uvicorn", "api.fastapi_server:create_app", "--factory", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
                capture_output=True,
            )

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()

        # Wait and test /status
        base_url = f"http://127.0.0.1:{port}"
        for _ in range(30):
            try:
                resp = requests.get(f"{base_url}/status", timeout=1)
                if resp.status_code == 200:
                    artifact["status_endpoint"] = True
                    artifact["uvicorn_start"] = True
                    break
            except Exception:
                time.sleep(0.1)
        else:
            artifact["reason"] = "status endpoint not reachable after 3s"

    except Exception as e:
        artifact["reason"] = f"exception: {str(e)}"

    artifact["overall_success"] = artifact["boot_import"] and artifact["create_app"] and artifact["uvicorn_start"] and artifact["status_endpoint"]
    artifact["ok"] = artifact["overall_success"]

    # Write artifact
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("artifacts/boot_import_smoke.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(artifact, f, indent=2)

    sys.exit(0 if artifact["ok"] else 1)

if __name__ == "__main__":
    main()
