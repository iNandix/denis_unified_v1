"""Tests for neuro event materialization (WS23-G)."""

from unittest.mock import MagicMock, patch
import os

from denis_unified_v1.graph.materializers.event_materializer import materialize_event
from denis_unified_v1.graph.materializers.mappings_v1 import MappingResult


def _mock_graph():
    g = MagicMock()
    g.enabled = True
    g.upsert_component.return_value = True
    g.upsert_neuro_layer.return_value = True
    g.upsert_consciousness_state.return_value = True
    g.upsert_run.return_value = True
    return g


def _base_event(**overrides):
    ev = {
        "event_id": 1,
        "ts": "2026-02-17T00:00:00Z",
        "conversation_id": "test_conv",
        "turn_id": "turn_1",
        "trace_id": "trace_1",
        "type": "neuro.wake.start",
        "payload": {},
    }
    ev.update(overrides)
    return ev


@patch("denis_unified_v1.graph.materializers.event_materializer._try_acquire_mutation", return_value=True)
def test_neuro_wake_start(mock_acq):
    g = _mock_graph()
    ev = _base_event(type="neuro.wake.start", payload={"ts": "2026-02-17T00:00:00Z", "identity_id": "identity:denis"})
    result = materialize_event(ev, graph=g)
    assert result.handled is True
    assert result.component_id == "neuro_layers"
    assert "neuro_wake_start" in (result.mutation_kinds or [])


@patch("denis_unified_v1.graph.materializers.event_materializer._try_acquire_mutation", return_value=True)
def test_neuro_layer_snapshot(mock_acq):
    g = _mock_graph()
    ev = _base_event(
        type="neuro.layer.snapshot",
        payload={
            "layer_index": 3,
            "layer_key": "intent_goals",
            "title": "Intent/Goals",
            "freshness_score": 0.8,
            "status": "ok",
            "signals_count": 2,
        },
    )
    result = materialize_event(ev, graph=g)
    assert result.handled is True
    g.upsert_neuro_layer.assert_called_once()
    call_kwargs = g.upsert_neuro_layer.call_args
    assert call_kwargs.kwargs["layer_id"] == "neuro:layer:3"


@patch("denis_unified_v1.graph.materializers.event_materializer._try_acquire_mutation", return_value=True)
def test_neuro_consciousness_snapshot(mock_acq):
    g = _mock_graph()
    ev = _base_event(
        type="neuro.consciousness.snapshot",
        payload={
            "mode": "awake",
            "fatigue_level": 0.1,
            "risk_level": 0.0,
            "confidence_level": 0.8,
            "guardrails_mode": "normal",
            "memory_mode": "balanced",
            "voice_mode": "off",
            "ops_mode": "normal",
        },
    )
    result = materialize_event(ev, graph=g)
    assert result.handled is True
    g.upsert_consciousness_state.assert_called_once()
    call_kwargs = g.upsert_consciousness_state.call_args
    assert call_kwargs.kwargs["state_id"] == "denis:consciousness"


@patch("denis_unified_v1.graph.materializers.event_materializer._try_acquire_mutation", return_value=True)
def test_neuro_turn_update(mock_acq):
    g = _mock_graph()
    ev = _base_event(
        type="neuro.turn.update",
        payload={
            "layers_summary": [
                {"layer_index": 1, "layer_key": "sensory_io", "freshness_score": 1.0, "status": "ok", "signals_count": 1},
                {"layer_index": 7, "layer_key": "safety_governance", "freshness_score": 0.5, "status": "degraded", "signals_count": 3},
            ],
            "ts": "2026-02-17T00:00:00Z",
        },
    )
    result = materialize_event(ev, graph=g)
    assert result.handled is True
    assert g.upsert_neuro_layer.call_count == 2


@patch("denis_unified_v1.graph.materializers.event_materializer._try_acquire_mutation", return_value=True)
def test_neuro_consciousness_update(mock_acq):
    g = _mock_graph()
    ev = _base_event(
        type="neuro.consciousness.update",
        payload={
            "mode": "focused",
            "fatigue_level": 0.2,
            "risk_level": 0.1,
            "confidence_level": 0.7,
        },
    )
    result = materialize_event(ev, graph=g)
    assert result.handled is True
    g.upsert_consciousness_state.assert_called_once()


@patch("denis_unified_v1.graph.materializers.event_materializer._try_acquire_mutation", return_value=True)
def test_persona_state_update(mock_acq):
    g = _mock_graph()
    ev = _base_event(
        type="persona.state.update",
        payload={"mode": "awake", "ts": "2026-02-17T00:00:00Z"},
    )
    result = materialize_event(ev, graph=g)
    assert result.handled is True
    assert result.component_id == "persona"
    g.upsert_component.assert_called()


@patch("denis_unified_v1.graph.materializers.event_materializer._try_acquire_mutation", return_value=True)
def test_neuro_wake_start_bootstraps_identity(mock_acq):
    """wake.start should MERGE Identity node (bootstrap)."""
    g = _mock_graph()
    ev = _base_event(
        type="neuro.wake.start",
        payload={"ts": "2026-02-17T00:00:00Z", "identity_id": "identity:denis"},
    )
    materialize_event(ev, graph=g)
    # Should have called run_write for Identity MERGE
    identity_calls = [
        c for c in g.run_write.call_args_list
        if "Identity" in str(c)
    ]
    assert len(identity_calls) >= 1


@patch("denis_unified_v1.graph.materializers.event_materializer._try_acquire_mutation", return_value=True)
def test_neuro_consciousness_snapshot_links_identity(mock_acq):
    """consciousness.snapshot should link Identity -> ConsciousnessState."""
    g = _mock_graph()
    ev = _base_event(
        type="neuro.consciousness.snapshot",
        payload={
            "mode": "awake",
            "fatigue_level": 0.1,
            "risk_level": 0.0,
            "confidence_level": 0.8,
            "guardrails_mode": "normal",
        },
    )
    materialize_event(ev, graph=g)
    g.link_identity_consciousness.assert_called_once_with(
        identity_id="identity:denis", state_id="denis:consciousness",
    )
