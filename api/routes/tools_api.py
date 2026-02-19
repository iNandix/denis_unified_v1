"""OpenCode-compatible Tools API (v1).

This exposes a minimal tool calling surface area for OpenCode's Denis provider:
- GET  /v1/tools/list
- GET  /v1/tools/{tool_name}
- POST /v1/tools/call
- POST /v1/tools/history

Implementation notes:
- Uses legacy_tools_v2 registry to enforce confidence-band and command gating.
- Tool step logs are written by legacy_tools_v2 via emit_tool_step() to JSONL.
- File tools are sandboxed to DENIS_WORK_DIR.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field


router = APIRouter(prefix="/v1/tools", tags=["tools"])


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _reports_path() -> Path:
    # Use the canonical telemetry path resolver (runtime env aware).
    from denis_unified_v1.telemetry.steps import get_toolchain_step_path

    return get_toolchain_step_path()


def _tool_registry_v2() -> dict[str, Any]:
    # Lazy import to keep fail-open semantics.
    from denis_unified_v1.cognition.legacy_tools_v2 import get_tool_registry_v2

    return get_tool_registry_v2()


def _default_confidence_band() -> str:
    # For OpenCode interactive tool execution we default to high, otherwise v2 blocks everything.
    band = (os.getenv("DENIS_TOOLS_CONFIDENCE_BAND") or "high").strip().lower()
    return band if band in {"low", "medium", "high"} else "high"


class ToolCallRequest(BaseModel):
    tool: str = Field(..., description="Tool name")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool args")
    request_id: str | None = Field(default=None, description="Optional external request id")
    confidence_band: str | None = Field(default=None, description="low|medium|high (optional)")


class ToolHistoryRequest(BaseModel):
    tool_name: str | None = None
    limit: int = 100


@router.get("/list")
async def list_tools(category: str | None = None) -> dict[str, Any]:
    reg = _tool_registry_v2()
    tools = []
    for name, tool in sorted(reg.items(), key=lambda kv: kv[0]):
        meta = getattr(tool, "meta", None)
        tools.append(
            {
                "name": name,
                "domain": getattr(meta, "domain", ""),
                "mutability": getattr(meta, "mutability", ""),
                "risk": getattr(meta, "risk", ""),
                "requires_approval": getattr(meta, "requires_approval", None),
                "requires_internet": getattr(meta, "requires_internet", False),
                "timeout_ms": getattr(meta, "timeout_ms", 30_000),
            }
        )

    # Optional: lightweight category filtering by domain prefix.
    if category:
        cat = str(category).strip().lower()
        if cat:
            tools = [t for t in tools if str(t.get("domain") or "").lower().startswith(cat)]

    return {"ok": True, "count": len(tools), "tools": tools, "ts_utc": _utc_now()}


@router.get("/{tool_name}")
async def get_tool(tool_name: str) -> dict[str, Any]:
    reg = _tool_registry_v2()
    tool = reg.get(tool_name)
    if tool is None:
        return {
            "ok": False,
            "error": {"type": "not_found", "message": f"tool_not_found: {tool_name}"},
            "ts_utc": _utc_now(),
        }

    meta = getattr(tool, "meta", None)
    return {
        "ok": True,
        "tool": tool_name,
        "meta": {
            "domain": getattr(meta, "domain", ""),
            "mutability": getattr(meta, "mutability", ""),
            "risk": getattr(meta, "risk", ""),
            "requires_approval": getattr(meta, "requires_approval", None),
            "requires_internet": getattr(meta, "requires_internet", False),
            "timeout_ms": getattr(meta, "timeout_ms", 30_000),
        },
        "ts_utc": _utc_now(),
    }


@router.post("/call")
async def call_tool(req: ToolCallRequest) -> dict[str, Any]:
    reg = _tool_registry_v2()
    tool = reg.get(req.tool)
    if tool is None:
        return {
            "ok": False,
            "tool": req.tool,
            "error": {"type": "not_found", "message": f"tool_not_found: {req.tool}"},
            "ts_utc": _utc_now(),
        }

    request_id = (req.request_id or "").strip() or f"opencode:{uuid.uuid4().hex[:12]}"
    band = (req.confidence_band or _default_confidence_band()).strip().lower()
    ctx = {"request_id": request_id, "confidence_band": band}

    t0 = time.time()
    try:
        if hasattr(tool, "run"):
            result = await tool.run(ctx, dict(req.arguments or {}))
            ok = bool(getattr(result, "ok", False))
            data = getattr(result, "data", {}) or {}
            err = getattr(result, "error", None)
        else:
            # Compat: plain callables
            out = tool(**(req.arguments or {}))
            ok = True
            data = {"text": str(out), "step_id": f"{request_id}:{req.tool}:direct"}
            err = None
    except Exception as e:
        ok = False
        data = {}
        err = {"type": "exception", "message": str(e)[:200]}

    duration_ms = int((time.time() - t0) * 1000)
    text_out = ""
    if isinstance(data, dict):
        text_out = str(data.get("text") or "")

    return {
        "ok": ok,
        "tool": req.tool,
        "request_id": request_id,
        "duration_ms": duration_ms,
        "result": data,
        "output": text_out,  # convenience alias for UIs
        "error": err,
        "ts_utc": _utc_now(),
    }


@router.post("/history")
async def tool_history(req: ToolHistoryRequest) -> dict[str, Any]:
    path = _reports_path()
    limit = max(1, int(req.limit or 100))
    tool_name = (req.tool_name or "").strip()

    if not path.exists():
        return {
            "ok": True,
            "tool_name": tool_name or None,
            "count": 0,
            "events": [],
            "ts_utc": _utc_now(),
        }

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:
        return {
            "ok": False,
            "error": {"type": "read_error", "message": str(e)[:200]},
            "ts_utc": _utc_now(),
        }

    events: list[dict[str, Any]] = []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue

        if tool_name:
            if str(ev.get("tool") or "") != tool_name:
                continue

        events.append(ev)
        if len(events) >= limit:
            break

    return {
        "ok": True,
        "tool_name": tool_name or None,
        "count": len(events),
        "events": events,
        "ts_utc": _utc_now(),
    }
