import os

from fastapi.testclient import TestClient


def test_graph_read_endpoints_fail_open(monkeypatch):
    from api.fastapi_server import create_app

    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("DENIS_CONTRACT_TEST_MODE", "1")
    # Graph reads must still return 200 with warning when graph disabled/unavailable.
    monkeypatch.delenv("GRAPH_ENABLED", raising=False)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)

    app = create_app()
    client = TestClient(app)

    r = client.get("/graph/intent/intent_test_1")
    assert r.status_code == 200
    data = r.json()
    assert data.get("id") == "intent_test_1"
    assert "intent" in data

    r = client.get("/graph/plan/plan_test_1")
    assert r.status_code == 200
    data = r.json()
    assert data.get("id") == "plan_test_1"
    assert "plan" in data


def test_cockpit_route_serves_html(monkeypatch):
    from api.fastapi_server import create_app

    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("DENIS_CONTRACT_TEST_MODE", "1")

    app = create_app()
    client = TestClient(app)

    r = client.get("/cockpit")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "Denis Cockpit" in r.text

