from __future__ import annotations


class ExplodingGraph:
    def __init__(self):
        self.enabled = True

    def __getattr__(self, name):
        raise RuntimeError("graph_down")


def test_graph_materializer_fail_open(monkeypatch, tmp_path):
    monkeypatch.setenv("GRAPH_ENABLED", "1")
    monkeypatch.setenv("DENIS_GML_DB_PATH", str(tmp_path / "gml.db"))

    from denis_unified_v1.graph.materializers.event_materializer import maybe_materialize_event

    ev = {
        "event_id": 9,
        "ts": "2026-02-17T00:00:00Z",
        "conversation_id": "c1",
        "trace_id": "t1",
        "type": "rag.context.compiled",
        "severity": "info",
        "schema_version": "1.0",
        "ui_hint": {"render": "x", "icon": "y"},
        "payload": {"chunks_count": 0, "citations": []},
    }

    # Should not raise even if graph client operations explode.
    maybe_materialize_event(ev, graph=ExplodingGraph())

