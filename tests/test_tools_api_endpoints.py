import os

from fastapi.testclient import TestClient


def test_tools_api_endpoints_exist_and_basic_call(monkeypatch, tmp_path):
    # Keep toolchain logs out of the repo in tests.
    monkeypatch.setenv("DENIS_REPORTS_DIR", str(tmp_path))
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("DENIS_CONTRACT_TEST_MODE", "1")

    from api.fastapi_server import create_app

    app = create_app()
    client = TestClient(app)

    r = client.get("/v1/tools/list")
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert data.get("count", 0) >= 5

    r = client.get("/v1/tools/read_file")
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert data.get("tool") == "read_file"

    r = client.post(
        "/v1/tools/call",
        json={
            "tool": "read_file",
            "arguments": {"path": "api/fastapi_server.py", "max_lines": 5},
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert data.get("tool") == "read_file"
    assert "output" in data

    r = client.post("/v1/tools/history", json={"tool_name": "read_file", "limit": 10})
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert data.get("count", 0) >= 1
    assert isinstance(data.get("events"), list)
