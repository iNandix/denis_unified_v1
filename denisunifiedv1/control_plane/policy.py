"""Control Plane Policy Engine - Release decision enforcement."""

from __future__ import annotations

import os
from typing import Any, Dict, List

from .registry import ControlPlaneRegistry


class PolicySpec:
    """Versioned policy specification."""

    def __init__(self, version: str = "cp_policy_v1"):
        self.version = version
        self.critical_modules = os.getenv("CP_CRITICAL_MODULES", "api,metacognitive,orchestrator").split(",")
        self.critical_modules = [m.strip() for m in self.critical_modules]

    def evaluate_releaseability(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate if system is releaseable based on snapshot."""
        degraded_reasons = snapshot.get("degraded_reasons", [])
        status = snapshot.get("status", "unknown")
        
        # Hard rules
        severity_5_count = sum(1 for rec in degraded_reasons if rec.get("severity") == 5)
        has_severity_5 = severity_5_count > 0
        
        critical_missing = any(
            rec.get("category") == "import" and 
            rec.get("reason") == "missing_module" and
            rec.get("evidence", {}).get("module") in self.critical_modules
            for rec in degraded_reasons
        )
        
        # Passed ratio (non-degraded components)
        total_tests = len(snapshot.get("category_counts", {}))
        if total_tests > 0:
            passed_ratio = 1.0 - (len(degraded_reasons) / total_tests)
        else:
            passed_ratio = 1.0
        
        # Decision
        releaseable = (
            not has_severity_5 and
            not critical_missing and
            passed_ratio >= 0.85
        )
        
        reasons = []
        if has_severity_5:
            reasons.append(f"severity_5_issues: {severity_5_count}")
        if critical_missing:
            reasons.append("critical_modules_missing")
        if passed_ratio < 0.85:
            reasons.append(".2f")
        
        return {
            "releaseable": releaseable,
            "policy_version": self.version,
            "reasons": reasons,
            "thresholds": {
                "passed_ratio_min": 0.85,
                "no_severity_5": True,
                "no_critical_missing": True,
            },
            "metrics": {
                "passed_ratio": passed_ratio,
                "severity_5_count": severity_5_count,
                "critical_missing": critical_missing,
                "total_degraded": len(degraded_reasons),
            }
        }


def get_control_plane_status() -> Dict[str, Any]:
    """Get complete control plane status."""
    registry = ControlPlaneRegistry()
    snapshot = registry.snapshot()
    policy = PolicySpec()
    policy_decision = policy.evaluate_releaseability(snapshot)
    
    return {
        "status": snapshot["status"],
        "releaseable": policy_decision["releaseable"],
        "policy_version": policy_decision["policy_version"],
        "policy_reasons": policy_decision["reasons"],
        "policy_thresholds": policy_decision["thresholds"],
        "policy_metrics": policy_decision["metrics"],
        "summary": {
            "total_degraded": snapshot["total_degraded"],
            "severity_counts": snapshot["severity_counts"],
            "category_counts": snapshot["category_counts"],
        },
        "degraded_reasons": snapshot["degraded_reasons"],
        "missing_optional_modules": snapshot["missing_optional_modules"],
        "timestamp_utc": snapshot["timestamp_utc"],
    }
