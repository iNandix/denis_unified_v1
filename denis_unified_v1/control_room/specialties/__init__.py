"""WS11-G: worker specialties + no-overlap contract.

Specialties define ownership prefixes and expose a deterministic contract hash.
Workers validate Task.requested_paths are a subset of the specialty ownership set.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


def _sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()


@dataclass(frozen=True)
class SpecialtySpec:
    specialty_id: str
    ownership_prefixes: tuple[str, ...]

    @property
    def no_overlap_contract_hash(self) -> str:
        # Stable hash used by Task.no_overlap_contract_hash.
        return _sha256("\n".join(sorted(self.ownership_prefixes)))

    def allows_paths(self, paths: list[str]) -> bool:
        if not paths:
            return True
        prefs = self.ownership_prefixes
        for p in paths:
            s = str(p or "")
            if not s:
                continue
            if not any(s.startswith(pref) for pref in prefs):
                return False
        return True


def get_specialty(specialty_id: str) -> SpecialtySpec:
    sid = (specialty_id or "").strip()
    if sid == "s1_core":
        from .s1_core import SPEC

        return SPEC
    if sid == "s2_voice":
        from .s2_voice import SPEC

        return SPEC
    if sid == "s3_front":
        from .s3_front import SPEC

        return SPEC
    if sid == "s4_govops":
        from .s4_govops import SPEC

        return SPEC
    raise KeyError(f"unknown_specialty:{sid}")

