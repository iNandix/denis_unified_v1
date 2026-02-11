"""Passive pattern detector for metagraph phase."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def detect_patterns(
    metrics_payload: dict[str, Any],
    hub_threshold: int = 100,
    orphan_warn_threshold: int = 10,
) -> dict[str, Any]:
    status = metrics_payload.get("status")
    if status != "ok":
        return {
            "status": "error",
            "timestamp_utc": _utc_now(),
            "error": "metrics_payload_not_ok",
            "source_status": status,
        }

    metrics = metrics_payload.get("metrics", {})
    top_hubs = metrics_payload.get("top_hubs", [])
    label_distribution = metrics_payload.get("label_distribution", [])

    patterns: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []
    proposals: list[dict[str, Any]] = []

    for row in top_hubs:
        degree = int(row.get("degree", 0))
        if degree >= hub_threshold:
            patterns.append(
                {
                    "type": "hub_node",
                    "node_ref": row.get("node_ref"),
                    "labels": row.get("labels", []),
                    "degree": degree,
                }
            )

    orphan_nodes = int(metrics.get("orphan_nodes", 0))
    if orphan_nodes > orphan_warn_threshold:
        anomalies.append(
            {
                "type": "orphan_pressure",
                "severity": "medium" if orphan_nodes <= 500 else "high",
                "value": orphan_nodes,
                "threshold": orphan_warn_threshold,
            }
        )
        proposals.append(
            {
                "action": "investigate_orphans",
                "mode": "read_only_proposal",
                "reason": f"{orphan_nodes} orphan nodes detected",
                "requires_human_approval": True,
            }
        )

    missing_timestamp_nodes = int(metrics.get("missing_timestamp_nodes", 0))
    if missing_timestamp_nodes > 0:
        anomalies.append(
            {
                "type": "missing_timestamp_nodes",
                "severity": "low" if missing_timestamp_nodes < 100 else "medium",
                "value": missing_timestamp_nodes,
            }
        )

    two_hop_cycles = int(metrics.get("two_hop_cycles", 0))
    if two_hop_cycles > 0:
        patterns.append(
            {
                "type": "short_cycles_detected",
                "count": two_hop_cycles,
            }
        )

    top_labels = label_distribution[:8] if isinstance(label_distribution, list) else []

    return {
        "status": "ok",
        "timestamp_utc": _utc_now(),
        "summary": {
            "patterns_count": len(patterns),
            "anomalies_count": len(anomalies),
            "proposals_count": len(proposals),
        },
        "patterns": patterns,
        "anomalies": anomalies,
        "proposals": proposals,
        "top_labels": top_labels,
    }

