"""Tests for neuro wake/update sequences (WS23-G) with mocked graph."""

from unittest.mock import MagicMock, patch

from denis_unified_v1.neuro.state import ConsciousnessState, NeuroLayerState
from denis_unified_v1.neuro.sequences import (
    CONSCIOUSNESS_ID,
    IDENTITY_ID,
    wake_sequence,
    update_sequence,
    _apply_turn_updates,
)
from denis_unified_v1.neuro.state import default_layers


def _mock_graph(enabled=True, read_layers=None, read_consciousness=None):
    g = MagicMock()
    g.enabled = enabled
    g._errors_window = 0
    g.run_read.return_value = read_layers or []
    g.upsert_neuro_layer.return_value = True
    g.upsert_consciousness_state.return_value = True
    g.link_identity_neuro_layer.return_value = True
    g.link_identity_consciousness.return_value = True
    g.link_consciousness_layer.return_value = True
    return g


def _mock_emit():
    events = []

    def emit_fn(**kwargs):
        events.append(kwargs)

    return emit_fn, events


def test_wake_sequence_bootstraps_12_layers():
    g = _mock_graph(enabled=True)
    emit_fn, events = _mock_emit()

    cs = wake_sequence(emit_fn=emit_fn, conversation_id="test_conv", graph=g)

    assert isinstance(cs, ConsciousnessState)
    assert cs.mode == "awake"
    assert g.upsert_neuro_layer.call_count == 12
    assert g.upsert_consciousness_state.called
    assert g.link_identity_neuro_layer.call_count == 12
    assert g.link_identity_consciousness.called


def test_wake_sequence_emits_events():
    g = _mock_graph(enabled=True)
    emit_fn, events = _mock_emit()

    wake_sequence(emit_fn=emit_fn, conversation_id="test_conv", graph=g)

    event_types = [e["event_type"] for e in events]
    assert "neuro.wake.start" in event_types
    assert event_types.count("neuro.layer.snapshot") == 12
    assert "neuro.consciousness.snapshot" in event_types
    assert "persona.state.update" in event_types


def test_wake_sequence_graph_disabled_degraded():
    g = _mock_graph(enabled=False)
    emit_fn, events = _mock_emit()

    cs = wake_sequence(emit_fn=emit_fn, conversation_id="test_conv", graph=g)

    assert cs.mode == "degraded"


def test_update_sequence_basic():
    g = _mock_graph(enabled=True)
    emit_fn, events = _mock_emit()

    turn_meta = {
        "input_sha256": "abc123",
        "input_len": 42,
        "modality": "text",
        "retrieval_count": 3,
        "turns_in_session": 1,
    }

    cs = update_sequence(
        emit_fn=emit_fn,
        conversation_id="test_conv",
        turn_meta=turn_meta,
        graph=g,
    )

    assert isinstance(cs, ConsciousnessState)
    event_types = [e["event_type"] for e in events]
    assert "neuro.turn.update" in event_types
    assert "neuro.consciousness.update" in event_types
    assert "persona.state.update" in event_types


def test_update_sequence_ops_degraded():
    g = _mock_graph(enabled=True)
    emit_fn, events = _mock_emit()

    turn_meta = {"ops_degraded": True}

    cs = update_sequence(
        emit_fn=emit_fn,
        conversation_id="test_conv",
        turn_meta=turn_meta,
        graph=g,
    )

    assert cs.mode == "degraded"
    assert cs.guardrails_mode == "strict"


def test_apply_turn_updates_sensory_io():
    layers = default_layers()
    _apply_turn_updates(layers, {"modality": "text"}, "2026-01-01T00:00:00Z")

    l1 = next(l for l in layers if l.layer_key == "sensory_io")
    assert l1.freshness_score == 1.0
    assert l1.signals_count == 1


def test_apply_turn_updates_attention():
    layers = default_layers()
    _apply_turn_updates(layers, {"focus_topic_hash": "abc"}, "2026-01-01T00:00:00Z")

    l2 = next(l for l in layers if l.layer_key == "attention")
    assert l2.freshness_score == 0.9
    assert l2.signals_count == 1


def test_apply_turn_updates_safety_governance_triggers():
    layers = default_layers()
    _apply_turn_updates(
        layers,
        {"risk_signals": 3, "guardrail_triggers": 5},
        "2026-01-01T00:00:00Z",
    )

    l7 = next(l for l in layers if l.layer_key == "safety_governance")
    assert l7.signals_count == 8
    assert l7.status == "degraded"


def test_apply_turn_updates_ops_degraded():
    layers = default_layers()
    _apply_turn_updates(layers, {"ops_degraded": True}, "2026-01-01T00:00:00Z")

    l8 = next(l for l in layers if l.layer_key == "ops_awareness")
    assert l8.status == "degraded"
    assert l8.freshness_score == 0.3
