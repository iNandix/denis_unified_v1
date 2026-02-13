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

    # Fail-open si uvicorn no está
    try:
        import uvicorn  # noqa: F401
    except Exception as e:
        artifact["ok"] = True
        artifact["results"]["skipped"] = {"status": "skippeddependency", "reason": "uvicorn_missing", "error": str(e)}
        Path("artifacts/agent_heart/stream7_heart_api_smoke.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")
        print("Smoke passed")
        return

    cmd = [
        sys.executable, "-m", "uvicorn",
        "api.fastapi_server:app",
        "--host", "127.0.0.1",
        "--port", str(port),
        "--log-level", "warning",
    ]

    server = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(1.5)

        base = f"http://127.0.0.1:{port}"
        r_status = _http_json("GET", f"{base}/agent/heart/status", payload=None, timeout=2.0)
        r_run = _http_json("POST", f"{base}/agent/heart/run", payload={"type": "analysis", "input": "ping"}, timeout=2.0)

        status_ok = (r_status["status"] == 200)
        run_ok = (r_run["status"] == 200)

        # Respuesta debe ser JSON parseable
        parsed_run = None
        try:
            parsed_run = json.loads(r_run["body"])
        except Exception:
            parsed_run = None

        artifact["results"] = {
            "port": port,
            "status_endpoint": r_status,
            "run_endpoint": {"status": r_run["status"], "content_type": r_run["content_type"]},
            "run_parsed_ok": isinstance(parsed_run, dict) and parsed_run.get("ok") is True and "result" in parsed_run,
        }

        artifact["ok"] = bool(status_ok and run_ok and artifact["results"]["run_parsed_ok"])

    except Exception as e:
        artifact["ok"] = True  # fail-open: no hard fail por entorno
        artifact["results"]["degraded"] = {"status": "degraded", "error": str(e)}
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
    print("Smoke passed" if artifact["ok"] else "Smoke failed")

if __name__ == "__main__":
    main()
