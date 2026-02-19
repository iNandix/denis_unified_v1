#!/usr/bin/env python3
"""WS23-G Neuro smoke test — validates /neuro/wake + /neuro/state endpoints.

Usage:
    python scripts/neuro_smoke.py [base_url]

Default base_url: http://127.0.0.1:8000
"""

import json
import sys

import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def _ok(label: str, data: dict) -> None:
    mode = data.get("consciousness", {}).get("mode") or data.get("status")
    print(f"  OK  {label}: status={data.get('status')}, mode={mode}")


def _fail(label: str, msg: str) -> None:
    print(f"  FAIL  {label}: {msg}")
    sys.exit(1)


def main() -> None:
    print(f"WS23-G Neuro Smoke — {BASE}")
    print()

    # 1) POST /neuro/wake
    print("[1] POST /neuro/wake")
    try:
        r = requests.post(f"{BASE}/neuro/wake", timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("status") in ("ok", "degraded"):
            _ok("/neuro/wake", data)
        else:
            _fail("/neuro/wake", f"unexpected status: {data.get('status')}")
    except Exception as e:
        _fail("/neuro/wake", str(e))

    # 2) GET /neuro/state
    print("[2] GET /neuro/state")
    try:
        r = requests.get(f"{BASE}/neuro/state", timeout=10)
        r.raise_for_status()
        data = r.json()
        layers = data.get("layers", [])
        if len(layers) == 12:
            _ok("/neuro/state", data)
            print(f"       layers: {len(layers)}")
            for l in layers:
                print(
                    f"         L{l.get('layer_index', '?'):>2} "
                    f"{l.get('layer_key', '?'):<24} "
                    f"fresh={l.get('freshness_score', '?')} "
                    f"status={l.get('status', '?')} "
                    f"signals={l.get('signals_count', '?')}"
                )
        elif data.get("status") == "degraded":
            _ok("/neuro/state (degraded)", data)
        else:
            _fail("/neuro/state", f"expected 12 layers, got {len(layers)}")
    except Exception as e:
        _fail("/neuro/state", str(e))

    # 3) GET /health — verify neuro router loaded
    print("[3] GET /health")
    try:
        r = requests.get(f"{BASE}/health", timeout=5)
        _ok("/health", r.json())
    except Exception as e:
        _fail("/health", str(e))

    print()
    print("WS23-G Neuro Smoke PASSED")


if __name__ == "__main__":
    main()
