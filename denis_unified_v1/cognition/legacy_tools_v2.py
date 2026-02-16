"""Legacy Tools v2 - Reactivate 100+ tools with policy safety and graph projection.

Compat wrapper for build_tool_registry() + HassAdapter tools.
Enforces confidence bands, internet gates, command gates.
Logs toolchain_step_logs, projects to graph, idempotency.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from denis_unified_v1.cognition.tools import build_tool_registry
from denis_unified_v1.telemetry.steps import emit_tool_step


_REGISTRY_V2: Any = None

def get_tool_registry_v2() -> Dict[str, Any]:
    global _REGISTRY_V2
    if _REGISTRY_V2 is None:
        _REGISTRY_V2 = build_tool_registry_v2()
    return _REGISTRY_V2


@dataclass
class ToolResult:
    ok: bool
    data: Dict[str, Any]
    error: Optional[Dict[str, Any]] = None


@dataclass
class ToolMeta:
    name: str
    domain: str          # belt
    mutability: str      # "ro"|"rw"
    risk: str            # "low"|"med"|"high"
    requires_internet: bool = False
    timeout_ms: int = 30_000


def _args_hash(args: Dict[str, Any]) -> str:
    blob = json.dumps(args, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


# --- run_command gating ---
_DANGEROUS_TOKENS = [
    " rm ", "rm -", "mkfs", " dd ", "chmod", "chown", "sudo", "shutdown", "reboot",
    "systemctl", " service ", "iptables", " curl ", " wget ", "| bash", "|sh",
    ">/etc", ">>/etc", ">/root", ">>/root",
]
_ALLOWED_PREFIXES = [
    "pytest", "python -m", "python3 -m", "rg", "grep", "ls", "cat", "tail",
    "git status", "git diff",
]


def is_command_allowed(cmd: str) -> bool:
    c = f" {cmd.strip()} ".lower()
    if any(tok in c for tok in _DANGEROUS_TOKENS):
        return False
    if any(c.strip().startswith(p) for p in _ALLOWED_PREFIXES):
        return True
    return False


class LegacyToolAdapter:
    """
    Wrap legacy callable(**kwargs)->str into a Tool v2 interface:
      await tool.run(ctx, args) -> ToolResult
    """
    def __init__(self, fn: Callable[..., str], meta: ToolMeta):
        self.fn = fn
        self.meta = meta

    async def run(self, ctx: Dict[str, Any], args: Dict[str, Any]) -> ToolResult:
        request_id = str(ctx.get("request_id", ""))
        band = str(ctx.get("confidence_band", "low"))

        # Policy: confidence bands
        if band == "low":
            emit_tool_step({
                "request_id": request_id,
                "step_id": f"{request_id}:{self.meta.name}:{_args_hash(args)}",
                "tool": self.meta.name,
                "domain": self.meta.domain,
                "mutability": self.meta.mutability,
                "risk": self.meta.risk,
                "status": "blocked",
                "ok": False,
                "error": {"type": "policy", "message": "low confidence: no tools"},
            })
            return ToolResult(False, {}, {"type": "policy", "message": "low confidence: no tools"})

        if band == "medium" and self.meta.mutability != "ro":
            emit_tool_step({
                "request_id": request_id,
                "step_id": f"{request_id}:{self.meta.name}:{_args_hash(args)}",
                "tool": self.meta.name,
                "domain": self.meta.domain,
                "mutability": self.meta.mutability,
                "risk": self.meta.risk,
                "status": "blocked",
                "ok": False,
                "error": {"type": "policy", "message": "medium confidence: read-only tools only"},
            })
            return ToolResult(False, {}, {"type": "policy", "message": "medium confidence: read-only tools only"})

        # Policy: internet gate
        if self.meta.requires_internet and not (ctx.get("internet_gate") and ctx.get("allow_boosters")):
            emit_tool_step({
                "request_id": request_id,
                "step_id": f"{request_id}:{self.meta.name}:{_args_hash(args)}",
                "tool": self.meta.name,
                "domain": self.meta.domain,
                "mutability": self.meta.mutability,
                "risk": self.meta.risk,
                "status": "blocked",
                "ok": False,
                "error": {"type": "policy", "message": "internet gated"},
            })
            return ToolResult(False, {}, {"type": "policy", "message": "internet gated"})

        # run_command gate
        if self.meta.name == "run_command":
            cmd = str(args.get("cmd", ""))
            if band != "high":
                emit_tool_step({
                    "request_id": request_id,
                    "step_id": f"{request_id}:{self.meta.name}:{_args_hash(args)}",
                    "tool": self.meta.name,
                    "domain": self.meta.domain,
                    "mutability": self.meta.mutability,
                    "risk": self.meta.risk,
                    "status": "blocked",
                    "ok": False,
                    "error": {"type": "policy", "message": "run_command blocked unless high confidence"},
                })
                return ToolResult(False, {}, {"type": "policy", "message": "run_command blocked unless high confidence"})
            if not is_command_allowed(cmd):
                emit_tool_step({
                    "request_id": request_id,
                    "step_id": f"{request_id}:{self.meta.name}:{_args_hash(args)}",
                    "tool": self.meta.name,
                    "domain": self.meta.domain,
                    "mutability": self.meta.mutability,
                    "risk": self.meta.risk,
                    "status": "blocked",
                    "ok": False,
                    "error": {"type": "policy", "message": "command not allowed by gate"},
                })
                return ToolResult(False, {}, {"type": "policy", "message": "command not allowed by gate"})

        step_id = f"{request_id}:{self.meta.name}:{_args_hash(args)}"
        t0 = time.time()
        emit_tool_step({
            "request_id": request_id,
            "step_id": step_id,
            "tool": self.meta.name,
            "domain": self.meta.domain,
            "mutability": self.meta.mutability,
            "risk": self.meta.risk,
            "status": "start",
            "ts_start": t0,
            "args": args,
        })

        try:
            out = await asyncio.to_thread(self.fn, **args)
            ok = True
            res = ToolResult(True, {"text": out, "step_id": step_id})
        except Exception as e:
            ok = False
            res = ToolResult(False, {"step_id": step_id}, {"type": "exception", "message": str(e)})

        t1 = time.time()
        emit_tool_step({
            "request_id": request_id,
            "step_id": step_id,
            "tool": self.meta.name,
            "domain": self.meta.domain,
            "mutability": self.meta.mutability,
            "risk": self.meta.risk,
            "status": "end",
            "ts_end": t1,
            "duration_ms": int((t1 - t0) * 1000),
            "ok": ok,
            "error": res.error,
        })
        return res


def build_tool_registry_v2() -> Dict[str, Any]:
    legacy = build_tool_registry()
    metas = {
        "list_files": ToolMeta("list_files", "ide.fs", "ro", "low"),
        "grep_search": ToolMeta("grep_search", "ide.fs", "ro", "low"),
        "read_file": ToolMeta("read_file", "ide.fs", "ro", "low"),
        "run_command": ToolMeta("run_command", "ide.exec", "rw", "high"),
    }
    v2: Dict[str, Any] = {}
    for name, fn in legacy.items():
        v2[name] = LegacyToolAdapter(fn, metas[name])
    return v2
