"""Guardrails for event payloads.

Goal:
- No secrets or dangerous fields persisted to WS events or sqlite event store.
- Keep fail-open behavior: sanitize and continue.

Policy:
- Drop keys containing deny substrings (case-insensitive).
- Redact known secret patterns in string values.
- Enforce size caps:
  - MAX_STR_LEN_EVENT (default 2000) for event payload strings.
  - MAX_LIST_LEN_EVENT (default 50) for list values.

On violations:
- Remove offending fields (never persist them).
- Add `_guardrails` summary into payload (safe).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Any

from denis_unified_v1.chat_cp.errors import redact as _basic_redact


DENY_KEYS_DEFAULT = [
    "prompt",
    "html",
    "snippet",
    "content",
    "cookie",
    "authorization",
    "token",
    "api_key",
    "secret",
    "session",
]

ALLOW_KEYS = {
    # Hash/length fields are safe and must not be dropped.
    "content_sha256",
    "content_len",
    "query_sha256",
    "query_len",
    "prompt_sha256",
    "prompt_len",
    "args_sha256",
    "args_len",
    "result_sha256",
    "result_len",
    "hash_sha256",
    "after_hash",
    "idempotency_key",
    "chunk_id",
}

_RE_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9\-\._~\+/]+=*", re.IGNORECASE)
_RE_JWT = re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")


def _sha256(text: str) -> str:
    raw = (text or "").encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class PayloadSanitizeResult:
    payload: dict[str, Any]
    violations: int
    dropped_keys: list[str]
    truncated: int


def _max_str_len() -> int:
    try:
        return int(os.getenv("MAX_STR_LEN_EVENT", "2000"))
    except Exception:
        return 2000


def _max_list_len() -> int:
    try:
        return int(os.getenv("MAX_LIST_LEN_EVENT", "50"))
    except Exception:
        return 50


def _deny_keys() -> list[str]:
    raw = os.getenv("DENY_KEYS_EVENT")
    if raw:
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if parts:
            return parts
    return DENY_KEYS_DEFAULT


def _is_denied_key(key: str) -> bool:
    k = (key or "").lower()
    if k in ALLOW_KEYS:
        return False
    # Allow common safe suffixes even if they contain deny substrings.
    if k.endswith("_sha256") or k.endswith("_len"):
        return False
    for d in _deny_keys():
        if d.lower() in k:
            return True
    return False


def _redact_str(s: str) -> str:
    t = _basic_redact(s or "")
    t = _RE_BEARER.sub("Bearer ***", t)
    t = _RE_JWT.sub("***JWT***", t)
    return t


def _sanitize_value(v: Any, *, path: str, stats: dict[str, Any]) -> Any:
    if v is None or isinstance(v, (bool, int, float)):
        return v

    if isinstance(v, str):
        s = _redact_str(v)
        max_len = _max_str_len()
        if len(s) > max_len:
            stats["truncated"] += 1
            stats["violations"] += 1
            stats["truncations"].append(
                {"path": path, "orig_len": len(s), "sha256": _sha256(s)}
            )
            s = s[: max_len - 1] + "…"
        return s

    if isinstance(v, dict):
        out: dict[str, Any] = {}
        for k, vv in v.items():
            kk = str(k)
            if _is_denied_key(kk):
                stats["violations"] += 1
                stats["dropped_keys"].append(f"{path}.{kk}" if path else kk)
                continue
            out[kk] = _sanitize_value(vv, path=f"{path}.{kk}" if path else kk, stats=stats)
        return out

    if isinstance(v, list):
        max_len = _max_list_len()
        if len(v) > max_len:
            stats["violations"] += 1
            stats["truncated"] += 1
            stats["list_caps"].append({"path": path, "orig_len": len(v), "cap": max_len})
            v = v[:max_len]
        return [_sanitize_value(x, path=f"{path}[]", stats=stats) for x in v]

    # Fallback: stringify safely
    try:
        s = json.dumps(v, ensure_ascii=True, sort_keys=True)
    except Exception:
        s = str(v)
    return _sanitize_value(s, path=path, stats=stats)


def sanitize_event_payload(payload: dict[str, Any] | None) -> PayloadSanitizeResult:
    enabled = (os.getenv("GUARDRAILS_ENABLED", "1") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if not enabled:
        p = payload if isinstance(payload, dict) else {}
        return PayloadSanitizeResult(payload=dict(p), violations=0, dropped_keys=[], truncated=0)
    stats: dict[str, Any] = {
        "violations": 0,
        "dropped_keys": [],
        "truncated": 0,
        "truncations": [],
        "list_caps": [],
    }
    p = payload if isinstance(payload, dict) else {}
    out = _sanitize_value(p, path="", stats=stats)
    if not isinstance(out, dict):
        out = {}

    if stats["violations"] > 0:
        out["_guardrails"] = {
            "violations": int(stats["violations"]),
            "dropped_keys": stats["dropped_keys"][:50],
            "truncated": int(stats["truncated"]),
            "truncations": stats["truncations"][:20],
            "list_caps": stats["list_caps"][:20],
        }
    return PayloadSanitizeResult(
        payload=out,
        violations=int(stats["violations"]),
        dropped_keys=list(stats["dropped_keys"]),
        truncated=int(stats["truncated"]),
    )
