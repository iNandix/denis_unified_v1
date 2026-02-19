from __future__ import annotations

from . import SpecialtySpec

# Frontend/UI ownership (exclusive).
SPEC = SpecialtySpec(
    specialty_id="s3_front",
    ownership_prefixes=(
        "static/",
        "templates/",
    ),
)

