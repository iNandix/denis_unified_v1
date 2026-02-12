#!/usr/bin/env python3
"""Build sprint review pack and checkpoint decision from validation JSON files."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "error", "error": f"read_failed:{exc}", "_missing_or_invalid": True}


def _status_ok(payload: dict[str, Any]) -> bool:
    return str(payload.get("status", "")).lower() == "ok"


def _decision(preflight_ok: bool, pentest_ok: bool, smoke_ok: bool) -> str:
    if preflight_ok and pentest_ok and smoke_ok:
        return "GO"
    if preflight_ok and pentest_ok and not smoke_ok:
        return "GO_WITH_FIXES"
    return "NO_GO"


def _render_md(summary: dict[str, Any]) -> str:
    checks = summary["checks"]
    lines = [
        "# Sprint Review Pack",
        "",
        f"- Generated UTC: `{summary['generated_utc']}`",
        f"- Decision: `{summary['decision']}`",
        "",
        "## Checks",
        f"- Preflight: `{checks['preflight']['status']}`",
        f"- Gate pentest: `{checks['pentest']['status']}`",
        f"- Autopoiesis smoke: `{checks['smoke']['status']}`",
        "",
        "## Details",
        f"- Pentest failed checks: `{checks['pentest']['failed_checks']}`",
        f"- Preflight missing tools: `{checks['preflight']['missing_tools']}`",
        "",
    ]
    if summary["errors"]:
        lines.append("## Errors")
        for err in summary["errors"]:
            lines.append(f"- {err}")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build sprint review pack")
    parser.add_argument("--preflight", default="phase10_gate_preflight.json")
    parser.add_argument("--smoke", default="phase4_autopoiesis_smoke.json")
    parser.add_argument("--pentest", default="phase10_gate_pentest.json")
    parser.add_argument("--out-json", default="sprint_review.json")
    parser.add_argument("--out-md", default="sprint_review.md")
    parser.add_argument(
        "--require-go",
        action="store_true",
        help="Exit non-zero if decision is not GO",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    preflight_path = Path(args.preflight)
    smoke_path = Path(args.smoke)
    pentest_path = Path(args.pentest)

    preflight = _read_json(preflight_path)
    smoke = _read_json(smoke_path)
    pentest = _read_json(pentest_path)

    preflight_ok = _status_ok(preflight)
    smoke_ok = _status_ok(smoke)
    pentest_failed = int((pentest.get("summary") or {}).get("failed") or 0)
    pentest_ok = _status_ok(pentest) and pentest_failed == 0

    errors: list[str] = []
    if preflight.get("_missing_or_invalid"):
        errors.append(f"preflight_invalid:{preflight_path}")
    if smoke.get("_missing_or_invalid"):
        errors.append(f"smoke_invalid:{smoke_path}")
    if pentest.get("_missing_or_invalid"):
        errors.append(f"pentest_invalid:{pentest_path}")
    if not preflight_ok:
        errors.append("preflight_not_ok")
    if not pentest_ok:
        errors.append("pentest_not_ok")
    if not smoke_ok:
        errors.append("smoke_not_ok")

    decision = _decision(preflight_ok=preflight_ok, pentest_ok=pentest_ok, smoke_ok=smoke_ok)

    summary: dict[str, Any] = {
        "generated_utc": _utc_now(),
        "decision": decision,
        "checks": {
            "preflight": {
                "file": str(preflight_path),
                "status": preflight.get("status", "error"),
                "missing_tools": (preflight.get("summary") or {}).get("missing_tools", []),
            },
            "pentest": {
                "file": str(pentest_path),
                "status": pentest.get("status", "error"),
                "failed_checks": pentest_failed,
                "total_checks": int((pentest.get("summary") or {}).get("total") or 0),
            },
            "smoke": {
                "file": str(smoke_path),
                "status": smoke.get("status", "error"),
            },
        },
        "errors": errors,
    }

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    out_md.write_text(_render_md(summary), encoding="utf-8")

    print(f"Wrote json: {out_json}")
    print(f"Wrote md: {out_md}")
    print(json.dumps(summary, indent=2, sort_keys=True))

    if args.require_go and decision != "GO":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
