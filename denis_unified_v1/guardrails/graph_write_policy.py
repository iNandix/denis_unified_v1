"""Guardrails for Graph writes (SSoT state only).

Goal:
- Ensure Graph never receives long text, snippets, HTML, prompts, or secrets.
- Enforce conservative property typing for Neo4j:
  - Only scalar values are allowed (str/int/float/bool/None).
  - dict/list values are converted to JSON strings (capped).

Policy:
- Drop keys containing deny substrings (case-insensitive).
- Redact known secret patterns in string values.
- Size caps:
  - MAX_STR_LEN_GRAPH (default 512)
  - MAX_LIST_LEN_GRAPH (default 50) before JSON conversion
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
    "hash_sha256",
    "after_hash",
    "idempotency_key",
    "content_sha256",
    "content_len",
    "query_sha256",
    "query_len",
    "prompt_sha256",
    "prompt_len",
    "counts_json",
}

_RE_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9\-\._~\+/]+=*", re.IGNORECASE)
_RE_JWT = re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")


def _sha256(text: str) -> str:
    raw = (text or "").encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()


def _max_str_len() -> int:
    try:
        return int(os.getenv("MAX_STR_LEN_GRAPH", "512"))
    except Exception:
        return 512


def _max_list_len() -> int:
    try:
        return int(os.getenv("MAX_LIST_LEN_GRAPH", "50"))
    except Exception:
        return 50


def _deny_keys() -> list[str]:
    raw = os.getenv("DENY_KEYS_GRAPH")
    if raw:
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if parts:
            return parts
    return DENY_KEYS_DEFAULT


def _is_denied_key(key: str) -> bool:
    k = (key or "").lower()
    if k in ALLOW_KEYS:
        return False
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


@dataclass(frozen=True)
class GraphPropsResult:
    props: dict[str, Any]
    violations: int
    dropped_keys: list[str]
    truncated: int


def sanitize_graph_props(props: dict[str, Any] | None) -> GraphPropsResult:
    enabled = (os.getenv("GUARDRAILS_ENABLED", "1") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if not enabled:
        p = props if isinstance(props, dict) else {}
        return GraphPropsResult(props=dict(p), violations=0, dropped_keys=[], truncated=0)
    p = props if isinstance(props, dict) else {}
    out: dict[str, Any] = {}
    violations = 0
    dropped: list[str] = []
    truncated = 0

    for k, v in p.items():
        key = str(k)
        if _is_denied_key(key):
            violations += 1
            dropped.append(key)
            continue

        # Only allow scalar types. Convert dict/list to JSON string (capped).
        vv: Any = v
        if isinstance(vv, str):
            s = _redact_str(vv)
            if len(s) > _max_str_len():
                violations += 1
                truncated += 1
                s = s[: _max_str_len() - 1] + "…"
                out[f"{key}__sha256"] = _sha256(_redact_str(vv))
                out[f"{key}__orig_len"] = int(len(vv))
            out[key] = s
            continue

        if vv is None or isinstance(vv, (bool, int, float)):
            out[key] = vv
            continue

        # list/dict or other objects: stringify.
        if isinstance(vv, list) and len(vv) > _max_list_len():
            violations += 1
            truncated += 1
            vv = vv[: _max_list_len()]
        try:
            s = json.dumps(vv, ensure_ascii=True, sort_keys=True)
        except Exception:
            s = str(vv)
        s = _redact_str(s)
        if len(s) > _max_str_len():
            violations += 1
            truncated += 1
            out[f"{key}__sha256"] = _sha256(s)
            out[f"{key}__orig_len"] = int(len(s))
            s = s[: _max_str_len() - 1] + "…"
        out[key] = s

    if violations > 0:
        out["_guardrails_violations"] = int(violations)
        out["_guardrails_truncated"] = int(truncated)
        out["_guardrails_dropped_keys"] = ",".join(dropped[:20])

    return GraphPropsResult(props=out, violations=violations, dropped_keys=dropped, truncated=truncated)
