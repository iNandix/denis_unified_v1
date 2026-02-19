"""Wake and Update sequences for 12-layer neuroplasticity (WS23-G).

All operations fail-open: if graph is unreachable, return degraded defaults.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any, Callable

from denis_unified_v1.graph.graph_client import GraphClient, get_graph_client
from denis_unified_v1.neuro.state import (
    LAYER_DEFINITIONS,
    ConsciousnessState,
    NeuroLayerState,
    default_layers,
    derive_consciousness,
)

IDENTITY_ID = "identity:denis"
CONSCIOUSNESS_ID = "denis:consciousness"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()


# ── Wake Sequence ───────────────────────────────────────────────────

def wake_sequence(
    emit_fn: Callable[..., Any],
    conversation_id: str,
    *,
    graph: GraphClient | None = None,
) -> ConsciousnessState:
    """Execute WAKE_SEQUENCE: read/bootstrap 12 layers + derive consciousness.

    Synchronous. Fail-open.

    Args:
        emit_fn: callable(type, payload, **kwargs) for event emission.
        conversation_id: active conversation id.
        graph: optional GraphClient override (for testing).

    Returns:
        ConsciousnessState (derived or degraded defaults).
    """
    g = graph or get_graph_client()
    now = _utc_now_iso()

    # Emit wake start
    _safe_emit(emit_fn, conversation_id, "neuro.wake.start", {
        "ts": now,
        "identity_id": IDENTITY_ID,
    }, stored=True)

    # 1) Read existing layers from graph
    layers = _read_layers(g)
    consciousness = _read_consciousness(g)

    # 2) Bootstrap missing layers
    layers = _bootstrap_layers(g, layers)

    # 3) Bootstrap consciousness if missing
    voice_enabled = (os.getenv("PIPECAT_ENABLED") or "").strip().lower() in ("1", "true", "yes")
    ops_healthy = g.enabled and g._errors_window < 5

    consciousness = derive_consciousness(
        layers,
        ops_healthy=ops_healthy,
        voice_enabled=voice_enabled,
        active_plans=False,
        graph_up=g.enabled,
    )
    consciousness.last_wake_ts = now
    consciousness.last_turn_ts = now

    # Write consciousness to graph
    _write_consciousness(g, consciousness)

    # Link identity -> layers + consciousness
    _link_all(g, layers)

    # 4) Emit snapshots
    for layer in layers:
        _safe_emit(emit_fn, conversation_id, "neuro.layer.snapshot", {
            "layer_index": layer.layer_index,
            "layer_key": layer.layer_key,
            "title": layer.title,
            "freshness_score": layer.freshness_score,
            "status": layer.status,
            "signals_count": layer.signals_count,
            "last_update_ts": layer.last_update_ts,
        }, stored=False)

    _safe_emit(emit_fn, conversation_id, "neuro.consciousness.snapshot", {
        **consciousness.to_dict(),
        "ts": now,
    }, stored=True)

    _safe_emit(emit_fn, conversation_id, "persona.state.update", {
        "mode": consciousness.mode,
        "ts": now,
    }, stored=False)

    return consciousness


# ── Update Sequence (per-turn) ──────────────────────────────────────

def update_sequence(
    emit_fn: Callable[..., Any],
    conversation_id: str,
    turn_meta: dict[str, Any],
    *,
    graph: GraphClient | None = None,
) -> ConsciousnessState:
    """Execute UPDATE_SEQUENCE: update layers + re-derive consciousness.

    Synchronous. Fail-open.

    Args:
        emit_fn: callable for event emission.
        conversation_id: active conversation id.
        turn_meta: dict with turn metadata:
            - input_sha256, input_len, modality (L1)
            - focus_topic_hash (L2)
            - intent_hash, constraints_hit (L3)
            - active_plan_ids, plan_progress (L4)
            - turns_in_session (L5)
            - retrieval_count, chunk_ids_count (L6)
            - guardrail_triggers, risk_signals (L7)
            - ops_degraded (L8)
            - tone, verbosity (L9)
            - contradiction_count (L10)
            - changed_components_count (L11)
            - errors_count (L12 input)
        graph: optional GraphClient override.

    Returns:
        ConsciousnessState (updated).
    """
    g = graph or get_graph_client()
    now = _utc_now_iso()

    # Read current layers (or defaults)
    layers = _read_layers(g)
    if not layers:
        layers = default_layers()

    # Apply turn updates to each layer
    _apply_turn_updates(layers, turn_meta, now)

    # Write updated layers to graph
    for layer in layers:
        g.upsert_neuro_layer(
            layer_id=layer.id,
            props=layer.to_dict(),
        )

    # Re-derive consciousness
    voice_enabled = (os.getenv("PIPECAT_ENABLED") or "").strip().lower() in ("1", "true", "yes")
    ops_healthy = not turn_meta.get("ops_degraded", False) and g._errors_window < 5
    active_plans = bool(turn_meta.get("active_plan_ids"))

    consciousness = derive_consciousness(
        layers,
        ops_healthy=ops_healthy,
        voice_enabled=voice_enabled,
        active_plans=active_plans,
        graph_up=g.enabled,
    )
    consciousness.last_turn_ts = now

    # Preserve last_wake_ts from graph
    existing_cs = _read_consciousness(g)
    if existing_cs and existing_cs.get("last_wake_ts"):
        consciousness.last_wake_ts = existing_cs["last_wake_ts"]

    _write_consciousness(g, consciousness)

    # Emit turn update events
    _safe_emit(emit_fn, conversation_id, "neuro.turn.update", {
        "layers_summary": [
            {
                "layer_index": l.layer_index,
                "layer_key": l.layer_key,
                "freshness_score": l.freshness_score,
                "status": l.status,
                "signals_count": l.signals_count,
            }
            for l in layers
        ],
        "ts": now,
    }, stored=True)

    _safe_emit(emit_fn, conversation_id, "neuro.consciousness.update", {
        **consciousness.to_dict(),
        "ts": now,
    }, stored=True)

    _safe_emit(emit_fn, conversation_id, "persona.state.update", {
        "mode": consciousness.mode,
        "ts": now,
    }, stored=False)

    return consciousness


# ── Internals ───────────────────────────────────────────────────────

def _read_layers(g: GraphClient) -> list[NeuroLayerState]:
    """Read 12 NeuroLayer nodes from graph. Fail-open -> []."""
    rows = g.run_read(
        """
        MATCH (i:Identity {id: $iid})-[:HAS_NEURO_LAYER]->(n:NeuroLayer)
        RETURN n.id AS id, n.layer_index AS layer_index, n.layer_key AS layer_key,
               n.title AS title, n.freshness_score AS freshness_score,
               n.status AS status, n.signals_count AS signals_count,
               n.last_update_ts AS last_update_ts, n.notes_hash AS notes_hash
        ORDER BY n.layer_index
        """,
        {"iid": IDENTITY_ID},
    )
    if not rows:
        return []
    result = []
    for r in rows:
        result.append(NeuroLayerState(
            layer_index=int(r.get("layer_index") or 0),
            layer_key=str(r.get("layer_key") or ""),
            title=str(r.get("title") or ""),
            freshness_score=float(r.get("freshness_score") or 0.5),
            status=str(r.get("status") or "ok"),
            signals_count=int(r.get("signals_count") or 0),
            last_update_ts=str(r.get("last_update_ts") or ""),
            notes_hash=str(r.get("notes_hash") or ""),
        ))
    return result


def _read_consciousness(g: GraphClient) -> dict[str, Any] | None:
    """Read ConsciousnessState from graph. Fail-open -> None."""
    rows = g.run_read(
        """
        MATCH (c:ConsciousnessState {id: $cid})
        RETURN c {.*} AS state
        """,
        {"cid": CONSCIOUSNESS_ID},
    )
    if not rows:
        return None
    return dict(rows[0].get("state") or {})


def _bootstrap_layers(g: GraphClient, existing: list[NeuroLayerState]) -> list[NeuroLayerState]:
    """Ensure all 12 layers exist; create missing ones with defaults."""
    existing_indices = {l.layer_index for l in existing}
    defaults = default_layers()
    merged = list(existing)

    for dl in defaults:
        if dl.layer_index not in existing_indices:
            g.upsert_neuro_layer(layer_id=dl.id, props=dl.to_dict())
            merged.append(dl)

    merged.sort(key=lambda l: l.layer_index)
    return merged


def _write_consciousness(g: GraphClient, cs: ConsciousnessState) -> None:
    """Write ConsciousnessState to graph."""
    g.upsert_consciousness_state(state_id=CONSCIOUSNESS_ID, props=cs.to_dict())


def _link_all(g: GraphClient, layers: list[NeuroLayerState]) -> None:
    """Link Identity -> NeuroLayers + ConsciousnessState, ConsciousnessState -> layers."""
    for layer in layers:
        g.link_identity_neuro_layer(identity_id=IDENTITY_ID, layer_id=layer.id)
        g.link_consciousness_layer(state_id=CONSCIOUSNESS_ID, layer_id=layer.id)
    g.link_identity_consciousness(identity_id=IDENTITY_ID, state_id=CONSCIOUSNESS_ID)


def _apply_turn_updates(
    layers: list[NeuroLayerState],
    meta: dict[str, Any],
    now: str,
) -> None:
    """Mutate layer states in place based on turn metadata."""
    by_key: dict[str, NeuroLayerState] = {l.layer_key: l for l in layers}

    def _touch(key: str, signals: int = 0, fresh: float | None = None) -> None:
        layer = by_key.get(key)
        if not layer:
            return
        layer.last_update_ts = now
        layer.signals_count += max(0, signals)
        if fresh is not None:
            layer.freshness_score = max(0.0, min(1.0, fresh))
        else:
            # Mild freshness boost on any touch
            layer.freshness_score = min(1.0, layer.freshness_score + 0.1)

    # L1: Sensory/IO — always touched on turn
    _touch("sensory_io", signals=1, fresh=1.0)

    # L2: Attention
    if meta.get("focus_topic_hash"):
        _touch("attention", signals=1, fresh=0.9)

    # L3: Intent/Goals
    if meta.get("intent_hash"):
        constraints_hit = len(meta.get("constraints_hit") or [])
        _touch("intent_goals", signals=1 + constraints_hit, fresh=0.85)

    # L4: Plans/Procedures
    if meta.get("active_plan_ids"):
        progress = float(meta.get("plan_progress") or 0.5)
        _touch("plans_procedures", signals=len(meta["active_plan_ids"]), fresh=progress)

    # L5: Memory Short — freshness based on recency
    turns = int(meta.get("turns_in_session") or 1)
    short_fresh = max(0.3, 1.0 - (turns - 1) * 0.05)
    _touch("memory_short", signals=1, fresh=short_fresh)

    # L6: Memory Long — retrieval stats
    retrieval_count = int(meta.get("retrieval_count") or 0)
    if retrieval_count > 0:
        _touch("memory_long", signals=retrieval_count, fresh=0.8)

    # L7: Safety/Governance
    risk_signals = int(meta.get("risk_signals") or 0)
    guardrail_triggers = int(meta.get("guardrail_triggers") or 0)
    if risk_signals > 0 or guardrail_triggers > 0:
        l7 = by_key.get("safety_governance")
        if l7:
            _touch("safety_governance", signals=risk_signals + guardrail_triggers)
            if guardrail_triggers > 2:
                l7.status = "degraded"
    else:
        _touch("safety_governance", fresh=0.9)

    # L8: Ops Awareness
    if meta.get("ops_degraded"):
        l8 = by_key.get("ops_awareness")
        if l8:
            l8.status = "degraded"
            l8.last_update_ts = now
            l8.freshness_score = 0.3
    else:
        _touch("ops_awareness", fresh=0.9)

    # L9: Social/Persona — tone adjustments
    _touch("social_persona", signals=1)

    # L10: Self-Monitoring — contradictions
    contradiction_count = int(meta.get("contradiction_count") or 0)
    if contradiction_count > 0:
        _touch("self_monitoring", signals=contradiction_count, fresh=0.5)
    else:
        _touch("self_monitoring", fresh=0.9)

    # L11: Learning/Plasticity — component changes
    changed = int(meta.get("changed_components_count") or 0)
    if changed > 0:
        _touch("learning_plasticity", signals=changed, fresh=0.8)

    # L12: Meta/Consciousness — errors feed into this
    errors = int(meta.get("errors_count") or 0)
    if errors > 0:
        _touch("meta_consciousness", signals=errors, fresh=0.5)
    else:
        _touch("meta_consciousness", fresh=0.9)


def _safe_emit(
    emit_fn: Callable[..., Any],
    conversation_id: str,
    event_type: str,
    payload: dict[str, Any],
    *,
    stored: bool = True,
) -> None:
    """Emit event via emit_fn, swallowing errors (fail-open)."""
    try:
        emit_fn(
            event_type=event_type,
            payload=payload,
            conversation_id=conversation_id,
            stored=stored,
            severity="info",
        )
    except Exception:
        pass
