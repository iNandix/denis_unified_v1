"""Control Plane Degradation Registry - Track all bypasses and degradations."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
from threading import RLock


@dataclass
class DegradationRecord:
    """Structured degradation record."""
    id: str
    component: str
    severity: int  # 1-5
    category: str  # import, shim, backend, schema, smoke, gate, graph
    reason: str  # missing_module, import_error, noop_shim_active, backend_unreachable, etc.
    evidence: Dict[str, Any]
    first_seen_utc: float
    last_seen_utc: float
    count: int
    suggested_remediation_key: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DegradationRecord:
        return cls(**data)


class ControlPlaneRegistry:
    """Central registry for all system degradations."""

    def __init__(self, persistence_path: Optional[Path] = None):
        self.persistence_path = persistence_path or Path("artifacts/control_plane/registry_snapshot.json")
        self._records: Dict[str, DegradationRecord] = {}
        self._lock = RLock()
        self._load_snapshot()

    def record_degraded(self, record: DegradationRecord) -> None:
        """Record a degradation event."""
        with self._lock:
            record_id = record.id
            if record_id in self._records:
                # Update existing record
                existing = self._records[record_id]
                existing.last_seen_utc = time.time()
                existing.count += 1
                # Update evidence if more recent
                if record.evidence:
                    existing.evidence.update(record.evidence)
            else:
                # New record
                record.first_seen_utc = record.first_seen_utc or time.time()
                record.last_seen_utc = record.last_seen_utc or record.first_seen_utc
                record.count = record.count or 1
                self._records[record_id] = record
            self._save_snapshot()

    def record_ok(self, component: str, details: Dict[str, Any]) -> None:
        """Record that a component is OK (clears any degradation)."""
        with self._lock:
            # Remove any degradation records for this component
            to_remove = [rid for rid, rec in self._records.items() if rec.component == component]
            for rid in to_remove:
                del self._records[rid]
            self._save_snapshot()

    def snapshot(self) -> Dict[str, Any]:
        """Get current registry snapshot."""
        with self._lock:
            records = [rec.to_dict() for rec in self._records.values()]
            
            # Summary stats
            total_degraded = len(records)
            severity_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
            category_counts = {}
            
            for rec in records:
                severity_counts[rec['severity']] = severity_counts.get(rec['severity'], 0) + 1
                category_counts[rec['category']] = category_counts.get(rec['category'], 0) + 1
            
            # Missing optional modules (derived)
            missing_modules = [
                rec['evidence'].get('module', rec['id']) 
                for rec in records 
                if rec['category'] == 'import' and rec['reason'] == 'missing_module'
            ]
            
            # Health summary
            critical_issues = sum(severity_counts.get(s, 0) for s in [4, 5])
            health_status = "failed" if critical_issues > 0 else "degraded" if total_degraded > 0 else "ok"
            
            return {
                "status": health_status,
                "total_degraded": total_degraded,
                "severity_counts": severity_counts,
                "category_counts": category_counts,
                "degraded_reasons": records,
                "missing_optional_modules": missing_modules,
                "timestamp_utc": time.time(),
            }

    def _load_snapshot(self) -> None:
        """Load persisted snapshot."""
        try:
            if self.persistence_path.exists():
                with self.persistence_path.open() as f:
                    data = json.load(f)
                    for rec_data in data.get("degraded_reasons", []):
                        rec = DegradationRecord.from_dict(rec_data)
                        self._records[rec.id] = rec
        except Exception:
            # Fail-open: start fresh
            pass

    def _save_snapshot(self) -> None:
        """Save current snapshot."""
        try:
            with self._lock:
                records = [rec.to_dict() for rec in self._records.values()]
                # Build snapshot without holding the lock for IO
                snapshot = {
                    "status": "degraded" if records else "ok",
                    "total_degraded": len(records),
                    "severity_counts": {},
                    "category_counts": {},
                    "degraded_reasons": records,
                    "missing_optional_modules": [
                        rec.get("evidence", {}).get("module", rec.get("id"))
                        for rec in records
                        if rec.get("category") == "import" and rec.get("reason") == "missing_module"
                    ],
                    "timestamp_utc": time.time(),
                }
            self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
            with self.persistence_path.open("w") as f:
                json.dump(snapshot, f, indent=2)
        except Exception:
            # Fail-open: don't crash on persistence failure
            pass


# Global registry instance
_registry = None

def get_control_plane_registry() -> ControlPlaneRegistry:
    """Get the global control plane registry instance."""
    global _registry
    if _registry is None:
        _registry = ControlPlaneRegistry()
    return _registry
