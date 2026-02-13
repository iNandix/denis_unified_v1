"""MCP bridge for Denis tool catalog discovery and visibility."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import urllib.error
import urllib.request
from typing import Any

from .config import SprintOrchestratorConfig
from .event_bus import EventBus, publish_event
from .models import SprintEvent
from .providers import merged_env
from .session_store import SessionStore


def _raw_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _strip_url_path(url: str) -> str:
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return ""
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def _derive_base_url(env: dict[str, str]) -> str:
    explicit = (env.get("DENIS_SPRINT_MCP_BASE_URL") or "").strip()
    if explicit:
        base = _strip_url_path(explicit)
        return base or explicit

    baseline = (env.get("DENIS_BASELINE_ENDPOINTS") or "").strip()
    if baseline:
        candidates = [x.strip() for x in baseline.split(",") if x.strip()]
        for candidate in candidates:
            if ":8084" in candidate:
                base = _strip_url_path(candidate)
                if base:
                    return base

    master = (env.get("DENIS_MASTER_URL") or "").strip()
    if master:
        base = _strip_url_path(master)
        if base:
            return base

    return "http://127.0.0.1:8084"


class MCPBridge:
    def __init__(self, config: SprintOrchestratorConfig) -> None:
        self.config = config
        env = merged_env(config)

        self.base_url = (_derive_base_url(env) or "").strip()
        self.tools_path = (env.get("DENIS_SPRINT_MCP_TOOLS_PATH") or "/tools").strip()
        self.enabled = _raw_bool(env.get("DENIS_SPRINT_MCP_ENABLED"), bool(self.base_url))
        self.allow_file_catalog = _raw_bool(
            env.get("DENIS_SPRINT_MCP_ALLOW_FILE_CATALOG"), False
        )
        catalog_raw = (env.get("DENIS_SPRINT_MCP_TOOL_CATALOG_FILE") or "").strip()
        self.catalog_file = Path(catalog_raw) if catalog_raw else None
        self.auth_token = (env.get("DENIS_SPRINT_MCP_AUTH_TOKEN") or "").strip()

    def status(self) -> dict[str, Any]:
        source = "none"
        configured = False
        if self.catalog_file is not None:
            if self.catalog_file.exists() and self.allow_file_catalog:
                source = "file"
                configured = True
            elif self.catalog_file.exists():
                source = "file_disabled"
            else:
                source = "file_missing"
        elif self.base_url:
            source = "http"
            configured = True
        return {
            "enabled": self.enabled,
            "configured": configured,
            "source": source,
            "base_url": self.base_url,
            "tools_path": self.tools_path,
            "catalog_file": str(self.catalog_file) if self.catalog_file is not None else "",
            "allow_file_catalog": self.allow_file_catalog,
            "auth_configured": bool(self.auth_token),
        }

    def list_tools(self) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        if self.catalog_file is not None and self.allow_file_catalog:
            return self._list_from_file(self.catalog_file)
        if self.base_url:
            return self._list_from_http()
        return []

    def _list_from_file(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return self._normalize_tools(payload)

    def _list_from_http(self) -> list[dict[str, Any]]:
        candidates: list[str] = []
        for path in [self.tools_path, "/tools", "/v1/tools", "/mcp/tools"]:
            url = self.base_url.rstrip("/") + "/" + path.lstrip("/")
            if url not in candidates:
                candidates.append(url)

        for url in candidates:
            req = urllib.request.Request(url=url, method="GET")
            req.add_header("Accept", "application/json")
            if self.auth_token:
                req.add_header("Authorization", f"Bearer {self.auth_token}")
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    raw = resp.read().decode("utf-8", errors="ignore")
            except (urllib.error.URLError, TimeoutError, ValueError):
                continue
            try:
                payload = json.loads(raw)
            except Exception:
                continue
            tools = self._normalize_tools(payload)
            if tools:
                return tools
        return []

    def _normalize_tools(self, payload: Any) -> list[dict[str, Any]]:
        tools_raw: list[Any]
        if isinstance(payload, list):
            tools_raw = payload
        elif isinstance(payload, dict) and isinstance(payload.get("tools"), list):
            tools_raw = payload.get("tools") or []
        else:
            return []

        normalized: list[dict[str, Any]] = []
        for item in tools_raw:
            if isinstance(item, str):
                name = item.strip()
                if name:
                    normalized.append(
                        {
                            "name": name,
                            "description": "",
                            "category": "general",
                            "requires_auth": False,
                        }
                    )
                continue
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("id") or "").strip()
            if not name:
                continue
            normalized.append(
                {
                    "name": name,
                    "description": str(item.get("description") or "").strip(),
                    "category": str(item.get("category") or "general").strip(),
                    "requires_auth": bool(item.get("requires_auth", False)),
                }
            )
        return normalized

    def emit_catalog_snapshot(
        self,
        *,
        session_id: str,
        worker_id: str,
        store: SessionStore,
        bus: EventBus | None = None,
    ) -> dict[str, Any]:
        status = self.status()
        tools = self.list_tools()
        payload = {
            "mcp_status": status,
            "tools_count": len(tools),
            "tools": tools[:50],
        }
        publish_event(
            store,
            SprintEvent(
                session_id=session_id,
                worker_id=worker_id,
                kind="mcp.catalog",
                message=f"MCP catalog snapshot tools={len(tools)} configured={status.get('configured')}",
                payload=payload,
            ),
            bus,
        )
        return payload
