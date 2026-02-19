"""X-Denis-Hop anti-loop utilities.

Denis may call OpenAI-compatible endpoints (node engines, gateways). If those
endpoints accidentally point back to Denis itself, we can end up in request
loops. We use an explicit hop counter header to detect and block re-entry.

Design constraints:
- No prompts or secrets logged here.
- Keep propagation implicit (contextvar) to avoid threading headers through
  every call site.
"""

from __future__ import annotations

from contextvars import ContextVar

_DENIS_HOP: ContextVar[int] = ContextVar("denis_x_denis_hop", default=0)


def parse_hop(value: str | None) -> int:
    """Parse hop header value to a non-negative int (invalid -> 0)."""
    if value is None:
        return 0
    raw = str(value).strip()
    if not raw:
        return 0
    try:
        hop = int(raw, 10)
    except Exception:
        return 0
    return hop if hop > 0 else 0


def get_current_hop() -> int:
    try:
        hop = int(_DENIS_HOP.get() or 0)
    except Exception:
        hop = 0
    return hop if hop > 0 else 0


def set_current_hop(hop: int):
    """Set current hop in context; returns a token for reset()."""
    try:
        value = int(hop)
    except Exception:
        value = 0
    if value < 0:
        value = 0
    return _DENIS_HOP.set(value)


def reset(token) -> None:
    _DENIS_HOP.reset(token)


def next_hop_header() -> dict[str, str]:
    """Return headers to propagate to downstream calls."""
    return {"X-Denis-Hop": str(get_current_hop() + 1)}

