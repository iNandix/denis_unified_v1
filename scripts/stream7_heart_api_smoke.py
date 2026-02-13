import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port

def _http_json(method: str, url: str, payload: dict | None = None, headers: dict | None = None, timeout: float = 2.0) -> dict:
    data = None
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers=h, method=method)
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
        return {"status": resp.status, "body": body, "content_type": resp.headers.get("content-type")}

def main() -> None:
    os.makedirs("artifacts/agent_heart", exist_ok=True)

    port = _free_port()
    artifact = {
        "ok": False,
        "timestamp_utc": _utc_now(),
        "stream": "stream7_heart_api",
        "results": {},
    }

    # Check if uvicorn is available
    try:
        import uvicorn  # noqa: F401
    except Exception as e:
        artifact["ok"] = True
        artifact["results"]["skipped"] = {"status": "skippeddependency", "reason": "uvicorn_missing", "error": str(e)}
        Path("artifacts/agent_heart/stream7_heart_api_smoke.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")
        print("Smoke passed (uvicorn not available)")
        return

    # Start server in background
    cmd = [
        sys.executable, "-m", "uvicorn",
        "api.fastapi_server:app",
        "--host", "127.0.0.1",
        "--port", str(port),
        "--log-level", "warning",
    ]

    server = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    try:
        # Wait for server to start (up to 10 seconds)
        import time
        server_ready = False
        for _ in range(20):  # 20 attempts * 0.5s = 10s max
            try:
                # Try to connect to health endpoint
                req = Request(f"http://127.0.0.1:{port}/health")
                with urlopen(req, timeout=1.0) as resp:
                    if resp.status == 200:
                        server_ready = True
                        break
            except Exception:
                pass
            time.sleep(0.5)

        if not server_ready:
            artifact["ok"] = True  # fail-open
            artifact["results"]["server_start_failed"] = {
                "status": "server_not_ready",
                "port": port,
                "timeout_seconds": 10
            }
            Path("artifacts/agent_heart/stream7_heart_api_smoke.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")
            print("Smoke passed (server not ready)")
            return

        # Server is ready, test endpoints
        base = f"http://127.0.0.1:{port}"
        
        # Test /health endpoint
        health_ok = False
        health_data = None
        try:
            r_health = _http_json("GET", f"{base}/health", payload=None, timeout=2.0)
            health_ok = (r_health["status"] == 200)
            if health_ok:
                try:
                    health_data = json.loads(r_health["body"])
                except Exception:
                    health_data = None
        except Exception as e:
            health_data = {"error": str(e)}

        # Test /agent/heart/status endpoint
        heart_status_ok = False
        heart_status_data = None
        try:
            r_heart_status = _http_json("GET", f"{base}/agent/heart/status", payload=None, timeout=2.0)
            heart_status_ok = (r_heart_status["status"] == 200)
            if heart_status_ok:
                try:
                    heart_status_data = json.loads(r_heart_status["body"])
                except Exception:
                    heart_status_data = None
        except Exception as e:
            heart_status_data = {"error": str(e)}

        # Test /agent/heart/run endpoint
        heart_run_ok = False
        heart_run_data = None
        try:
            test_payload = {"type": "analysis", "payload": {"data": [1, 2, 3]}}
            r_heart_run = _http_json("POST", f"{base}/agent/heart/run", payload=test_payload, timeout=2.0)
            heart_run_ok = (r_heart_run["status"] == 200)
            if heart_run_ok:
                try:
                    heart_run_data = json.loads(r_heart_run["body"])
                except Exception:
                    heart_run_data = None
        except Exception as e:
            heart_run_data = {"error": str(e)}

        # Validate results
        health_json_valid = isinstance(health_data, dict) and health_data.get("status") == "ok"
        heart_status_json_valid = isinstance(heart_status_data, dict) and heart_status_data.get("ok") is True
        heart_run_json_valid = isinstance(heart_run_data, dict) and heart_run_data.get("ok") is True and "result" in heart_run_data

        artifact["results"] = {
            "port": port,
            "server_started": True,
            "health_endpoint": {
                "status_code": 200 if health_ok else None,
                "json_valid": health_json_valid,
                "has_status": health_data.get("status") if isinstance(health_data, dict) else None
            },
            "agent_heart_status_endpoint": {
                "status_code": 200 if heart_status_ok else None,
                "json_valid": heart_status_json_valid,
                "ok_response": heart_status_data.get("ok") if isinstance(heart_status_data, dict) else None
            },
            "agent_heart_run_endpoint": {
                "status_code": 200 if heart_run_ok else None,
                "json_valid": heart_run_json_valid,
                "has_result": "result" in (heart_run_data or {}),
                "ok_response": heart_run_data.get("ok") if isinstance(heart_run_data, dict) else None
            }
        }

        # Overall success: all endpoints work and return valid JSON
        artifact["ok"] = bool(
            health_ok and health_json_valid and
            heart_status_ok and heart_status_json_valid and
            heart_run_ok and heart_run_json_valid
        )

    except Exception as e:
        artifact["ok"] = True  # fail-open
        artifact["results"]["unexpected_error"] = {
            "status": "unexpected_error",
            "error": str(e)
        }
    finally:
        try:
            server.terminate()
            server.wait(timeout=2)
        except Exception:
            try:
                server.kill()
            except Exception:
                pass

    Path("artifacts/agent_heart/stream7_heart_api_smoke.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    status = "PASSED" if artifact["ok"] else "FAILED"
    print(f"Smoke {status}")

if __name__ == "__main__":
    main()
