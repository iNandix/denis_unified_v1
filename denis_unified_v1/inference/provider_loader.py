"""Provider onboarding pipeline with step logging and model schema registry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Callable
import urllib.error
import urllib.request
import uuid


_FREE_PRICING_EPSILON = 1e-12
_STEP_TOTAL = 5


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(raw: Any, default: float = 0.0) -> float:
    if raw is None:
        return default
    try:
        return float(raw)
    except Exception:
        return default


def _mask_secret(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if len(raw) <= 6:
        return "*" * len(raw)
    return f"{raw[:2]}***{raw[-2:]}"


def _slug(value: str) -> str:
    out = re.sub(r"[^a-z0-9_]+", "_", (value or "").strip().lower())
    out = re.sub(r"_+", "_", out).strip("_")
    return out or "unknown"


def _http_json(
    *,
    url: str,
    headers: dict[str, str] | None = None,
    timeout_sec: float = 20.0,
) -> dict[str, Any]:
    req = urllib.request.Request(url=url, method="GET", headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=max(0.5, timeout_sec)) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            status = int(getattr(resp, "status", 200))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore") if exc.fp else str(exc)
        raise RuntimeError(f"http_error_{exc.code}:{body[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"network_error:{exc}") from exc

    if status >= 400:
        raise RuntimeError(f"http_error_{status}")
    try:
        payload = json.loads(raw)
    except Exception as exc:
        raise RuntimeError(f"invalid_json:{raw[:200]}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("unexpected_payload")
    return payload


@dataclass
class DiscoveredModel:
    """Modelo descubierto de un provider."""
    provider: str
    model_id: str
    model_name: str
    request_format: str
    is_free: bool
    context_length: int
    supports_tools: bool
    supports_json_mode: bool
    tags: list[str]
    metadata: dict[str, Any]


class ProviderLoadRegistry:
    def __init__(self, db_path: Path | None = None) -> None:
        configured = (os.getenv("DENIS_PROVIDER_REGISTRY_DB") or "").strip()
        self.db_path = db_path or (
            Path(configured)
            if configured
            else Path.cwd() / ".sprint_orchestrator" / "provider_registry.db"
        )
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS provider_load_runs(
                    run_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_utc TEXT NOT NULL,
                    finished_utc TEXT NOT NULL DEFAULT '',
                    summary_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS provider_load_steps(
                    step_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    step_no INTEGER NOT NULL,
                    step_total INTEGER NOT NULL,
                    label TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS provider_models(
                    provider TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    request_format TEXT NOT NULL,
                    is_free INTEGER NOT NULL DEFAULT 0,
                    available INTEGER NOT NULL DEFAULT 0,
                    context_length INTEGER NOT NULL DEFAULT 0,
                    supports_tools INTEGER NOT NULL DEFAULT 0,
                    supports_json_mode INTEGER NOT NULL DEFAULT 0,
                    input_schema_json TEXT NOT NULL DEFAULT '{}',
                    output_schema_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    updated_utc TEXT NOT NULL,
                    PRIMARY KEY(provider, model_id)
                );
                CREATE INDEX IF NOT EXISTS idx_provider_models_available
                    ON provider_models(provider, available, is_free);
                """
            )
            conn.commit()

    def start_run(self, provider: str) -> str:
        run_id = f"pload-{_slug(provider)}-{uuid.uuid4().hex[:10]}"
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO provider_load_runs(run_id, provider, status, started_utc, finished_utc, summary_json)
                VALUES(?, ?, ?, ?, '', '{}')
                """,
                (run_id, provider, "running", now),
            )
            conn.commit()
        return run_id

    def log_step(
        self,
        *,
        run_id: str,
        step_no: int,
        label: str,
        status: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        payload_json = json.dumps(payload or {}, ensure_ascii=True, sort_keys=True)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO provider_load_steps(
                    run_id, step_no, step_total, label, status, message, payload_json, created_utc
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, int(step_no), _STEP_TOTAL, label, status, message[:1000], payload_json, _utc_now()),
            )
            conn.commit()

    def finish_run(self, *, run_id: str, status: str, summary: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE provider_load_runs
                SET status=?, finished_utc=?, summary_json=?
                WHERE run_id=?
                """,
                (status, _utc_now(), json.dumps(summary, ensure_ascii=True, sort_keys=True), run_id),
            )
            conn.commit()

    def mark_provider_models_unavailable(self, provider: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE provider_models SET available=0, updated_utc=? WHERE provider=?",
                (_utc_now(), provider),
            )
            conn.commit()

    def upsert_model(
        self,
        *,
        model: DiscoveredModel,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any],
        available: bool = True,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO provider_models(
                    provider, model_id, model_name, request_format, is_free, available,
                    context_length, supports_tools, supports_json_mode,
                    input_schema_json, output_schema_json, metadata_json, updated_utc
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, model_id) DO UPDATE SET
                    model_name=excluded.model_name,
                    request_format=excluded.request_format,
                    is_free=excluded.is_free,
                    available=excluded.available,
                    context_length=excluded.context_length,
                    supports_tools=excluded.supports_tools,
                    supports_json_mode=excluded.supports_json_mode,
                    input_schema_json=excluded.input_schema_json,
                    output_schema_json=excluded.output_schema_json,
                    metadata_json=excluded.metadata_json,
                    updated_utc=excluded.updated_utc
                """,
                (
                    model.provider,
                    model.model_id,
                    model.model_name,
                    model.request_format,
                    1 if model.is_free else 0,
                    1 if available else 0,
                    int(model.context_length),
                    1 if model.supports_tools else 0,
                    1 if model.supports_json_mode else 0,
                    json.dumps(input_schema, ensure_ascii=True, sort_keys=True),
                    json.dumps(output_schema, ensure_ascii=True, sort_keys=True),
                    json.dumps(model.metadata, ensure_ascii=True, sort_keys=True),
                    _utc_now(),
                ),
            )
            conn.commit()

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            run = conn.execute(
                """
                SELECT run_id, provider, status, started_utc, finished_utc, summary_json
                FROM provider_load_runs
                WHERE run_id=?
                """,
                (run_id,),
            ).fetchone()
            if run is None:
                return {}
            steps_rows = conn.execute(
                """
                SELECT step_no, step_total, label, status, message, payload_json, created_utc
                FROM provider_load_steps
                WHERE run_id=?
                ORDER BY step_no ASC, step_id ASC
                """,
                (run_id,),
            ).fetchall()
            steps: list[dict[str, Any]] = []
            for row in steps_rows:
                try:
                    payload = json.loads(str(row["payload_json"] or "{}"))
                except Exception:
                    payload = {}
                steps.append(
                    {
                        "step": int(row["step_no"]),
                        "step_total": int(row["step_total"]),
                        "label": str(row["label"] or ""),
                        "status": str(row["status"] or ""),
                        "message": str(row["message"] or ""),
                        "payload": payload,
                        "timestamp_utc": str(row["created_utc"] or ""),
                    }
                )
            try:
                summary = json.loads(str(run["summary_json"] or "{}"))
            except Exception:
                summary = {}
            return {
                "run_id": str(run["run_id"]),
                "provider": str(run["provider"] or ""),
                "status": str(run["status"] or ""),
                "started_utc": str(run["started_utc"] or ""),
                "finished_utc": str(run["finished_utc"] or ""),
                "summary": summary,
                "steps": steps,
            }

    def list_runs(self, *, provider: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 200))
        out: list[dict[str, Any]] = []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT run_id, provider, status, started_utc, finished_utc, summary_json
                FROM provider_load_runs
                WHERE (? = '' OR provider = ?)
                ORDER BY started_utc DESC
                LIMIT ?
                """,
                (provider or "", provider or "", safe_limit),
            ).fetchall()
            for row in rows:
                try:
                    summary = json.loads(str(row["summary_json"] or "{}"))
                except Exception:
                    summary = {}
                out.append(
                    {
                        "run_id": str(row["run_id"] or ""),
                        "provider": str(row["provider"] or ""),
                        "status": str(row["status"] or ""),
                        "started_utc": str(row["started_utc"] or ""),
                        "finished_utc": str(row["finished_utc"] or ""),
                        "summary": summary,
                    }
                )
        return out

    def list_models(self, *, provider: str | None = None, available_only: bool = True) -> list[dict[str, Any]]:
        query = """
            SELECT provider, model_id, model_name, request_format, is_free, available,
                   context_length, supports_tools, supports_json_mode, metadata_json, updated_utc
            FROM provider_models
            WHERE ( ? = '' OR provider = ? )
        """
        params: list[Any] = [provider or "", provider or ""]
        if available_only:
            query += " AND available = 1"
        query += " ORDER BY provider ASC, is_free DESC, model_name ASC"
        out: list[dict[str, Any]] = []
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            for row in rows:
                try:
                    metadata = json.loads(str(row["metadata_json"] or "{}"))
                except Exception:
                    metadata = {}
                out.append(
                    {
                        "provider": str(row["provider"] or ""),
                        "model_id": str(row["model_id"] or ""),
                        "model_name": str(row["model_name"] or ""),
                        "request_format": str(row["request_format"] or ""),
                        "is_free": bool(int(row["is_free"] or 0)),
                        "available": bool(int(row["available"] or 0)),
                        "context_length": int(row["context_length"] or 0),
                        "supports_tools": bool(int(row["supports_tools"] or 0)),
                        "supports_json_mode": bool(int(row["supports_json_mode"] or 0)),
                        "metadata": metadata,
                        "updated_utc": str(row["updated_utc"] or ""),
                    }
                )
        return out


