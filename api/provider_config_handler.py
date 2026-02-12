"""Provider config API for frontend-managed .env updates."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from denis_unified_v1.inference.provider_loader import ProviderLoadRegistry, run_provider_load
from denis_unified_v1.sprint_orchestrator.config import load_sprint_config
from denis_unified_v1.sprint_orchestrator.providers import load_provider_statuses


_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ENV_LINE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$")


PROVIDER_FIELDS: dict[str, list[dict[str, Any]]] = {
    "denis_canonical": [
        {"key": "DENIS_CANONICAL_URL", "secret": False, "required": False},
        {"key": "DENIS_CANONICAL_MODEL", "secret": False, "required": False},
        {"key": "DENIS_CANONICAL_API_KEY", "secret": True, "required": False},
        {"key": "DENIS_SPRINT_PRIMARY_PROVIDER", "secret": False, "required": False},
    ],
    "groq": [
        {"key": "GROQ_API_KEY", "secret": True, "required": True},
        {"key": "DENIS_GROQ_URL", "secret": False, "required": False},
        {"key": "DENIS_GROQ_MODEL", "secret": False, "required": False},
    ],
    "openrouter": [
        {"key": "OPENROUTER_API_KEY", "secret": True, "required": True},
        {"key": "DENIS_OPENROUTER_URL", "secret": False, "required": False},
        {"key": "DENIS_OPENROUTER_MODEL", "secret": False, "required": False},
    ],
    "claude": [
        {"key": "ANTHROPIC_API_KEY", "secret": True, "required": True},
        {"key": "DENIS_ANTHROPIC_URL", "secret": False, "required": False},
        {"key": "DENIS_CLAUDE_MODEL", "secret": False, "required": False},
    ],
    "opencode": [
        {"key": "OPENAI_API_KEY", "secret": True, "required": True},
        {"key": "LLM_BASE_URL", "secret": False, "required": True},
        {"key": "LLM_MODEL", "secret": False, "required": False},
    ],
    "vllm": [
        {"key": "DENIS_VLLM_URL", "secret": False, "required": True},
        {"key": "DENIS_VLLM_MODEL", "secret": False, "required": False},
        {"key": "DENIS_VLLM_API_KEY", "secret": True, "required": False},
    ],
    "llama_node1": [
        {"key": "DENIS_SPRINT_LLAMA_NODE1_MODE", "secret": False, "required": True},
        {"key": "DENIS_SPRINT_LLAMA_NODE1_URL", "secret": False, "required": False},
        {"key": "DENIS_SPRINT_LLAMA_NODE1_QUEUE", "secret": False, "required": False},
        {"key": "DENIS_SPRINT_LLAMA_NODE1_API_KEY", "secret": True, "required": False},
    ],
    "llama_node2": [
        {"key": "DENIS_SPRINT_LLAMA_NODE2_MODE", "secret": False, "required": True},
        {"key": "DENIS_SPRINT_LLAMA_NODE2_URL", "secret": False, "required": False},
        {"key": "DENIS_SPRINT_LLAMA_NODE2_QUEUE", "secret": False, "required": False},
        {"key": "DENIS_SPRINT_LLAMA_NODE2_API_KEY", "secret": True, "required": False},
    ],
    "celery_crewai": [
        {"key": "REDIS_URL", "secret": True, "required": True},
        {"key": "DENIS_SPRINT_CELERY_APP", "secret": False, "required": False},
        {"key": "DENIS_SPRINT_CELERY_TASK", "secret": False, "required": False},
        {"key": "DENIS_SPRINT_CREW_QUEUE", "secret": False, "required": False},
    ],
    "legacy_core": [
        {"key": "DENIS_MASTER_URL", "secret": False, "required": False},
        {"key": "LLM_API_KEY", "secret": True, "required": False},
    ],
    "mcp": [
        {"key": "DENIS_SPRINT_MCP_ENABLED", "secret": False, "required": False},
        {"key": "DENIS_SPRINT_MCP_BASE_URL", "secret": False, "required": False},
        {"key": "DENIS_SPRINT_MCP_TOOLS_PATH", "secret": False, "required": False},
        {"key": "DENIS_SPRINT_MCP_AUTH_TOKEN", "secret": True, "required": False},
        {"key": "DENIS_SPRINT_MCP_ALLOW_FILE_CATALOG", "secret": False, "required": False},
    ],
}


class ProviderEnvUpdateRequest(BaseModel):
    provider: str | None = Field(default=None, description="Optional provider scope for key validation")
    updates: dict[str, str] = Field(default_factory=dict)
    create_backup: bool = True


class ProviderLoadRequest(BaseModel):
    provider: str
    api_key: str = ""
    persist_env: bool = True
    create_backup: bool = True
    extra_env: dict[str, str] = Field(default_factory=dict)


def _registry() -> ProviderLoadRegistry:
    return ProviderLoadRegistry()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_path() -> Path:
    cfg = load_sprint_config()
    return cfg.projects_scan_root / ".env"


def _read_env_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="ignore").splitlines()


def _read_env_dict(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in _read_env_lines(path):
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        m = _ENV_LINE_RE.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        if " #" in value and not value.startswith(("'", '"')):
            value = value.split(" #", 1)[0]
        values[key] = value.strip().strip("'").strip('"')
    return values


def _mask_secret(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if len(raw) <= 6:
        return "*" * len(raw)
    return f"{raw[:2]}***{raw[-2:]}"


def _serialize_env_value(value: str) -> str:
    v = str(value)
    if v == "":
        return ""
    if any(ch in v for ch in [" ", "#", '"', "'"]):
        escaped = v.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return v


def _allowed_keys_for_provider(provider: str | None) -> set[str]:
    if not provider:
        return set()
    items = PROVIDER_FIELDS.get(provider, [])
    return {str(item.get("key") or "") for item in items if str(item.get("key") or "")}


def _update_env_file(path: Path, updates: dict[str, str], *, create_backup: bool) -> str | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = _read_env_lines(path)
    index_map: dict[str, int] = {}
    for idx, raw in enumerate(lines):
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        m = _ENV_LINE_RE.match(line)
        if not m:
            continue
        index_map[m.group(1)] = idx

    backup_path: str | None = None
    if create_backup and path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup = path.with_name(f"{path.name}.bak.{stamp}")
        backup.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        backup_path = str(backup)

    for key, value in updates.items():
        serialized = _serialize_env_value(value)
        new_line = f"{key}={serialized}"
        if key in index_map:
            lines[index_map[key]] = new_line
        else:
            lines.append(new_line)

    text = "\n".join(lines).rstrip() + "\n"
    path.write_text(text, encoding="utf-8")
    return backup_path


def _write_env_updates(updates: dict[str, str], create_backup: bool) -> str | None:
    return _update_env_file(_env_path(), updates, create_backup=create_backup)


def _provider_payload(provider: str, env_file_values: dict[str, str], statuses: dict[str, Any]) -> dict[str, Any]:
    fields = []
    for spec in PROVIDER_FIELDS.get(provider, []):
        key = str(spec.get("key") or "")
        secret = bool(spec.get("secret"))
        value = str(env_file_values.get(key) or "")
        fields.append(
            {
                "key": key,
                "secret": secret,
                "required": bool(spec.get("required")),
                "present": bool(value.strip()),
                "value_masked": _mask_secret(value) if secret else value,
            }
        )
    status = statuses.get(provider) or {}
    return {
        "provider": provider,
        "configured": bool(status.get("configured")),
        "missing_env": status.get("missing_env") or [],
        "endpoint": status.get("endpoint") or "",
        "mode": status.get("mode") or "",
        "request_format": status.get("request_format") or "",
        "fields": fields,
    }


def build_provider_config_router() -> APIRouter:
    router = APIRouter(prefix="/v1/providers", tags=["providers"])

    @router.get("/config")
    def get_provider_config() -> dict[str, Any]:
        cfg = load_sprint_config()
        env_path = _env_path()
        env_file_values = _read_env_dict(env_path)
        statuses = {item.provider: item.as_dict() for item in load_provider_statuses(cfg)}
        providers = []
        for provider in sorted(PROVIDER_FIELDS.keys()):
            providers.append(_provider_payload(provider, env_file_values, statuses))
        return {
            "status": "ok",
            "timestamp_utc": _utc_now(),
            "env_file": str(env_path),
            "providers": providers,
        }

    @router.post("/config")
    def update_provider_config(req: ProviderEnvUpdateRequest) -> dict[str, Any]:
        if not req.updates:
            raise HTTPException(status_code=400, detail="updates_required")

        if req.provider and req.provider not in PROVIDER_FIELDS:
            raise HTTPException(status_code=404, detail=f"unknown_provider:{req.provider}")

        allowed = _allowed_keys_for_provider(req.provider)
        sanitized: dict[str, str] = {}
        for key, value in req.updates.items():
            if not _ENV_KEY_RE.fullmatch(key or ""):
                raise HTTPException(status_code=400, detail=f"invalid_env_key:{key}")
            if req.provider and key not in allowed:
                raise HTTPException(status_code=400, detail=f"key_not_allowed_for_provider:{key}")
            sanitized[key] = str(value)

        env_path = _env_path()
        backup_path = _update_env_file(env_path, sanitized, create_backup=bool(req.create_backup))

        cfg = load_sprint_config()
        statuses = {item.provider: item.as_dict() for item in load_provider_statuses(cfg)}
        masked = {k: _mask_secret(v) for k, v in sanitized.items()}
        scoped_status = statuses.get(req.provider) if req.provider else None
        return {
            "status": "ok",
            "timestamp_utc": _utc_now(),
            "provider": req.provider or "multi",
            "updated_keys": sorted(sanitized.keys()),
            "updated_values_masked": masked,
            "backup_file": backup_path or "",
            "provider_status": scoped_status or {},
        }

    @router.post("/load")
    def start_provider_load(req: ProviderLoadRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
        provider = str(req.provider or "").strip().lower()
        if not provider:
            raise HTTPException(status_code=400, detail="provider_required")

        reg = _registry()
        run_id = reg.start_run(provider)
        background_tasks.add_task(
            run_provider_load,
            provider=provider,
            run_id=run_id,
            api_key=req.api_key,
            persist_env=bool(req.persist_env),
            create_backup=bool(req.create_backup),
            extra_env=dict(req.extra_env or {}),
            env_writer=_write_env_updates,
            registry=reg,
        )
        return {
            "status": "accepted",
            "timestamp_utc": _utc_now(),
            "run_id": run_id,
            "provider": provider,
        }

    @router.get("/load/{run_id}")
    def get_provider_load_run(run_id: str) -> dict[str, Any]:
        payload = _registry().get_run(run_id)
        if not payload:
            raise HTTPException(status_code=404, detail="run_not_found")
        return payload

    @router.get("/load")
    def list_provider_load_runs(
        provider: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=200),
    ) -> dict[str, Any]:
        runs = _registry().list_runs(provider=provider, limit=limit)
        return {
            "status": "ok",
            "timestamp_utc": _utc_now(),
            "provider": provider or "",
            "runs": runs,
        }

    @router.get("/models")
    def list_provider_models(
        provider: str | None = Query(default=None),
        available_only: bool = Query(default=True),
    ) -> dict[str, Any]:
        models = _registry().list_models(provider=provider, available_only=bool(available_only))
        return {
            "status": "ok",
            "timestamp_utc": _utc_now(),
            "provider": provider or "",
            "available_only": bool(available_only),
            "models": models,
        }

    return router
