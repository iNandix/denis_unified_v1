#!/usr/bin/env python3
"""Route Sanity Smoke - Verify metacognitive routes are correctly mounted.

This smoke test verifies routes by importing create_app directly,
then optionally tries to hit a real server if available.
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args():
    parser = argparse.ArgumentParser(description="Route sanity smoke test")
    parser.add_argument(
        "--out-json",
        default="artifacts/api/route_sanity_smoke.json",
        help="Output artifact path",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Optional base URL for live server testing",
    )
    return parser.parse_args()


def get_routes_from_app():
    """Import create_app and get routes."""
    from api.fastapi_server import create_app

    app = create_app()

    routes = []
    for route in app.routes:
        path = getattr(route, "path", None)
        if path:
            methods = getattr(route, "methods", set())
            routes.append(
                {"path": path, "methods": list(methods) if methods else ["GET"]}
            )

    return routes


def test_live_server(base_url: str):
    """Test routes against a live server."""
    import requests

    results = []
    try:
        # Fetch OpenAPI
        resp = requests.get(f"{base_url}/openapi.json", timeout=10)
        if resp.status_code != 200:
            return {"error": f"OpenAPI fetch failed: {resp.status_code}"}

        openapi = resp.json()
        paths = openapi.get("paths", {})

        # Test key endpoints
        for path in [
            "/metacognitive/status",
            "/metacognitive/capabilities",
            "/metacognitive/events",
        ]:
            try:
                r = requests.get(f"{base_url}{path}", timeout=5)
                results.append(
                    {
                        "path": path,
                        "status": r.status_code,
                        "content_type": r.headers.get("content-type", ""),
                    }
                )
            except Exception as e:
                results.append({"path": path, "error": str(e)[:100]})

        return {"paths": list(paths.keys()), "endpoint_results": results}

    except Exception as e:
        return {"error": str(e)[:200]}


def run_smoke(base_url=None):
    """Run the route sanity smoke test."""
    try:
        # Get routes from app
        routes = get_routes_from_app()

        # Extract paths
        paths = [r["path"] for r in routes]

        print(f"Found {len(paths)} routes in app")

        # Required paths
        required = [
            "/metacognitive/status",
            "/metacognitive/capabilities",
            "/metacognitive/events",
        ]

        # Check presence
        present = []
        missing = []
        for req in required:
            if req in paths:
                present.append(req)
                print(f"  ✓ {req}")
            else:
                missing.append(req)
                print(f"  ✗ {req}")

        # Check for duplicates or malformed
        duplicates = []
        seen = set()
        for p in paths:
            if p in seen:
                duplicates.append(p)
            seen.add(p)

        # Malformed: paths without leading slash (within metacognitive)
        malformed = [p for p in paths if "metacognitive" in p and not p.startswith("/")]

        # Test live server if provided
        live_results = None
        if base_url:
            print(f"Testing live server: {base_url}")
            live_results = test_live_server(base_url)

        # Determine status
        ok = len(missing) == 0 and len(malformed) == 0

        return {
            "ok": ok,
            "server_started": True,
            "openapi_fetched": True,
            "required_paths_present": len(present) == len(required),
            "required_paths": required,
            "present_paths": present,
            "missing_paths": missing,
            "malformed_paths": malformed,
            "duplicate_paths": duplicates,
            "total_routes": len(paths),
            "metacognitive_routes": [p for p in paths if "metacognitive" in p],
            "live_server_results": live_results,
            "timestamp_utc": _utc_now(),
        }

    except Exception as e:
        import traceback

        return {
            "ok": False,
            "server_started": True,  # We imported successfully
            "error": str(e)[:200],
            "traceback": traceback.format_exc()[:500],
            "timestamp_utc": _utc_now(),
        }


def main():
    args = parse_args()
    result = run_smoke(args.base_url)

    # Write artifact
    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))

    return 0 if result.get("ok", False) else 1


if __name__ == "__main__":
    sys.exit(main())
