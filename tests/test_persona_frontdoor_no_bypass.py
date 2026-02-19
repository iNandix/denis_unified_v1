from __future__ import annotations


def test_persona_frontdoor_blocks_direct_event_bus_emit(tmp_path, monkeypatch):
    monkeypatch.setenv("DENIS_EVENTS_DB_PATH", str(tmp_path / "events.db"))
    monkeypatch.setenv("PERSONA_FRONTDOOR_ENFORCE", "1")
    monkeypatch.setenv("PERSONA_FRONTDOOR_BYPASS_MODE", "raise")

    import pytest

    from api.event_bus import emit_event, reset_event_bus_for_tests

    reset_event_bus_for_tests()

    with pytest.raises(RuntimeError):
        emit_event(
            conversation_id="conv_pf_1",
            trace_id="trace_pf_1",
            type="ops.metric",
            payload={"name": "x", "value": 1.0, "unit": None, "labels": None},
        )


def test_persona_emit_sets_emitter(tmp_path, monkeypatch):
    monkeypatch.setenv("DENIS_EVENTS_DB_PATH", str(tmp_path / "events.db"))
    monkeypatch.setenv("PERSONA_FRONTDOOR_ENFORCE", "1")
    monkeypatch.setenv("PERSONA_FRONTDOOR_BYPASS_MODE", "raise")

    from api.event_bus import get_event_store, reset_event_bus_for_tests
    from api.persona.event_router import persona_emit

    reset_event_bus_for_tests()

    ev = persona_emit(
        conversation_id="conv_pf_2",
        trace_id="trace_pf_2",
        type="ops.metric",
        payload={"name": "x", "value": 1.0, "unit": None, "labels": None},
        ui_hint={"render": "metric", "icon": "gauge"},
    )

    assert ev["emitter"] == "denis_persona"
    assert ev["correlation_id"] == "trace_pf_2"
    assert ev["turn_id"] == "trace_pf_2"

    stored = get_event_store().query_after(conversation_id="conv_pf_2", after_event_id=0)
    assert stored and stored[0]["emitter"] == "denis_persona"

