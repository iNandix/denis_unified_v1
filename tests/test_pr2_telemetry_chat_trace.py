from fastapi.testclient import TestClient


def test_pr2_telemetry_counts_and_chat_decision_trace(monkeypatch):
    from api.fastapi_server import create_app

    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("DENIS_CONTRACT_TEST_MODE", "1")

    app = create_app()
    client = TestClient(app)

    r = client.get("/telemetry")
    assert r.status_code == 200
    snap0 = r.json()
    assert "requests" in snap0 and "chat" in snap0

    # Normal chat completion (deterministic path, no external routing)
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "denis-contract-test",
            "messages": [{"role": "user", "content": "ping"}],
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("object") == "chat.completion"

    r = client.get("/telemetry")
    assert r.status_code == 200
    snap1 = r.json()
    assert snap1["chat"]["total"] >= 1
    assert isinstance(snap1["chat"]["last_decisions"], list)
    assert snap1["chat"]["last_decisions"]
    assert snap1["chat"]["last_decisions"][0].get("blocked") is False

    # Hop-blocked request should still return 200 and be recorded
    r = client.post(
        "/v1/chat/completions",
        headers={"X-Denis-Hop": "1"},
        json={
            "model": "denis-contract-test",
            "messages": [{"role": "user", "content": "ping"}],
        },
    )
    assert r.status_code == 200
    blocked = r.json()
    assert blocked.get("meta", {}).get("path") == "blocked_hop"

    r = client.get("/telemetry")
    assert r.status_code == 200
    snap2 = r.json()
    assert snap2["chat"]["blocked_hop_total"] >= 1

