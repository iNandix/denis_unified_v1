from __future__ import annotations


class FakeGraph:
    def __init__(self):
        self.enabled = True
        self.calls = 0

    def __getattr__(self, _name):
        # Count any graph op calls.
        def _fn(*_a, **_k):
            self.calls += 1
            return True

        return _fn


def test_ws_replay_idempotency_same_events_reprocessed_no_extra_mutations(monkeypatch, tmp_path):
    monkeypatch.setenv("DENIS_EVENTS_DB_PATH", str(tmp_path / "events.db"))
    monkeypatch.setenv("DENIS_GML_DB_PATH", str(tmp_path / "gml.db"))
    monkeypatch.setenv("GRAPH_ENABLED", "0")  # disable auto materialize inside emit_event

    from api.event_bus import get_event_store, reset_event_bus_for_tests
    from api.persona.event_router import persona_emit as emit_event
    from denis_unified_v1.graph.materializers.event_materializer import materialize_event

    reset_event_bus_for_tests()

    conv = "conv_replay_1"
    emit_event(
        conversation_id=conv,
        trace_id="t1",
        type="rag.search.start",
        payload={"query_sha256": "0" * 64, "query_len": 4, "k": 8, "filters": None},
        ui_hint={"render": "x", "icon": "y"},
    )
    emit_event(
        conversation_id=conv,
        trace_id="t1",
        type="rag.search.result",
        payload={"selected": [{"chunk_id": "c1", "score": 0.9, "source": "repo", "hash_sha256": "h"}], "warning": None},
        ui_hint={"render": "x", "icon": "y"},
    )
    emit_event(
        conversation_id=conv,
        trace_id="t1",
        type="rag.context.compiled",
        payload={"chunks_count": 1, "citations": [{"chunk_id": "c1", "hash_sha256": "h"}]},
        ui_hint={"render": "x", "icon": "y"},
    )

    events = get_event_store().query_after(conversation_id=conv, after_event_id=0)
    g = FakeGraph()
    for ev in events:
        materialize_event(ev, graph=g)
    c1 = g.calls
    # Replay processing should not create more mutations (dedupe by mutation_id).
    for ev in events:
        materialize_event(ev, graph=g)
    assert g.calls == c1
