"""Compat shim for feature flags.

Exports load_feature_flags / load_featureflags delegating to feature_flags.py
(legacy name) to enable fail-open imports when feature_flags is optional.
"""
from __future__ import annotations

import time

try:
    from feature_flags import load_feature_flags as _load
except Exception:  # pragma: no cover - fail-open
    def _load():
        # Record degradation
        try:
            from denisunifiedv1.control_plane.registry import get_control_plane_registry, DegradationRecord
            registry = get_control_plane_registry()
            registry.record_degraded(DegradationRecord(
                id="import.feature_flags.missing",
                component="featureflags",
                severity=2,
                category="import",
                reason="missing_module",
                evidence={"module": "feature_flags", "fallback": "empty dict"},
                first_seen_utc=time.time(),
                last_seen_utc=time.time(),
                count=1,
                suggested_remediation_key="install_feature_flags",
            ))
        except Exception:
            pass  # Fail-open even for recording
        return {}


def load_feature_flags():
    return _load()


def load_featureflags():  # alias
    return _load()
