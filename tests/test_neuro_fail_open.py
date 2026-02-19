"""Tests for neuro fail-open behavior (WS23-G) — graph down scenarios."""

from unittest.mock import MagicMock

from denis_unified_v1.neuro.sequences import wake_sequence, update_sequence
from denis_unified_v1.neuro.state import ConsciousnessState


def _graph_disabled():
    g = MagicMock()
    g.enabled = False
    g._errors_window = 0
    g.run_read.return_value = []
    g.upsert_neuro_layer.return_value = False
    g.upsert_consciousness_state.return_value = False
    g.link_identity_neuro_layer.return_value = False
    g.link_identity_consciousness.return_value = False
    g.link_consciousness_layer.return_value = False
    return g


def _graph_errors():
    g = MagicMock()
    g.enabled = True
    g._errors_window = 10
    g.run_read.return_value = []
    g.upsert_neuro_layer.return_value = False
    g.upsert_consciousness_state.return_value = False
    g.link_identity_neuro_layer.return_value = False
    g.link_identity_consciousness.return_value = False
    g.link_consciousness_layer.return_value = False
    return g


def _mock_emit():
    events = []

    def emit_fn(**kwargs):
        events.append(kwargs)

    return emit_fn, events


def test_wake_graph_disabled_returns_degraded():
    g = _graph_disabled()
    emit_fn, events = _mock_emit()

    cs = wake_sequence(emit_fn=emit_fn, conversation_id="test", graph=g)

    assert isinstance(cs, ConsciousnessState)
    assert cs.mode == "degraded"
    assert cs.guardrails_mode == "strict"
    # Events still emitted (fail-open)
    event_types = [e["event_type"] for e in events]
    assert "neuro.wake.start" in event_types


def test_wake_graph_errors_returns_degraded():
    g = _graph_errors()
    emit_fn, events = _mock_emit()

    cs = wake_sequence(emit_fn=emit_fn, conversation_id="test", graph=g)

    assert cs.mode == "degraded"


def test_update_graph_disabled_returns_degraded():
    g = _graph_disabled()
    emit_fn, events = _mock_emit()

    cs = update_sequence(
        emit_fn=emit_fn,
        conversation_id="test",
        turn_meta={"input_len": 10},
        graph=g,
    )

    assert isinstance(cs, ConsciousnessState)
    assert cs.mode == "degraded"


def test_wake_emit_failure_does_not_raise():
    """Emit function raises, but wake_sequence still returns."""
    g = _graph_disabled()

    def bad_emit(**kwargs):
        raise RuntimeError("emit broken")

    cs = wake_sequence(emit_fn=bad_emit, conversation_id="test", graph=g)
    assert isinstance(cs, ConsciousnessState)


def test_update_emit_failure_does_not_raise():
    """Emit function raises, but update_sequence still returns."""
    g = _graph_disabled()

    def bad_emit(**kwargs):
        raise RuntimeError("emit broken")

    cs = update_sequence(
        emit_fn=bad_emit,
        conversation_id="test",
        turn_meta={},
        graph=g,
    )
    assert isinstance(cs, ConsciousnessState)


# ── Executor consciousness integration (WS23-G) ──────────────


def test_executor_strict_guardrails_blocks_run_command():
    """When consciousness has guardrails_mode=strict, only read-only tools allowed."""
    from denis_unified_v1.cognition.executor import Executor

    executor = Executor(tool_registry={"run_command": lambda **kw: "ok", "read_file": lambda **kw: "ok"})

    # strict -> run_command blocked
    assert not executor._is_tool_allowed(
        "run_command", "test", "high",
        consciousness={"guardrails_mode": "strict"},
    )
    # strict -> read_file allowed
    assert executor._is_tool_allowed(
        "read_file", "test", "high",
        consciousness={"guardrails_mode": "strict"},
    )


def test_executor_degraded_mode_blocks_mutating_tools():
    """When consciousness mode=degraded, only read-only tools allowed."""
    from denis_unified_v1.cognition.executor import Executor

    executor = Executor(tool_registry={})
    assert not executor._is_tool_allowed(
        "run_command", "test", "high",
        consciousness={"mode": "degraded"},
    )
    assert executor._is_tool_allowed(
        "grep_search", "test", "high",
        consciousness={"mode": "degraded"},
    )


def test_executor_normal_consciousness_allows_all():
    """Normal consciousness state allows all tools as usual."""
    from denis_unified_v1.cognition.executor import Executor

    executor = Executor(tool_registry={})
    assert executor._is_tool_allowed(
        "run_command", "test", "high",
        consciousness={"guardrails_mode": "normal", "mode": "awake"},
    )


def test_executor_no_consciousness_allows_all():
    """No consciousness state (None) allows all tools (fail-open)."""
    from denis_unified_v1.cognition.executor import Executor

    executor = Executor(tool_registry={})
    assert executor._is_tool_allowed("run_command", "test", "high", consciousness=None)
