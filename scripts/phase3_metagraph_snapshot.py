#!/usr/bin/env python3
"""Phase-3 metagraph snapshot (passive, read-only for graph structure)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from denis_unified_v1.metagraph.dashboard import persist_patterns_redis
from denis_unified_v1.metagraph.observer import collect_graph_metrics, persist_metrics_redis
from denis_unified_v1.metagraph.pattern_detector import detect_patterns


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run metagraph passive snapshot")
    parser.add_argument(
        "--out-json",
        default="/home/jotah/denis_unified_v1/phase3_metagraph_snapshot.json",
        help="Output json path",
    )
    parser.add_argument(
        "--persist-redis",
        action="store_true",
        help="Persist metrics/patterns to Redis keys (metagraph:*).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    metrics = collect_graph_metrics()
    patterns = detect_patterns(metrics)

    redis_status = {"status": "skipped"}
    if args.persist_redis:
        m = persist_metrics_redis(metrics)
        p = persist_patterns_redis(patterns)
        redis_status = {"metrics": m, "patterns": p}

    payload = {
        "status": "ok" if metrics.get("status") == "ok" else "error",
        "metrics": metrics,
        "patterns": patterns,
        "redis": redis_status,
    }

    out = Path(args.out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote json: {out}")
    print(json.dumps(payload, indent=2, sort_keys=True))

    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

