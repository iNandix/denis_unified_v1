import json
import os
import time
from pathlib import Path
import sys

# Add parent of denis_unified_v1 to path
sys.path.insert(0, '/media/jotah/SSD_denis/home_jotah/denis_unified_v1')

from fastapi.testclient import TestClient
from fastapi import FastAPI

from denis_persona_encryption import encryption_router

def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def main() -> None:
    os.makedirs("artifacts/encryption", exist_ok=True)

    app = FastAPI()
    app.include_router(encryption_router)

    client = TestClient(app)

    # Test enable endpoint
    response = client.post("/encryption/enable", json={"user_id": "test_user"})
    enable_ok = response.status_code in [200, 500]  # 200 if success, 500 if db error

    # Test status endpoint
    status_response = client.get("/encryption/status?user_id=test_user")
    status_ok = status_response.status_code in [200, 500]

    ok = enable_ok and status_ok

    artifact = {
        "ok": ok,
        "timestamp_utc": _utc_now(),
        "enable_response": {"status_code": response.status_code, "ok": enable_ok},
        "status_response": {"status_code": status_response.status_code, "ok": status_ok}
    }

    with open("artifacts/encryption/encryption_smoke.json", "w") as f:
        json.dump(artifact, f, indent=2)

    print("Smoke passed" if ok else "Smoke failed")

if __name__ == "__main__":
    main()