_PROVIDER_KEY_ENV = {
    "openrouter": "OPENROUTER_API_KEY",
    "groq": "GROQ_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "opencode": "OPENAI_API_KEY",
    "ollama_cloud": "OLLAMA_CLOUD_API_KEY",
    "vllm": "DENIS_VLLM_API_KEY",
    "llama_node1": "DENIS_SPRINT_LLAMA_NODE1_API_KEY",
    "llama_node2": "DENIS_SPRINT_LLAMA_NODE2_API_KEY",
}


def _provider_tags(model_id: str) -> list[str]:
    lower = model_id.lower()
    tags: list[str] = []
    if any(t in lower for t in ["code", "coder", "deepseek"]):
        tags.append("code")
    if any(t in lower for t in ["reason", "reasoning", "think", "qwq", "o1"]):
        tags.append("reasoning")
    if "instruct" in lower:
        tags.append("instruct")
    if not tags:
        tags.append("general")
    return tags


def _discover_openrouter_models(api_key: str) -> tuple[int, list[DiscoveredModel]]:
    data = _http_json(
        url="https://openrouter.ai/api/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    models_data = data.get("data")
    if not isinstance(models_data, list):
        raise RuntimeError("openrouter_invalid_models_payload")

    out: list[DiscoveredModel] = []
    for item in models_data:
        if not isinstance(item, dict):
            continue
        pricing = item.get("pricing") or {}
        prompt_price = _safe_float((pricing or {}).get("prompt"), default=0.0)
        completion_price = _safe_float((pricing or {}).get("completion"), default=0.0)
        is_free = abs(prompt_price) <= _FREE_PRICING_EPSILON and abs(completion_price) <= _FREE_PRICING_EPSILON
        if not is_free:
            continue
        model_id = str(item.get("id") or "").strip()
        if not model_id:
            continue
        supported = item.get("supported_parameters")
        supported_params = [str(x) for x in supported] if isinstance(supported, list) else []
        out.append(
            DiscoveredModel(
                provider="openrouter",
                model_id=model_id,
                model_name=str(item.get("name") or model_id),
                request_format="openai_chat",
                is_free=True,
                context_length=int(item.get("context_length") or 0),
                supports_tools="tools" in supported_params,
                supports_json_mode=any(x in supported_params for x in ("response_format", "json_schema")),
                tags=_provider_tags(model_id),
                metadata={
                    "source": "openrouter_api",
                    "pricing_prompt": prompt_price,
                    "pricing_completion": completion_price,
                },
            )
        )
    return len(models_data), out


def _discover_groq_models(api_key: str) -> tuple[int, list[DiscoveredModel]]:
    data = _http_json(
        url="https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    models_data = data.get("data")
    if not isinstance(models_data, list):
        raise RuntimeError("groq_invalid_models_payload")

    out: list[DiscoveredModel] = []
    for item in models_data:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "").strip()
        if not model_id:
            continue
        out.append(
            DiscoveredModel(
                provider="groq",
                model_id=model_id,
                model_name=str(item.get("id") or model_id),
                request_format="openai_chat",
                is_free=True,
                context_length=0,
                supports_tools=("70b" in model_id.lower() or "tool" in model_id.lower()),
                supports_json_mode=True,
                tags=_provider_tags(model_id),
                metadata={"source": "groq_api"},
            )
        )
    return len(models_data), out


def _derive_models_endpoint(chat_endpoint: str) -> str:
    value = (chat_endpoint or "").strip()
    if not value:
        return ""
    lower = value.lower()
    for suffix in ["/v1/chat/completions", "/chat/completions", "/v1/completions", "/completions"]:
        if lower.endswith(suffix):
            return value[: -len(suffix)] + "/v1/models"
    if value.endswith("/v1"):
        return value + "/models"
    if value.endswith("/"):
        return value + "v1/models"
    return value + "/v1/models"


def _discover_openai_compatible_models(
    *,
    provider: str,
    endpoint: str,
    api_key: str = "",
) -> tuple[int, list[DiscoveredModel]]:
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = _http_json(url=endpoint, headers=headers)
    models_data = data.get("data")
    if not isinstance(models_data, list):
        raise RuntimeError(f"{provider}_invalid_models_payload")
    out: list[DiscoveredModel] = []
    for item in models_data:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "").strip()
        if not model_id:
            continue
        out.append(
            DiscoveredModel(
                provider=provider,
                model_id=model_id,
                model_name=str(item.get("id") or model_id),
                request_format="openai_chat",
                is_free=True,
                context_length=0,
                supports_tools=True,
                supports_json_mode=True,
                tags=_provider_tags(model_id),
                metadata={"source": f"{provider}_models_endpoint"},
            )
        )
    return len(models_data), out


