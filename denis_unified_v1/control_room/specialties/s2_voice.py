from __future__ import annotations

from . import SpecialtySpec

# Voice stack ownership (exclusive).
SPEC = SpecialtySpec(
    specialty_id="s2_voice",
    ownership_prefixes=(
        "voice/",
        "denis_unified_v1/voice/",
    ),
)

