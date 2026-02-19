"""Redaction gate for indexing (no secrets, no raw prompts)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from denis_unified_v1.chat_cp.errors import redact as _basic_redact

# Regexes must match real whitespace/dots (avoid double escaping in raw strings).
_RE_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9\-\._~\+/]+=*", re.IGNORECASE)
_RE_JWT = re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")
_RE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}")
_RE_PHONE = re.compile(r"\\+?\\d[\\d\\s\\-\\(\\)]{8,}\\d")


@dataclass(frozen=True)
class SafetyInfo:
    redacted: bool
    pii_risk: str  # low|med|high


def redact_for_indexing(text: str) -> tuple[str, SafetyInfo]:
    """Return (safe_text, safety)."""
    raw = text or ""
    redacted = False
    s = raw

    # Secret/Key redaction (existing policy)
    s2 = _basic_redact(s)
    if s2 != s:
        redacted = True
        s = s2

    # Auth headers / JWTs
    s2 = _RE_BEARER.sub("Bearer ***", s)
    if s2 != s:
        redacted = True
        s = s2
    s2 = _RE_JWT.sub("***JWT***", s)
    if s2 != s:
        redacted = True
        s = s2

    pii_risk = "low"
    if _RE_EMAIL.search(s) or _RE_PHONE.search(s):
        pii_risk = "high"
        redacted = True

    return s, SafetyInfo(redacted=bool(redacted), pii_risk=pii_risk)


def safe_snippet(text: str, *, max_chars: int = 400) -> str:
    s = (text or "").strip()
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 1] + "…"
