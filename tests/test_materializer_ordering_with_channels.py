from __future__ import annotations


def _disable_neo4j_env(monkeypatch) -> None:
    # Avoid accidental network connections during tests.
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.delenv("NEO4J_USER", raising=False)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    monkeypatch.delenv("NEO4J_PASS", raising=False)


class FakeGraph:
    def __init__(self):
        self.enabled = True
        self.components = []
        self.runs = []
        self.steps = []
        self.artifacts = []
        self.sources = []

    def upsert_feature_flag(self, **kwargs):
        return True

    def upsert_component(self, **kwargs):
        self.components.append(kwargs)
        return True

    def link_component_flag(self, **kwargs):
        return True

    def link_component_depends_on(self, **kwargs):
        return True

    def link_step_component(self, **kwargs):
        return True

    def upsert_run(self, **kwargs):
        self.runs.append(kwargs)
        return True

    def upsert_step(self, **kwargs):
        self.steps.append(kwargs)
        return True

    def upsert_artifact(self, **kwargs):
        self.artifacts.append(kwargs)
        return True

    def upsert_source(self, **kwargs):
        self.sources.append(kwargs)
        return True

    def link_run_step(self, **kwargs):
        return True

    def link_step_artifact(self, **kwargs):
        return True

    def link_artifact_source(self, **kwargs):
        return True

    def link_run_provider(self, **kwargs):
        return True

    def upsert_voice_session(self, **kwargs):
        return True

    def increment_voice_session_error(self, **kwargs):
        return True


def test_materializer_ordering_with_channels(monkeypatch, tmp_path):
    _disable_neo4j_env(monkeypatch)
    monkeypatch.setenv("DENIS_EVENTS_DB_PATH", str(tmp_path / "events.db"))
    monkeypatch.setenv("GRAPH_ENABLED", "0")  # we pass FakeGraph explicitly

    from api.event_bus import get_event_store, reset_event_bus_for_tests
    from api.persona.event_router import persona_emit
    from denis_unified_v1.graph.materializers.event_materializer import materialize_event

    reset_event_bus_for_tests()

    conv = "conv_mat_1"
    trace = "turn_mat_1"

    # Emit a full turn sequence with channel tagging inferred by type.
    persona_emit(
        conversation_id=conv,
        trace_id=trace,
        type="chat.message",
        severity="info",
        ui_hint={"render": "chat_bubble", "icon": "message"},
        payload={"role": "user", "content_sha256": "0" * 64, "content_len": 4},
    )
    persona_emit(
        conversation_id=conv,
        trace_id=trace,
        type="rag.search.start",
        severity="info",
        ui_hint={"render": "rag_search", "icon": "search"},
        payload={"query_sha256": "1" * 64, "query_len": 4, "k": 8, "filters": None},
    )
    persona_emit(
        conversation_id=conv,
        trace_id=trace,
        type="rag.search.result",
        severity="info",
        ui_hint={"render": "rag_result", "icon": "search"},
        payload={
            "query_sha256": "1" * 64,
            "query_len": 4,
            "selected": [{"source": "example.com", "score": 0.9, "chunk_id": "c1"}],
        },
    )
    persona_emit(
        conversation_id=conv,
        trace_id=trace,
        type="rag.context.compiled",
        severity="info",
        ui_hint={"render": "rag_context", "icon": "layers"},
        payload={"chunks_count": 1, "citations": [{"chunk_id": "c1"}]},
    )
    persona_emit(
        conversation_id=conv,
        trace_id=trace,
        type="agent.reasoning.summary",
        severity="info",
        ui_hint={"render": "reasoning_summary", "icon": "brain"},
        payload={
            "adaptive_reasoning": {
                "goal_sha256": "2" * 64,
                "goal_len": 4,
                "constraints_hit": [],
                "tools_used": [],
                "retrieval": {"chunk_ids": ["c1"]},
                "next_action": None,
            }
        },
    )
    persona_emit(
        conversation_id=conv,
        trace_id=trace,
        type="agent.decision_trace_summary",
        severity="info",
        ui_hint={"render": "decision_trace", "icon": "route"},
        payload={"blocked": False, "x_denis_hop": 0, "path": "ok"},
    )

    events = get_event_store().query_after(conversation_id=conv, after_event_id=0)

    wanted = {
        "chat.message",
        "rag.search.start",
        "rag.search.result",
        "rag.context.compiled",
        "agent.reasoning.summary",
        "agent.decision_trace_summary",
    }
    seq = [e for e in events if e.get("type") in wanted]
    types = [e["type"] for e in seq]

    # WS16 ordering policy (within a turn).
    want = [
        "chat.message",
        "rag.search.start",
        "rag.search.result",
        "rag.context.compiled",
        "agent.reasoning.summary",
        "agent.decision_trace_summary",
    ]
    assert types == want

    # Channel tagging + envelope fields present.
    by_type = {e["type"]: e for e in seq}
    assert by_type["chat.message"]["channel"] == "text"
    assert by_type["rag.search.start"]["channel"] == "rag"
    assert by_type["rag.search.result"]["channel"] == "rag"
    assert by_type["rag.context.compiled"]["channel"] == "rag"
    assert by_type["agent.reasoning.summary"]["channel"] == "ops"
    assert by_type["agent.decision_trace_summary"]["channel"] == "ops"

    for e in seq:
        assert e["emitter"] == "denis_persona"
        assert e["stored"] is True
        assert isinstance(e.get("correlation_id"), str) and e["correlation_id"]
        assert isinstance(e.get("turn_id"), str) and e["turn_id"]

    # Materializer accepts channel/stored fields (no crash).
    g = FakeGraph()
    for e in seq:
        _ = materialize_event(e, graph=g)
    assert g.runs, "expected upsert_run calls"

