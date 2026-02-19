"""Persona frontdoor enforcement policies (WS15).

These helpers are intentionally tiny and side-effect free to avoid import cycles.
"""

from __future__ import annotations

import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    val = raw.strip().lower()
    if val in {"1", "true", "yes", "y", "on"}:
        return True
    if val in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def persona_frontdoor_enforced() -> bool:
    """Whether non-persona event emission is blocked."""
    return _env_bool("PERSONA_FRONTDOOR_ENFORCE", True)


def persona_bypass_mode() -> str:
    """How to react when a non-persona module calls the WS event bus directly.

    Values:
    - "raise": raise RuntimeError (dev/test)
    - "drop": log-safe and drop event (prod)
    """
    forced = (os.getenv("PERSONA_FRONTDOOR_BYPASS_MODE") or "").strip().lower()
    if forced in {"raise", "drop"}:
        return forced

    # Default: raise in tests / dev; drop in production.
    if os.getenv("PYTEST_CURRENT_TEST"):
        return "raise"

    env = (os.getenv("ENV") or os.getenv("DENIS_ENV") or "").strip().lower()
    if env in {"prod", "production"}:
        return "drop"
    if env in {"dev", "test", "local"}:
        return "raise"

    # Safe default: raise (catch bypass early).
    return "raise"

