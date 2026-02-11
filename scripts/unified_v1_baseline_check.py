#!/usr/bin/env python3
"""Phase-0 baseline check for DENIS unified incremental refactor."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_ENDPOINTS = [
    "http://127.0.0.1:8084/health",
    "http://127.0.0.1:9999/health",
    "http://127.0.0.1:8086/health",
    "http://127.0.0.1:8000/health",
]
DEFAULT_PORTS = [8084, 9999, 8086, 9100, 8000]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_csv_env(name: str, fallback: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return fallback
    values = [x.strip() for x in raw.split(",")]
    return [x for x in values if x]


def _check_ports(ports: list[int]) -> dict[str, object]:
    cmd = ["ss", "-tlnp"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    lines = proc.stdout.splitlines()
    open_ports: list[int] = []
    for line in lines:
        for port in ports:
            if f":{port} " in line or f":{port}\n" in line:
                open_ports.append(port)
    return {
        "command": " ".join(cmd),
        "exit_code": proc.returncode,
        "requested_ports": ports,
        "open_ports": sorted(set(open_ports)),
    }


def _fetch_health(url: str, timeout_sec: float = 4.0) -> dict[str, object]:
    result: dict[str, object] = {
        "url": url,
        "ok": False,
        "status_code": None,
        "latency_ms": None,
        "body_preview": "",
        "error": None,
    }
    start = datetime.now(timezone.utc)
    cmd = [
        "curl",
        "-sS",
        "-m",
        str(timeout_sec),
        "-w",
        "\\n%{http_code}",
        url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    delta = datetime.now(timezone.utc) - start
    result["latency_ms"] = int(delta.total_seconds() * 1000)

    if proc.returncode != 0:
        result["error"] = (proc.stderr or "").strip() or "curl failed"
        return result

    payload = proc.stdout or ""
    if "\n" not in payload:
        result["error"] = "invalid curl output"
        return result

    body, code = payload.rsplit("\n", 1)
    try:
        status_code = int(code.strip())
    except ValueError:
        result["error"] = f"invalid status code: {code.strip()}"
        return result

    result["status_code"] = status_code
    result["ok"] = 200 <= status_code < 300
    result["body_preview"] = body[:300]
    return result


def _build_markdown(report: dict[str, object]) -> str:
    lines: list[str] = []
    lines.append("# DENIS Baseline (Phase 0)")
    lines.append("")
    lines.append(f"- Timestamp (UTC): `{report['timestamp_utc']}`")
    lines.append(f"- Host: `{report['host']}`")
    lines.append("")
    lines.append("## Ports")
    ports = report["ports"]
    lines.append(f"- Command: `{ports['command']}`")
    lines.append(f"- Requested: `{ports['requested_ports']}`")
    lines.append(f"- Open: `{ports['open_ports']}`")
    lines.append("")
    lines.append("## Health Endpoints")
    for item in report["health"]:
        state = "ok" if item["ok"] else "error"
        lines.append(
            f"- `{item['url']}` -> `{state}` "
            f"(status={item['status_code']}, latency_ms={item['latency_ms']})"
        )
        if item["error"]:
            lines.append(f"  error: `{item['error']}`")
    lines.append("")
    lines.append("## Feature Flags Default")
    for key, value in report["phase0_feature_flags"].items():
        lines.append(f"- `{key}={value}`")
    lines.append("")
    return "\n".join(lines)


def run(endpoints: list[str], ports: list[int]) -> dict[str, object]:
    from denis_unified_v1.feature_flags import load_feature_flags

    return {
        "timestamp_utc": _utc_now(),
        "host": os.uname().nodename,
        "ports": _check_ports(ports),
        "health": [_fetch_health(url) for url in endpoints],
        "phase0_feature_flags": load_feature_flags().as_dict(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate phase-0 baseline report")
    parser.add_argument(
        "--out-md",
        default="DENIS_BASELINE.md",
        help="Output markdown report path",
    )
    parser.add_argument(
        "--out-json",
        default="baseline_report.json",
        help="Output json report path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    endpoint_values = _parse_csv_env("DENIS_BASELINE_ENDPOINTS", DEFAULT_ENDPOINTS)
    port_values = [
        int(x)
        for x in _parse_csv_env("DENIS_BASELINE_PORTS", [str(p) for p in DEFAULT_PORTS])
    ]

    report = run(endpoint_values, port_values)
    markdown = _build_markdown(report)

    os.makedirs(os.path.dirname(args.out_md) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(args.out_json) or ".", exist_ok=True)
    with open(args.out_md, "w", encoding="utf-8") as f_md:
        f_md.write(markdown)
    with open(args.out_json, "w", encoding="utf-8") as f_json:
        json.dump(report, f_json, indent=2, sort_keys=True)

    print(f"Wrote markdown: {args.out_md}")
    print(f"Wrote json: {args.out_json}")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
