"""Neuro state definitions and derivation logic (WS23-G).

Pure data + pure functions.  No I/O, no graph calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── 12 Layer Definitions ────────────────────────────────────────────

LAYER_DEFINITIONS: list[dict[str, Any]] = [
    {"layer_index": 1, "layer_key": "sensory_io", "title": "Sensory/IO"},
    {"layer_index": 2, "layer_key": "attention", "title": "Attention"},
    {"layer_index": 3, "layer_key": "intent_goals", "title": "Intent/Goals"},
    {"layer_index": 4, "layer_key": "plans_procedures", "title": "Plans/Procedures"},
    {"layer_index": 5, "layer_key": "memory_short", "title": "Memory Short"},
    {"layer_index": 6, "layer_key": "memory_long", "title": "Memory Long"},
    {"layer_index": 7, "layer_key": "safety_governance", "title": "Safety/Governance"},
    {"layer_index": 8, "layer_key": "ops_awareness", "title": "Ops Awareness"},
    {"layer_index": 9, "layer_key": "social_persona", "title": "Social/Persona"},
    {"layer_index": 10, "layer_key": "self_monitoring", "title": "Self-Monitoring"},
    {"layer_index": 11, "layer_key": "learning_plasticity", "title": "Learning/Plasticity"},
    {"layer_index": 12, "layer_key": "meta_consciousness", "title": "Meta/Consciousness"},
]


# ── Dataclasses ─────────────────────────────────────────────────────

@dataclass
class NeuroLayerState:
    layer_index: int
    layer_key: str
    title: str
    freshness_score: float = 0.5
    status: str = "ok"
    signals_count: int = 0
    last_update_ts: str = ""
    notes_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def id(self) -> str:
        return f"neuro:layer:{self.layer_index}"


@dataclass
class ConsciousnessState:
    mode: str = "awake"  # awake | focused | idle | degraded
    focus_topic_hash: str = ""
    fatigue_level: float = 0.0
    risk_level: float = 0.0
    confidence_level: float = 0.7
    last_wake_ts: str = ""
    last_turn_ts: str = ""
    guardrails_mode: str = "normal"  # normal | strict
    memory_mode: str = "balanced"  # short | balanced | long
    voice_mode: str = "off"  # on | off | stub
    ops_mode: str = "normal"  # normal | incident

    STATE_ID: str = field(default="denis:consciousness", init=False, repr=False)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("STATE_ID", None)
        return d


# ── Defaults ────────────────────────────────────────────────────────

def default_layers() -> list[NeuroLayerState]:
    """Return 12 layers with fresh defaults."""
    now = _utc_now_iso()
    return [
        NeuroLayerState(
            layer_index=ld["layer_index"],
            layer_key=ld["layer_key"],
            title=ld["title"],
            freshness_score=0.5,
            status="ok",
            signals_count=0,
            last_update_ts=now,
        )
        for ld in LAYER_DEFINITIONS
    ]


# ── Derivation (pure) ──────────────────────────────────────────────

def derive_consciousness(
    layers: list[NeuroLayerState],
    *,
    ops_healthy: bool = True,
    voice_enabled: bool = False,
    active_plans: bool = False,
    graph_up: bool = True,
) -> ConsciousnessState:
    """Derive ConsciousnessState from ALL 12 layers + runtime signals.

    Pure function — no I/O.

    Layer contributions:
      L1  sensory_io          -> fatigue (input freshness)
      L2  attention           -> mode (focused if high freshness + signals)
      L3  intent_goals        -> risk (constraints_hit via signals), mode
      L4  plans_procedures    -> mode (focused when active)
      L5  memory_short        -> memory_mode
      L6  memory_long         -> memory_mode
      L7  safety_governance   -> risk, guardrails_mode
      L8  ops_awareness       -> ops_mode, mode (degraded)
      L9  social_persona      -> confidence (contradictions)
      L10 self_monitoring     -> confidence (primary)
      L11 learning_plasticity -> fatigue (staleness indicator)
      L12 meta_consciousness  -> confidence (errors), mode (degraded if stale)
    """
    now = _utc_now_iso()

    # Index layers by key for quick lookup
    by_key: dict[str, NeuroLayerState] = {l.layer_key: l for l in layers}

    # ── Mode derivation (multi-layer) ──────────────────────────
    if not graph_up or not ops_healthy:
        mode = "degraded"
    else:
        l8 = by_key.get("ops_awareness")
        l12 = by_key.get("meta_consciousness")
        if l8 and l8.status in ("degraded", "error"):
            mode = "degraded"
        elif l12 and l12.freshness_score < 0.2:
            mode = "degraded"
        elif active_plans:
            mode = "focused"
        else:
            # L2 attention: high signals + freshness -> focused
            l2 = by_key.get("attention")
            if l2 and l2.freshness_score > 0.8 and l2.signals_count > 2:
                mode = "focused"
            else:
                mode = "awake"

    # ── Risk (L7 primary, L3 secondary) ────────────────────────
    l7 = by_key.get("safety_governance")
    risk = 0.0
    if l7:
        risk = min(1.0, l7.signals_count * 0.1) if l7.signals_count > 0 else 0.0
        if l7.status == "degraded":
            risk = max(risk, 0.5)
    # L3 intent_goals: constraints hit add risk
    l3 = by_key.get("intent_goals")
    if l3 and l3.signals_count > 3:
        risk = min(1.0, risk + l3.signals_count * 0.03)

    # ── Fatigue (all layers, weighted) ─────────────────────────
    # Critical layers (L1, L8, L12) weight 2x for fatigue
    critical_keys = {"sensory_io", "ops_awareness", "meta_consciousness"}
    weighted_sum = 0.0
    weight_total = 0.0
    for l in layers:
        w = 2.0 if l.layer_key in critical_keys else 1.0
        weighted_sum += l.freshness_score * w
        weight_total += w
    avg_freshness = weighted_sum / weight_total if weight_total > 0 else 0.5
    fatigue = max(0.0, min(1.0, 1.0 - avg_freshness))

    # L11 learning_plasticity: very stale -> extra fatigue
    l11 = by_key.get("learning_plasticity")
    if l11 and l11.freshness_score < 0.3:
        fatigue = min(1.0, fatigue + 0.1)

    # ── Confidence (L10 primary, L9 + L12 secondary) ──────────
    l10 = by_key.get("self_monitoring")
    confidence = 0.7
    if l10:
        if l10.status == "degraded":
            confidence = 0.4
        elif l10.signals_count > 5:
            confidence = max(0.3, 0.7 - l10.signals_count * 0.05)

    # L9 social_persona: contradiction signals lower confidence
    l9 = by_key.get("social_persona")
    if l9 and l9.status == "degraded":
        confidence = min(confidence, 0.5)

    # L12 meta_consciousness: errors erode confidence
    l12 = by_key.get("meta_consciousness")
    if l12 and l12.signals_count > 3:
        confidence = max(0.2, confidence - l12.signals_count * 0.03)

    # ── Guardrails mode ───────────────────────────────────────
    guardrails_mode = "strict" if risk > 0.5 or mode == "degraded" else "normal"

    # ── Memory mode (L5/L6 freshness) ─────────────────────────
    l5 = by_key.get("memory_short")
    l6 = by_key.get("memory_long")
    if l6 and l6.freshness_score > 0.7:
        memory_mode = "long"
    elif l5 and l5.freshness_score < 0.3:
        memory_mode = "short"
    else:
        memory_mode = "balanced"

    # ── Voice mode ─────────────────────────────────────────────
    voice_mode = "on" if voice_enabled else "off"

    # ── Ops mode (L8) ─────────────────────────────────────────
    l8 = by_key.get("ops_awareness")
    ops_mode = "incident" if (l8 and l8.status in ("degraded", "error")) else "normal"

    return ConsciousnessState(
        mode=mode,
        fatigue_level=round(fatigue, 3),
        risk_level=round(risk, 3),
        confidence_level=round(confidence, 3),
        last_wake_ts=now,
        last_turn_ts=now,
        guardrails_mode=guardrails_mode,
        memory_mode=memory_mode,
        voice_mode=voice_mode,
        ops_mode=ops_mode,
    )
