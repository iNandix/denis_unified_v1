"""Unit tests for neuro state module (WS23-G)."""

from denis_unified_v1.neuro.state import (
    LAYER_DEFINITIONS,
    ConsciousnessState,
    NeuroLayerState,
    default_layers,
    derive_consciousness,
)


def test_layer_definitions_count():
    assert len(LAYER_DEFINITIONS) == 12
    indices = [ld["layer_index"] for ld in LAYER_DEFINITIONS]
    assert indices == list(range(1, 13))


def test_default_layers():
    layers = default_layers()
    assert len(layers) == 12
    for i, layer in enumerate(layers, 1):
        assert layer.layer_index == i
        assert layer.freshness_score == 0.5
        assert layer.status == "ok"
        assert layer.signals_count == 0
        assert layer.last_update_ts != ""


def test_neuro_layer_id():
    layer = NeuroLayerState(layer_index=3, layer_key="intent_goals", title="Intent/Goals")
    assert layer.id == "neuro:layer:3"


def test_neuro_layer_to_dict():
    layer = NeuroLayerState(layer_index=1, layer_key="sensory_io", title="Sensory/IO")
    d = layer.to_dict()
    assert d["layer_index"] == 1
    assert d["layer_key"] == "sensory_io"
    assert "title" in d


def test_consciousness_state_to_dict():
    cs = ConsciousnessState(mode="awake")
    d = cs.to_dict()
    assert d["mode"] == "awake"
    assert "STATE_ID" not in d
    assert "fatigue_level" in d


def test_derive_consciousness_awake():
    layers = default_layers()
    cs = derive_consciousness(layers, ops_healthy=True, graph_up=True)
    assert cs.mode == "awake"
    assert cs.guardrails_mode == "normal"
    assert cs.ops_mode == "normal"


def test_derive_consciousness_degraded_graph_down():
    layers = default_layers()
    cs = derive_consciousness(layers, ops_healthy=True, graph_up=False)
    assert cs.mode == "degraded"
    assert cs.guardrails_mode == "strict"


def test_derive_consciousness_degraded_ops_down():
    layers = default_layers()
    cs = derive_consciousness(layers, ops_healthy=False, graph_up=True)
    assert cs.mode == "degraded"


def test_derive_consciousness_focused():
    layers = default_layers()
    cs = derive_consciousness(layers, ops_healthy=True, graph_up=True, active_plans=True)
    assert cs.mode == "focused"


def test_derive_consciousness_risk_triggers_strict():
    layers = default_layers()
    for l in layers:
        if l.layer_key == "safety_governance":
            l.signals_count = 10  # high risk signals
            break
    cs = derive_consciousness(layers, ops_healthy=True, graph_up=True)
    assert cs.risk_level >= 0.5
    assert cs.guardrails_mode == "strict"


def test_derive_consciousness_memory_mode_long():
    layers = default_layers()
    for l in layers:
        if l.layer_key == "memory_long":
            l.freshness_score = 0.9
            break
    cs = derive_consciousness(layers, ops_healthy=True, graph_up=True)
    assert cs.memory_mode == "long"


def test_derive_consciousness_memory_mode_short():
    layers = default_layers()
    for l in layers:
        if l.layer_key == "memory_short":
            l.freshness_score = 0.2
            break
        if l.layer_key == "memory_long":
            l.freshness_score = 0.3
            break
    cs = derive_consciousness(layers, ops_healthy=True, graph_up=True)
    assert cs.memory_mode == "short"


def test_derive_consciousness_voice_on():
    layers = default_layers()
    cs = derive_consciousness(layers, voice_enabled=True, ops_healthy=True, graph_up=True)
    assert cs.voice_mode == "on"


def test_derive_consciousness_ops_incident():
    layers = default_layers()
    for l in layers:
        if l.layer_key == "ops_awareness":
            l.status = "degraded"
            break
    cs = derive_consciousness(layers, ops_healthy=True, graph_up=True)
    assert cs.ops_mode == "incident"


