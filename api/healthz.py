"""Healthz endpoint for DENIS 8084 - Brain visibility.

Provides visibility into:
- Version / git sha
- Internet status
- Allow boosters
- Registry hash
- Engine list (id + tags + sanitized endpoint)
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])


def _get_git_sha() -> str:
    """Get current git commit sha."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(__file__),
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _get_registry_hash(registry: dict) -> str:
    """Compute hash of engine registry for change detection."""
    try:
        # Sort keys for deterministic hash
        registry_str = str(sorted(registry.items()))
        return hashlib.sha256(registry_str.encode()).hexdigest()[:16]
    except Exception:
        return "unknown"


def _sanitize_endpoint(endpoint: str) -> str:
    """Sanitize endpoint for display (hide sensitive parts)."""
    if not endpoint:
        return ""

    # Hide API keys in URLs
    if "api_key=" in endpoint or "key=" in endpoint:
        parts = endpoint.split("?")
        base = parts[0]
        return f"{base}?<api_key_hidden>"

    # Hide auth in URLs
    if "://" in endpoint:
        protocol, rest = endpoint.split("://", 1)
        if "@" in rest:
            # Has credentials
            creds, host = rest.split("@", 1)
            return f"{protocol}://<credentials>@{host}"

    return endpoint


@router.get("/healthz")
async def healthz(request: Request) -> dict[str, Any]:
    """
    Health check with brain visibility.

    Returns:
        - version: Current version
        - git_sha: Git commit sha
        - internet_status: OK/DOWN/UNKNOWN
        - allow_boosters: Whether boosters are allowed
        - registry_hash: Hash of engine registry
        - engines: List of configured engines
        - timestamp: ISO timestamp
    """
    # Import here to avoid circular dependencies
    from denis_unified_v1.kernel.engine_registry import get_engine_registry
    from denis_unified_v1.kernel.internet_health import get_internet_health
    from denis_unified_v1.kernel.scheduler import get_model_scheduler

    # Get internet status
    internet_health = get_internet_health()
    internet_status = internet_health.check()
    allow_boosters = internet_health.allow_boosters()

    # Get registry info
    registry = get_engine_registry()
    registry_hash = _get_registry_hash(registry)

    # Build engine list
    engines = []
    for engine_id, engine_info in registry.items():
        engines.append(
            {
                "id": engine_id,
                "tags": engine_info.get("tags", []),
                "endpoint": _sanitize_endpoint(engine_info.get("endpoint", "")),
                "provider": engine_info.get("provider_key", "unknown"),
                "model": engine_info.get("model", "unknown"),
                "priority": engine_info.get("priority", 50),
            }
        )

    # Sort by priority
    engines.sort(key=lambda e: e["priority"])

    # Get scheduler stats
    scheduler = get_model_scheduler()
    scheduler_stats = scheduler.get_stats()

    return {
        "status": "healthy",
        "version": "unified-v1",
        "git_sha": _get_git_sha(),
        "internet_status": internet_status,
        "allow_boosters": allow_boosters,
        "registry_hash": registry_hash,
        "engines": engines,
        "engines_count": len(engines),
        "scheduler": {
            "total_engines": scheduler_stats.get("total_engines", 0),
            "available_engines": scheduler_stats.get("available_engines", 0),
            "active_requests": scheduler_stats.get("active_requests", 0),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health")
async def health_simple() -> dict[str, str]:
    """Simple health check for load balancers."""
    return {"status": "ok"}
