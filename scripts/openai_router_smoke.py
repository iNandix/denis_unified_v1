#!/usr/bin/env python3
"""OpenAI-compatible router smoke test."""

import json
import os
import sys
import time
from pathlib import Path
import subprocess
import threading
import socket
import requests


def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"error": "invalid_json", "text": resp.text[:1000]}

def main():
    artifact = {
        "ok": False,
        "reason": None,
        "router_boot": False,
        "models_endpoint": False,
        "chat_endpoint": False,
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
                ["python3", "-m", "uvicorn", "api.fastapi_server:create_app", "--factory", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
                env={"PYTHONPATH": ".", "DISABLE_OBSERVABILITY": "1"},
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
                    artifact["router_boot"] = True
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

        # Headers (auth optional)
        headers = {}
        token = os.getenv("DENIS_API_BEARER_TOKEN", "").strip()
        if token:
            headers["authorization"] = f"Bearer {token}"

        # Test /v1/models
        try:
            resp = requests.get(f"{base_url}/v1/models", timeout=5, headers=headers)
            artifact["models_status_code"] = resp.status_code
            artifact["models_body"] = safe_json(resp)
            if resp.status_code == 200:
                data = artifact["models_body"]
                if isinstance(data, dict) and "data" in data:
                    artifact["models_endpoint"] = True
            else:
                artifact["reason"] = f"/v1/models status {resp.status_code}"
        except Exception as e:
            artifact["reason"] = f"Models endpoint failed: {str(e)}"

        # Test /v1/chat/completions
        try:
            payload = {
                "model": "denis-cognitive",
                "messages": [{"role": "user", "content": "Say hello"}],
                "stream": False,
            }
            resp = requests.post(f"{base_url}/v1/chat/completions", json=payload, timeout=10, headers=headers)
            artifact["chat_status_code"] = resp.status_code
            artifact["chat_body"] = safe_json(resp)
            if resp.status_code == 200:
                data = artifact["chat_body"]
                if isinstance(data, dict) and "choices" in data:
                    artifact["chat_endpoint"] = True
            else:
                artifact["reason"] = f"/v1/chat/completions status {resp.status_code}"
        except Exception as e:
            artifact["reason"] = f"Chat endpoint failed: {str(e)}"

    except Exception as e:
        artifact["reason"] = f"Exception: {str(e)}"

    artifact["overall_success"] = artifact["router_boot"] and artifact["models_endpoint"] and artifact["chat_endpoint"]
    artifact["ok"] = artifact["overall_success"]

    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts/openai_router_smoke.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(artifact, f, indent=2)

    sys.exit(0 if artifact["ok"] else 1)

if __name__ == "__main__":
    main()


# Helpers
def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"error": "invalid_json", "text": resp.text[:1000]}
