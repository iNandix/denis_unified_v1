from __future__ import annotations

from . import SpecialtySpec

# Core backend ownership: control_room + graph modules only (keep exclusive).
SPEC = SpecialtySpec(
    specialty_id="s1_core",
    ownership_prefixes=(
        "denis_unified_v1/control_room/",
        "denis_unified_v1/graph/",
    ),
)

