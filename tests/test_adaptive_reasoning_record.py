from __future__ import annotations


def test_adaptive_reasoning_record_emitted_and_safe(tmp_path, monkeypatch):
    # Ensure no external deps are required.
    monkeypatch.setenv("DENIS_EVENTS_DB_PATH", str(tmp_path / "events.db"))
    monkeypatch.setenv("DENIS_CONTRACT_TEST_MODE", "1")
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("RAG_ENABLED", "0")
    monkeypatch.setenv("INDEXING_ENABLED", "0")
    monkeypatch.setenv("VECTORSTORE_ENABLED", "0")

    # Capture DecisionTrace linkage (without Neo4j).
    captured = {}

    def _fake_emit_decision_trace(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return "trace_fake"

    import denis_unified_v1.actions.decision_trace as dt

    monkeypatch.setattr(dt, "emit_decision_trace", _fake_emit_decision_trace)

    from api.event_bus import reset_event_bus_for_tests
    from api.fastapi_server import create_app
    from fastapi.testclient import TestClient

    reset_event_bus_for_tests()
    app = create_app()
    client = TestClient(app)

    conv = "conv_ar_1"
    # Inject secret-like strings in user prompt; must not appear in reasoning record/events.
    user_prompt = "ping Bearer abcdef sk-ant-12345"
    r = client.post(
        "/v1/chat/completions",
        headers={"X-Denis-Conversation-Id": conv, "X-Denis-Trace-Id": "trace_ar_1"},
        json={"model": "denis-cognitive", "messages": [{"role": "user", "content": user_prompt}], "max_tokens": 8},
    )
    assert r.status_code == 200

    events = client.get(f"/v1/events?conversation_id={conv}&after=0").json()["events"]
    reasoning = [e for e in events if e.get("type") == "agent.reasoning.summary"]
    assert reasoning, "expected agent.reasoning.summary event"
    ar = (reasoning[-1].get("payload") or {}).get("adaptive_reasoning") or {}
    assert ar.get("goal_sha256")
    assert isinstance(ar.get("goal_len"), int)

    # Safety: no secret substrings in stored event payloads.
    raw = str(events)
    assert "Bearer " not in raw
    assert "sk-" not in raw

    # DecisionTrace linkage called with extra containing adaptive_reasoning only.
    extra = (captured.get("kwargs") or {}).get("extra") or {}
    assert "adaptive_reasoning" in extra
    assert "Bearer " not in str(extra)
    assert "sk-" not in str(extra)

