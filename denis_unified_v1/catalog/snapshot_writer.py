"""Snapshot writer for catalog lookups - P1.3 telemetry."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone

from denis_unified_v1.catalog.schemas_v1 import LookupResultV1


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_catalog_lookup_snapshot(lookup: LookupResultV1, reports_dir: Path) -> Path:
    """Save catalog lookup result to JSON snapshot."""
    data = lookup.model_dump()
    ts_clean = (
        _utc_now().replace(":", "").replace("-", "").replace("T", "_").replace("Z", "")
    )
    filename = f"{ts_clean}_{lookup.request_id}_tool_lookup_snapshot.json"
    path = reports_dir / filename

    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    return path


def get_reports_dir() -> Path:
    """Get or create reports directory for snapshots."""
    base = Path("/media/jotah/SSD_denis/home_jotah/denis_unified_v1/reports")
    base.mkdir(parents=True, exist_ok=True)
    return base
