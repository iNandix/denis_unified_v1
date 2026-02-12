#!/usr/bin/env python3
"""Phase-11 sprint orchestrator smoke."""
# ruff: noqa: E402

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from denis_unified_v1.sprint_orchestrator.config import load_sprint_config
from denis_unified_v1.sprint_orchestrator.model_adapter import build_provider_request
from denis_unified_v1.sprint_orchestrator.orchestrator import SprintOrchestrator
from denis_unified_v1.sprint_orchestrator.providers import (
    configured_provider_ids,
    load_provider_statuses,
    provider_status_map,
)
from denis_unified_v1.sprint_orchestrator.validation import resolve_target, run_validation_target


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run phase-11 sprint orchestrator smoke")
    parser.add_argument(
        "--out-json",
        default=str(PROJECT_ROOT / "denis_unified_v1" / "phase11_sprint_orchestrator_smoke.json"),
        help="Output json path",
    )
    return parser.parse_args()


def run_smoke() -> dict[str, Any]:
    os.environ.setdefault("DENIS_USE_SPRINT_ORCHESTRATOR", "true")

    config = load_sprint_config(PROJECT_ROOT / "denis_unified_v1")
    orchestrator = SprintOrchestrator(config)

    provider_statuses = load_provider_statuses(config)
    real_provider_ids = configured_provider_ids(provider_statuses)
    provider_map = provider_status_map(provider_statuses)

    projects = orchestrator.discover_projects(config.projects_scan_root)
    if not real_provider_ids:
        raise RuntimeError("No configured providers for phase11 smoke")
    session = orchestrator.create_session(
        prompt="fase11: arrancar sprint a/b, visualizar workers y ejecutar validacion preflight",
        workers=2,
        projects=projects,
        provider_pool=real_provider_ids,
    )

    orchestrator.emit(
        session_id=session.session_id,
        worker_id="worker-1",
        kind="worker.note",
        message="Implementando CLI terminal-first con filtro por worker",
    )

    preflight = run_validation_target(
        session_id=session.session_id,
        worker_id="worker-2",
        store=orchestrator.store,
        target=resolve_target(config.projects_scan_root, "preflight"),
    )

    adaptable = [
        item.provider
        for item in provider_statuses
        if item.provider in real_provider_ids
        and item.request_format in {"openai_chat", "anthropic_messages"}
    ]
    if not adaptable:
        raise RuntimeError("No adaptable API provider available for phase11 smoke")
    sample_provider = adaptable[0]
    adapted = build_provider_request(
        config=config,
        status=provider_map[sample_provider],
        messages=[{"role": "user", "content": "smoke payload adaptation"}],
    ).as_dict(redact_headers=True)

    events = orchestrator.store.read_events(session.session_id)
    checks = [
        {
            "check": "session_created",
            "ok": bool(session.session_id),
            "session_id": session.session_id,
        },
        {
            "check": "assignments_generated",
            "ok": len(session.assignments) == 2,
            "assignments": len(session.assignments),
        },
        {
            "check": "providers_configured",
            "ok": len(real_provider_ids) >= 1,
            "providers": real_provider_ids[:8],
        },
        {
            "check": "payload_adaptation",
            "ok": bool(adapted.get("payload")) and bool(adapted.get("endpoint")),
            "provider": sample_provider,
            "request_format": adapted.get("request_format"),
        },
        {
            "check": "events_logged",
            "ok": len(events) >= 4,
            "events": len(events),
        },
        {
            "check": "preflight_validation",
            "ok": preflight.get("status") == "ok",
            "preflight_status": preflight.get("status"),
            "duration_ms": preflight.get("duration_ms"),
        },
    ]

    status = "ok" if all(item["ok"] for item in checks) else "error"

    return {
        "status": status,
        "timestamp_utc": _utc_now(),
        "config": {
            "enabled": config.enabled,
            "scan_root": str(config.projects_scan_root),
            "state_dir": str(config.state_dir),
        },
        "session_id": session.session_id,
        "projects_count": len(projects),
        "providers_configured": real_provider_ids,
        "adapted_preview": adapted,
        "checks": checks,
        "preflight": preflight,
        "events_logged": len(events),
    }


def main() -> int:
    args = parse_args()
    payload = run_smoke()
    out = Path(args.out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote json: {out}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
