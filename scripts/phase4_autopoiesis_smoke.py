#!/usr/bin/env python3
"""Phase-4 autopoiesis supervised smoke script."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from denis_unified_v1.autopoiesis.dashboard import approve_proposal, list_proposals
from denis_unified_v1.autopoiesis.proposal_engine import generate_proposals
from denis_unified_v1.cortex.neo4j_config_resolver import ensure_neo4j_env_auto
from denis_unified_v1.feature_flags import load_feature_flags


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run phase-4 autopoiesis smoke")
    parser.add_argument(
        "--out-json",
        default="/home/jotah/denis_unified_v1/phase4_autopoiesis_smoke.json",
        help="Output json path",
    )
    parser.add_argument(
        "--approve-first",
        action="store_true",
        help="Approve first proposal after sandbox simulation.",
    )
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Skip generating new proposals and only list existing.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    flags = load_feature_flags().as_dict()

    payload: dict[str, Any] = {
        "status": "ok",
        "feature_flags": flags,
        "steps": [],
    }

    neo4j = ensure_neo4j_env_auto()
    payload["steps"].append({"step": "neo4j_env_auto", "result": neo4j})
    if neo4j.get("status") != "ok" and (os.getenv("DENIS_REQUIRE_NEO4J") or "").strip() in {
        "1",
        "true",
        "yes",
    }:
        payload["status"] = "error"

    if not args.no_refresh:
        generated = generate_proposals(persist_redis=True)
        payload["steps"].append({"step": "generate_proposals", "result": generated})
        if generated.get("status") != "ok":
            payload["status"] = "error"

    listed = list_proposals()
    payload["steps"].append({"step": "list_proposals", "result": listed})

    if args.approve_first:
        proposals = listed.get("proposals") or []
        if proposals:
            proposal_id = str(proposals[0].get("proposal_id", ""))
            if proposal_id:
                approved = approve_proposal(proposal_id)
                payload["steps"].append({"step": "approve_first", "result": approved})
                if approved.get("status") not in {"approved"}:
                    payload["status"] = "error"
        else:
            payload["steps"].append(
                {"step": "approve_first", "result": {"status": "skipped", "reason": "no_proposals"}}
            )

    out = Path(args.out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Wrote json: {out}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
