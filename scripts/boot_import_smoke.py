#!/usr/bin/env python3
"""Boot import smoke test."""

import json
import os
import subprocess
import sys
import time
import traceback
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
        os.environ.setdefault("DISABLE_OBSERVABILITY", "1")
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from api.fastapi_server import create_app; create_app()",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
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
            out_path = (
                Path(sys.argv[1])
                if len(sys.argv) > 1
                else Path("artifacts/boot_import_smoke.json")
            )
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with out_path.open("w") as f:
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
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "api.fastapi_server:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--log-level",
                    "warning",
                ],
                env={"PYTHONPATH": ".", "DISABLE_OBSERVABILITY": "1", **os.environ},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()

        # Wait and test /status (with exponential backoff, max 15s)
        base_url = f"http://127.0.0.1:{port}"
        wait_times = [0.2, 0.4, 0.8, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]  # ~10s total
        for wait in wait_times:
            time.sleep(wait)
            try:
                resp = requests.get(f"{base_url}/status", timeout=1)
                if resp.status_code == 200:
                    artifact["status_endpoint"] = True
                    artifact["uvicorn_start"] = True
                    break
            except Exception:
                pass
        else:
            artifact["reason"] = "status endpoint not reachable after 10s"

    except Exception as e:
        artifact["reason"] = f"exception: {str(e)}\n{traceback.format_exc()}"

    artifact["overall_success"] = (
        artifact["boot_import"]
        and artifact["create_app"]
        and artifact["uvicorn_start"]
        and artifact["status_endpoint"]
    )
    artifact["ok"] = artifact["overall_success"]

    # Write artifact
    if len(sys.argv) > 1:
        out_path = Path(sys.argv[1])
    else:
        out_path = Path("artifacts/boot_import_smoke.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with out_path.open("w") as f:
            json.dump(artifact, f, indent=2)
    except Exception as e:
        print(f"Failed to write artifact to {out_path}: {str(e)}")
        sys.exit(1)

    sys.exit(0 if artifact["ok"] else 1)


if __name__ == "__main__":
    main()