def discover_provider_models(
    *,
    provider: str,
    api_key: str = "",
) -> tuple[int, list[DiscoveredModel]]:
    provider_norm = _slug(provider)
    if provider_norm == "openrouter":
        return _discover_openrouter_models(api_key)
    if provider_norm == "groq":
        return _discover_groq_models(api_key)
    if provider_norm == "vllm":
        endpoint = _derive_models_endpoint(
            os.getenv("DENIS_VLLM_URL", "http://10.10.10.2:8084/v1/chat/completions")
        )
        return _discover_openai_compatible_models(provider="vllm", endpoint=endpoint, api_key=api_key)
    if provider_norm == "llama_node1":
        mode = (os.getenv("DENIS_SPRINT_LLAMA_NODE1_MODE") or "direct").strip().lower()
        if mode == "direct":
            endpoint = _derive_models_endpoint(
                os.getenv("DENIS_SPRINT_LLAMA_NODE1_URL", "http://10.10.10.1:8084/v1/chat/completions")
            )
            if endpoint:
                try:
                    return _discover_openai_compatible_models(
                        provider="llama_node1",
                        endpoint=endpoint,
                        api_key=api_key,
                    )
                except Exception:
                    pass
        model_id = (os.getenv("DENIS_SPRINT_LLAMA_NODE1_MODEL") or "denis-node1").strip()
        return 1, [
            DiscoveredModel(
                provider="llama_node1",
                model_id=model_id,
                model_name=model_id,
                request_format="openai_chat",
                is_free=True,
                context_length=0,
                supports_tools=True,
                supports_json_mode=True,
                tags=_provider_tags(model_id),
                metadata={"source": "llama_node1_env_fallback", "mode": mode},
            )
        ]
    if provider_norm == "llama_node2":
        mode = (os.getenv("DENIS_SPRINT_LLAMA_NODE2_MODE") or "direct").strip().lower()
        if mode == "direct":
            endpoint = _derive_models_endpoint(
                os.getenv("DENIS_SPRINT_LLAMA_NODE2_URL", "http://10.10.10.2:8084/v1/chat/completions")
            )
            if endpoint:
                try:
                    return _discover_openai_compatible_models(
                        provider="llama_node2",
                        endpoint=endpoint,
                        api_key=api_key,
                    )
                except Exception:
                    pass
        model_id = (os.getenv("DENIS_SPRINT_LLAMA_NODE2_MODEL") or "denis-node2").strip()
        return 1, [
            DiscoveredModel(
                provider="llama_node2",
                model_id=model_id,
                model_name=model_id,
                request_format="openai_chat",
                is_free=True,
                context_length=0,
                supports_tools=True,
                supports_json_mode=True,
                tags=_provider_tags(model_id),
                metadata={"source": "llama_node2_env_fallback", "mode": mode},
            )
        ]
    if provider_norm == "legacy_core":
        model_id = (os.getenv("LLM_MODEL") or "denis-core").strip()
        return 1, [
            DiscoveredModel(
                provider="legacy_core",
                model_id=model_id,
                model_name=model_id,
                request_format="openai_chat",
                is_free=True,
                context_length=0,
                supports_tools=True,
                supports_json_mode=True,
                tags=["general"],
                metadata={"source": "legacy_core_env"},
            )
        ]
    if provider_norm == "claude":
        model_id = (os.getenv("DENIS_CLAUDE_MODEL") or "claude-3-5-sonnet-20241022").strip()
        return 1, [
            DiscoveredModel(
                provider="claude",
                model_id=model_id,
                model_name=model_id,
                request_format="anthropic_messages",
                is_free=False,
                context_length=0,
                supports_tools=False,
                supports_json_mode=False,
                tags=["general"],
                metadata={"source": "claude_env"},
            )
        ]
    if provider_norm == "opencode":
        base = (os.getenv("LLM_BASE_URL") or "").strip()
        endpoint = _derive_models_endpoint(base)
        if not endpoint:
            raise RuntimeError("opencode_models_endpoint_missing")
        return _discover_openai_compatible_models(provider="opencode", endpoint=endpoint, api_key=api_key)
    raise RuntimeError(f"provider_not_supported_for_discovery:{provider}")