# ── Multi-layer derivation tests (WS23-G enrichment) ──────────


def test_derive_degraded_when_meta_consciousness_stale():
    """L12 meta_consciousness very stale -> degraded mode."""
    layers = default_layers()
    for l in layers:
        if l.layer_key == "meta_consciousness":
            l.freshness_score = 0.1
            break
    cs = derive_consciousness(layers, ops_healthy=True, graph_up=True)
    assert cs.mode == "degraded"


def test_derive_degraded_when_ops_awareness_degraded():
    """L8 ops_awareness degraded status -> degraded mode (via by_key check)."""
    layers = default_layers()
    for l in layers:
        if l.layer_key == "ops_awareness":
            l.status = "error"
            break
    cs = derive_consciousness(layers, ops_healthy=True, graph_up=True)
    assert cs.mode == "degraded"


def test_derive_focused_from_attention_signals():
    """L2 attention with high freshness + signals -> focused mode."""
    layers = default_layers()
    for l in layers:
        if l.layer_key == "attention":
            l.freshness_score = 0.9
            l.signals_count = 5
            break
    cs = derive_consciousness(layers, ops_healthy=True, graph_up=True)
    assert cs.mode == "focused"


def test_risk_from_intent_goals_signals():
    """L3 intent_goals with many signals adds risk."""
    layers = default_layers()
    for l in layers:
        if l.layer_key == "intent_goals":
            l.signals_count = 10
            break
    cs = derive_consciousness(layers, ops_healthy=True, graph_up=True)
    assert cs.risk_level > 0.0


def test_confidence_lowered_by_social_persona_degraded():
    """L9 social_persona degraded -> confidence capped at 0.5."""
    layers = default_layers()
    for l in layers:
        if l.layer_key == "social_persona":
            l.status = "degraded"
            break
    cs = derive_consciousness(layers, ops_healthy=True, graph_up=True)
    assert cs.confidence_level <= 0.5


def test_confidence_lowered_by_meta_consciousness_errors():
    """L12 meta_consciousness with many error signals -> lower confidence."""
    layers = default_layers()
    for l in layers:
        if l.layer_key == "meta_consciousness":
            l.signals_count = 10
            l.freshness_score = 0.5  # enough to not trigger degraded
            break
    cs = derive_consciousness(layers, ops_healthy=True, graph_up=True)
    assert cs.confidence_level < 0.7


def test_fatigue_extra_from_stale_learning_plasticity():
    """L11 learning_plasticity stale -> extra fatigue."""
    layers = default_layers()
    for l in layers:
        if l.layer_key == "learning_plasticity":
            l.freshness_score = 0.1
            break
    cs_stale = derive_consciousness(layers, ops_healthy=True, graph_up=True)

    layers2 = default_layers()
    cs_fresh = derive_consciousness(layers2, ops_healthy=True, graph_up=True)
    # Stale L11 should produce higher fatigue
    assert cs_stale.fatigue_level > cs_fresh.fatigue_level


def test_fatigue_weighted_critical_layers():
    """Critical layers (L1, L8, L12) weight 2x for fatigue calculation."""
    layers = default_layers()
    # Set only L1 (critical, 2x weight) to very low freshness
    for l in layers:
        if l.layer_key == "sensory_io":
            l.freshness_score = 0.0
            break
    cs_l1 = derive_consciousness(layers, ops_healthy=True, graph_up=True)

    layers2 = default_layers()
    # Set only L2 (normal, 1x weight) to very low freshness
    for l in layers2:
        if l.layer_key == "attention":
            l.freshness_score = 0.0
            break
    cs_l2 = derive_consciousness(layers2, ops_healthy=True, graph_up=True)
    # L1 stale should produce more fatigue than L2 stale
    assert cs_l1.fatigue_level > cs_l2.fatigue_level
