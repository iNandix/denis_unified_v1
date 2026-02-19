from __future__ import annotations

import os


def _disable_neo4j_env(monkeypatch) -> None:
    # Avoid create_app attempting network connections during tests.
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.delenv("NEO4J_USER", raising=False)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    monkeypatch.delenv("NEO4J_PASS", raising=False)


def test_ws_basic_connect_subscribe_and_receive_hello(tmp_path, monkeypatch):
    _disable_neo4j_env(monkeypatch)
    monkeypatch.setenv("DENIS_EVENTS_DB_PATH", str(tmp_path / "events.db"))

    from api.event_bus import reset_event_bus_for_tests
    from api.fastapi_server import create_app
    from api.persona.event_router import persona_emit as emit_event
    from fastapi.testclient import TestClient

    reset_event_bus_for_tests()
    app = create_app()
    client = TestClient(app)

    with client.websocket_connect("/v1/ws?conversation_id=conv1") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        assert hello["schema_version"] == "1.0"

        ws.send_json({"type": "subscribe", "conversation_id": "conv1", "last_event_id": 0})

        emit_event(
            conversation_id="conv1",
            trace_id="t1",
            type="ops.metric",
            payload={"name": "x", "value": 1.0, "unit": None, "labels": None},
            ui_hint={"render": "metric", "icon": "gauge"},
        )

        ev = ws.receive_json()
        assert ev["type"] == "ops.metric"
        assert ev["conversation_id"] == "conv1"
        assert ev["event_id"] == 1
        assert ev["emitter"] == "denis_persona"
        assert ev["stored"] is True
        assert ev["channel"] == "ops"
        assert isinstance(ev.get("correlation_id"), str) and ev["correlation_id"]
        assert isinstance(ev.get("turn_id"), str) and ev["turn_id"]


def test_ws_replay_after_last_event_id(tmp_path, monkeypatch):
    _disable_neo4j_env(monkeypatch)
    monkeypatch.setenv("DENIS_EVENTS_DB_PATH", str(tmp_path / "events.db"))

    from api.event_bus import reset_event_bus_for_tests
    from api.fastapi_server import create_app
    from api.persona.event_router import persona_emit as emit_event
    from fastapi.testclient import TestClient

    reset_event_bus_for_tests()
    app = create_app()
    client = TestClient(app)

    # Emit 5 events upfront (persisted)
    for i in range(5):
        emit_event(
            conversation_id="conv2",
            trace_id=f"t{i}",
            type="run.step",
            payload={"step_id": f"s{i}", "state": "SUCCESS"},
            ui_hint={"render": "step", "icon": "list"},
        )

    with client.websocket_connect("/v1/ws?conversation_id=conv2") as ws:
        _ = ws.receive_json()  # hello
        ws.send_json({"type": "subscribe", "conversation_id": "conv2", "last_event_id": 2})

        ev3 = ws.receive_json()
        ev4 = ws.receive_json()
        ev5 = ws.receive_json()
        assert [ev3["event_id"], ev4["event_id"], ev5["event_id"]] == [3, 4, 5]
        for ev in (ev3, ev4, ev5):
            assert ev["emitter"] == "denis_persona"
            assert ev["stored"] is True
            assert ev["channel"] in {
                "text",
                "voice",
                "control_room",
                "ops",
                "tool",
                "rag",
                "scrape",
                "compiler",
            }
            assert isinstance(ev.get("correlation_id"), str) and ev["correlation_id"]
            assert isinstance(ev.get("turn_id"), str) and ev["turn_id"]


def test_chat_emits_events_in_order(tmp_path, monkeypatch):
    _disable_neo4j_env(monkeypatch)
    monkeypatch.setenv("DENIS_EVENTS_DB_PATH", str(tmp_path / "events.db"))
    monkeypatch.setenv("DENIS_CONTRACT_TEST_MODE", "1")
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("RAG_ENABLED", "0")
    monkeypatch.setenv("INDEXING_ENABLED", "0")

    from api.event_bus import reset_event_bus_for_tests
    from api.fastapi_server import create_app
    from fastapi.testclient import TestClient

    reset_event_bus_for_tests()
    app = create_app()
    client = TestClient(app)

    conv = "conv_chat_1"
    r = client.post(
        "/v1/chat/completions",
        headers={"X-Denis-Conversation-Id": conv, "X-Denis-Trace-Id": "trace1"},
        json={"model": "denis-cognitive", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 8},
    )
    assert r.status_code == 200

    events = client.get(f"/v1/events?conversation_id={conv}&after=0").json()["events"]
    assert len(events) >= 4
    for ev in events:
        assert ev["emitter"] == "denis_persona"
        assert ev["stored"] is True
        assert ev["channel"] in {
            "text",
            "voice",
            "control_room",
            "ops",
            "tool",
            "rag",
            "scrape",
            "compiler",
        }
        assert isinstance(ev.get("correlation_id"), str) and ev["correlation_id"]
        assert isinstance(ev.get("turn_id"), str) and ev["turn_id"]
    types = [e["type"] for e in events]
    # Required subsequence (fail-open: runtime may be degraded in test env).
    want = [
        "chat.message",
        "run.step",
        "agent.reasoning.summary",
        "agent.decision_trace_summary",
        "chat.message",
    ]
    pos = 0
    for t in types:
        if pos < len(want) and t == want[pos]:
            pos += 1
    assert pos == len(want)
