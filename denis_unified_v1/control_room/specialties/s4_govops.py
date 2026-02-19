from __future__ import annotations

from . import SpecialtySpec

# Governance/ops guardrails + graph docs ownership (exclusive).
SPEC = SpecialtySpec(
    specialty_id="s4_govops",
    ownership_prefixes=(
        "denis_unified_v1/guardrails/",
        "docs/graph/",
        "docs/schema/",
    ),
)