def _build_input_schema(model: DiscoveredModel) -> dict[str, Any]:
    if model.request_format == "anthropic_messages":
        schema: dict[str, Any] = {
            "type": "object",
            "required": ["model", "messages"],
            "properties": {
                "model": {"type": "string", "const": model.model_id},
                "messages": {"type": "array"},
                "max_tokens": {"type": "integer", "minimum": 1},
                "temperature": {"type": "number", "minimum": 0.0, "maximum": 2.0},
                "system": {"type": "string"},
            },
        }
    else:
        schema = {
            "type": "object",
            "required": ["model", "messages"],
            "properties": {
                "model": {"type": "string", "const": model.model_id},
                "messages": {"type": "array"},
                "temperature": {"type": "number", "minimum": 0.0, "maximum": 2.0},
                "max_tokens": {"type": "integer", "minimum": 1},
                "stream": {"type": "boolean"},
            },
        }
        if model.supports_tools:
            schema["properties"]["tools"] = {"type": "array"}
        if model.supports_json_mode:
            schema["properties"]["response_format"] = {"type": "object"}
    return schema


def _build_output_schema(model: DiscoveredModel) -> dict[str, Any]:
    if model.request_format == "anthropic_messages":
        return {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "content": {"type": "array"},
                "usage": {"type": "object"},
                "stop_reason": {"type": "string"},
            },
        }
    return {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "choices": {"type": "array"},
            "usage": {"type": "object"},
        },
    }


