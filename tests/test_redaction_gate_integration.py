from __future__ import annotations


def test_event_payload_guardrails_drop_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("DENIS_EVENTS_DB_PATH", str(tmp_path / "events.db"))
    monkeypatch.setenv("GRAPH_ENABLED", "0")

    from api.event_bus import get_event_store, reset_event_bus_for_tests
    from api.persona.event_router import persona_emit as emit_event

    reset_event_bus_for_tests()
    conv = "conv_guardrails_1"
    emit_event(
        conversation_id=conv,
        trace_id="t1",
        type="tool.result",
        severity="info",
        ui_hint={"render": "x", "icon": "y"},
        payload={
            "authorization": "Bearer abcdef",
            "token": "sk-test-123",
            "content": "do not store this",
            "ok": True,
            "content_sha256": "0" * 64,
            "content_len": 12,
        },
    )

    events = get_event_store().query_after(conversation_id=conv, after_event_id=0)
    assert events
    raw = str(events)
    assert "Bearer " not in raw
    assert "sk-" not in raw
    payload = events[0].get("payload") or {}
    assert "authorization" not in payload
    assert "token" not in payload
    assert "content" not in payload
    assert payload.get("content_sha256") == "0" * 64
    assert payload.get("content_len") == 12
    assert "_guardrails" in payload


def test_indexing_redaction_removes_bearer_and_sk(monkeypatch):
    monkeypatch.setenv("VECTORSTORE_ENABLED", "0")
    monkeypatch.setenv("INDEXING_ENABLED", "1")
    monkeypatch.setenv("QDRANT_COLLECTION_DEFAULT", "denis_chunks_v1")

    from denis_unified_v1.vectorstore.qdrant_client import get_vectorstore, reset_vectorstore_for_tests
    from denis_unified_v1.indexing.indexing_bus import get_indexing_bus, IndexPiece

    reset_vectorstore_for_tests()
    bus = get_indexing_bus()
    bus.upsert_piece(
        IndexPiece(
            kind="scrape",
            title="T",
            content="Authorization: Bearer abc sk-ant-xyz",
            tags=["t"],
            source="scraper",
        )
    )
    store = get_vectorstore()
    col = store.collection_default
    # inspect mock store
    pts = list(store._mock.get(col, {}).values())  # type: ignore[attr-defined]
    assert pts
    joined = str(pts[0].payload)
    # Redaction may keep the prefix but must remove the raw credential.
    assert "Bearer abc" not in joined
    assert "sk-" not in joined
