"""Legacy namespace shim for orchestration."""

import time

try:
    from denisunifiedv1.orchestration import *
    # Record OK if import succeeds
    try:
        from denisunifiedv1.control_plane.registry import get_control_plane_registry
        registry = get_control_plane_registry()
        registry.record_ok("orchestration", {"shim": "direct_import"})
    except Exception:
        pass
except Exception:
    # Record degradation
    try:
        from denisunifiedv1.control_plane.registry import get_control_plane_registry, DegradationRecord
        registry = get_control_plane_registry()
        registry.record_degraded(DegradationRecord(
            id="shim.orchestration.active",
            component="orchestration",
            severity=2,
            category="shim",
            reason="noop_shim_active",
            evidence={"shim": "orchestration", "target": "denisunifiedv1.orchestration"},
            first_seen_utc=time.time(),
            last_seen_utc=time.time(),
            count=1,
        ))
    except Exception:
        pass
