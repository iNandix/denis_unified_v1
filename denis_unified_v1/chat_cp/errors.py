"""Errors and redaction helpers for chat control plane."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

_RE_SECRET = re.compile(r"(sk-[A-Za-z0-9\-_]+|anthropic|api[_-]?key)", re.IGNORECASE)


def redact(text: str) -> str:
    return _RE_SECRET.sub("[REDACTED]", text or "")


def hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()


@dataclass
class ChatProviderError(Exception):
    code: str
    msg: str
    retryable: bool = False

    def __str__(self) -> str:
        return f"{self.code}: {redact(self.msg)}"
