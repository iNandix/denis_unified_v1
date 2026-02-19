from __future__ import annotations


class FakeGraph:
    def __init__(self):
        self.enabled = True
        self.calls = []

    def upsert_feature_flag(self, **kwargs):
        self.calls.append(("flag", kwargs))
        return True

    def upsert_component(self, **kwargs):
        self.calls.append(("component", kwargs))
        return True

    def link_component_flag(self, **kwargs):
        self.calls.append(("component_flag", kwargs))
        return True

    def link_component_depends_on(self, **kwargs):
        self.calls.append(("depends_on", kwargs))
        return True

    def upsert_run(self, **kwargs):
        self.calls.append(("run", kwargs))
        return True

    def upsert_step(self, **kwargs):
        self.calls.append(("step", kwargs))
        return True

    def upsert_artifact(self, **kwargs):
        self.calls.append(("artifact", kwargs))
        return True

    def upsert_source(self, **kwargs):
        self.calls.append(("source", kwargs))
        return True

    def link_run_step(self, **kwargs):
        self.calls.append(("run_step", kwargs))
        return True

    def link_step_artifact(self, **kwargs):
        self.calls.append(("step_artifact", kwargs))
        return True

    def link_artifact_source(self, **kwargs):
        self.calls.append(("artifact_source", kwargs))
        return True

    def link_run_provider(self, **kwargs):
        self.calls.append(("run_provider", kwargs))
        return True


def test_materializer_idempotent_same_event_twice(monkeypatch, tmp_path):
    monkeypatch.setenv("GRAPH_ENABLED", "1")
    monkeypatch.setenv("DENIS_GML_DB_PATH", str(tmp_path / "gml.db"))

    from denis_unified_v1.graph.materializers.event_materializer import materialize_event

    g = FakeGraph()
    ev = {
        "event_id": 7,
        "ts": "2026-02-17T00:00:00Z",
        "conversation_id": "c1",
        "trace_id": "t1",
        "type": "rag.search.result",
        "severity": "info",
        "schema_version": "1.0",
        "ui_hint": {"render": "x", "icon": "y"},
        "payload": {
            "selected": [
                {"chunk_id": "a:0", "score": 0.9, "source": "repo", "hash_sha256": "h1"}
            ],
            "warning": None,
        },
    }

    r1 = materialize_event(ev, graph=g)
    c1 = len(g.calls)
    r2 = materialize_event(ev, graph=g)
    c2 = len(g.calls)

    assert r1.handled is True
    assert r2.handled is True
    # second pass should not apply new mutations
    assert c2 == c1

