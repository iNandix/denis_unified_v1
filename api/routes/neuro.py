"""WS23-G Neuro API — /neuro/state + /neuro/wake (fail-open, read from Graph SSoT)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["neuro"])


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/neuro/state")
async def neuro_state() -> dict[str, Any]:
    """Read 12 NeuroLayers + ConsciousnessState from Graph SSoT."""
    try:
        from denis_unified_v1.feature_flags import load_feature_flags

        flags = load_feature_flags()
        if not getattr(flags, "neuro_enabled", True):
            return {
                "status": "disabled",
                "ts": _utc_now_iso(),
                "layers": [],
                "consciousness": None,
            }
    except Exception:
        pass

    try:
        from denis_unified_v1.graph.graph_client import get_graph_client
        from denis_unified_v1.neuro.sequences import _read_layers, _read_consciousness

        g = get_graph_client()

        layers = _read_layers(g)
        consciousness = _read_consciousness(g)

        if not layers:
            from denis_unified_v1.neuro.state import default_layers

            layers = default_layers()

        return {
            "status": "ok" if layers else "no_data",
            "ts": _utc_now_iso(),
            "layers": [l.to_dict() for l in layers],
            "consciousness": consciousness or {},
        }
    except Exception as e:
        logger.warning(f"neuro_state failed (degraded): {e}")
        return {
            "status": "degraded",
            "ts": _utc_now_iso(),
            "layers": [],
            "consciousness": None,
            "error": str(e)[:200],
        }


@router.post("/neuro/wake")
async def neuro_wake() -> dict[str, Any]:
    """Trigger WAKE_SEQUENCE: bootstrap/refresh 12 layers + derive consciousness."""
    try:
        from denis_unified_v1.feature_flags import load_feature_flags

        flags = load_feature_flags()
        if not getattr(flags, "neuro_enabled", True):
            return {
                "status": "disabled",
                "ts": _utc_now_iso(),
                "consciousness": None,
            }
    except Exception:
        pass

    try:
        from api.event_bus import emit_event, persona_emitter_context
        from denis_unified_v1.neuro.sequences import wake_sequence

        with persona_emitter_context():
            cs = wake_sequence(
                emit_fn=emit_event,
                conversation_id="neuro_wake",
            )

        return {
            "status": "ok",
            "ts": _utc_now_iso(),
            "consciousness": cs.to_dict(),
        }
    except Exception as e:
        logger.warning(f"neuro_wake failed (degraded): {e}")
        return {
            "status": "degraded",
            "ts": _utc_now_iso(),
            "consciousness": None,
            "error": str(e)[:200],
        }
