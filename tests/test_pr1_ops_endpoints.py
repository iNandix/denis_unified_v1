import os

from fastapi.testclient import TestClient


def test_pr1_ops_endpoints_exist_and_fail_open(monkeypatch):
    from api.fastapi_server import create_app

    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("DENIS_CONTRACT_TEST_MODE", "1")

    app = create_app()
    client = TestClient(app)

    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data.get("status"), str)
    assert "timestamp_utc" in data or "timestamp" in data

    r = client.get("/hass/entities")
    assert r.status_code == 200
    data = r.json()
    assert "entities" in data and isinstance(data["entities"], list)
    assert "count" in data and isinstance(data["count"], int)
    assert "hass_connected" in data and isinstance(data["hass_connected"], bool)

    r = client.get("/telemetry")
    assert r.status_code == 200
    data = r.json()
    assert "requests" in data and isinstance(data["requests"], dict)
    assert "timestamp" in data and isinstance(data["timestamp"], str)