def run_provider_load(
    *,
    provider: str,
    run_id: str | None = None,
    api_key: str = "",
    persist_env: bool = True,
    create_backup: bool = True,
    extra_env: dict[str, str] | None = None,
    env_writer: Callable[[dict[str, str], bool], str | None] | None = None,
    registry: ProviderLoadRegistry | None = None,
) -> dict[str, Any]:
    provider_norm = _slug(provider)
    if not provider_norm:
        raise RuntimeError("invalid_provider")

    reg = registry or ProviderLoadRegistry()
    active_run_id = run_id or reg.start_run(provider_norm)
    discovered_total = 0
    free_models: list[DiscoveredModel] = []
    updated_env_keys: list[str] = []
    backup_file = ""

    key_env_var = _PROVIDER_KEY_ENV.get(provider_norm, "")
    effective_key = (api_key or "").strip()
    if not effective_key and key_env_var:
        effective_key = (os.getenv(key_env_var) or "").strip()

    try:
        # 1/5: registro api key confirmado
        key_required = provider_norm in {"openrouter", "groq", "claude", "opencode", "ollama_cloud"}
        if key_required and not effective_key:
            raise RuntimeError(f"api_key_required:{provider_norm}")
        reg.log_step(
            run_id=active_run_id,
            step_no=1,
            label="Registro api key",
            status="ok",
            message=f"1/5 - Registro api key [confirmado {provider_norm}]",
            payload={"provider": provider_norm, "api_key_masked": _mask_secret(effective_key)},
        )

        # 2/5: validar + registrar en .env
        discovered_total, _ = discover_provider_models(provider=provider_norm, api_key=effective_key)
        env_updates = dict(extra_env or {})
        if key_env_var and effective_key:
            env_updates[key_env_var] = effective_key
        if persist_env and env_updates:
            if env_writer is None:
                raise RuntimeError("env_writer_required_for_persist")
            backup = env_writer(env_updates, bool(create_backup))
            backup_file = backup or ""
            updated_env_keys = sorted(env_updates.keys())
        reg.log_step(
            run_id=active_run_id,
            step_no=2,
            label="Validacion y registro",
            status="ok",
            message="2/5 - API key valida, procedemos al registro [.env actualizado]",
            payload={
                "provider": provider_norm,
                "discovered_raw": int(discovered_total),
                "persist_env": bool(persist_env),
                "updated_keys": updated_env_keys,
                "backup_file": backup_file,
            },
        )

        # 3/5: discovery free models
        discovered_total, free_models = discover_provider_models(provider=provider_norm, api_key=effective_key)
        reg.log_step(
            run_id=active_run_id,
            step_no=3,
            label="Discovery modelos gratuitos",
            status="ok",
            message="3/5 - Obteniendo lista actualizada de modelos gratuitos [discover+registro]",
            payload={
                "provider": provider_norm,
                "raw_models": int(discovered_total),
                "free_models": len(free_models),
            },
        )

        # 4/5: adaptacion de llamadas + schemas por modelo (serial)
        reg.mark_provider_models_unavailable(provider_norm)
        for model in free_models:
            input_schema = _build_input_schema(model)
            output_schema = _build_output_schema(model)
            reg.upsert_model(
                model=model,
                input_schema=input_schema,
                output_schema=output_schema,
                available=True,
            )
        reg.log_step(
            run_id=active_run_id,
            step_no=4,
            label="Adaptacion JSON y schema",
            status="ok",
            message="4/5 - Adaptacion de llamadas y JSON [serializado + schema en BBDD]",
            payload={
                "provider": provider_norm,
                "schemas_written": len(free_models),
                "request_format": free_models[0].request_format if free_models else "",
            },
        )

        # 5/5: cierre
        summary = {
            "provider": provider_norm,
            "models_registered": len(free_models),
            "models_discovered_total": int(discovered_total),
            "updated_env_keys": updated_env_keys,
            "backup_file": backup_file,
            "status": "ok",
        }
        reg.log_step(
            run_id=active_run_id,
            step_no=5,
            label="Registro completo",
            status="ok",
            message=(
                "5/5 - Registro completo. "
                f"{len(free_models)}/{discovered_total} modelos registrados para {provider_norm}"
            ),
            payload=summary,
        )
        reg.finish_run(run_id=active_run_id, status="ok", summary=summary)
        return reg.get_run(active_run_id)
    except Exception as exc:
        message = str(exc)[:300]
        reg.log_step(
            run_id=active_run_id,
            step_no=5,
            label="Registro completo",
            status="error",
            message=f"5/5 - Registro incompleto para {provider_norm}: {message}",
            payload={"error": message},
        )
        reg.finish_run(
            run_id=active_run_id,
            status="error",
            summary={"provider": provider_norm, "status": "error", "error": message},
        )
        return reg.get_run(active_run_id)
