"""Provider loading for sprint workers (without exposing secrets)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
import shutil
import shlex
from typing import Any

from .config import SprintOrchestratorConfig


_ENV_LINE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$")


@dataclass(frozen=True)
class ProviderStatus:
    provider: str
    mode: str
    request_format: str
    configured: bool
    missing_env: list[str]
    endpoint: str
    queue: str
    notes: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "mode": self.mode,
            "request_format": self.request_format,
            "configured": self.configured,
            "missing_env": list(self.missing_env),
            "endpoint": self.endpoint,
            "queue": self.queue,
            "notes": self.notes,
        }


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        match = _ENV_LINE_RE.match(line)
        if not match:
            continue
        key, value = match.group(1), match.group(2)
        if " #" in value and not value.startswith(("'", '"')):
            value = value.split(" #", 1)[0]
        value = value.strip().strip("'").strip('"')
        values[key] = value
    return values


def merged_env(config: SprintOrchestratorConfig) -> dict[str, str]:
    env = dict(os.environ)
    project_env = _load_env_file(config.projects_scan_root / ".env")
    for key, value in project_env.items():
        if key not in env:
            env[key] = value
    return env


def _present(env: dict[str, str], key: str) -> bool:
    return bool((env.get(key) or "").strip())


def _missing(env: dict[str, str], required: list[str]) -> list[str]:
    return [key for key in required if not _present(env, key)]


def _tool_available(name: str) -> bool:
    if not name.strip():
        return False
    executable = shlex.split(name)[0]
    return shutil.which(executable) is not None


def load_provider_statuses(config: SprintOrchestratorConfig) -> list[ProviderStatus]:
    env = merged_env(config)
    statuses: list[ProviderStatus] = []

    codex_cmd = env.get("DENIS_SPRINT_CODEX_CMD", "codex").strip()
    statuses.append(
        ProviderStatus(
            provider="codex",
            mode="terminal",
            request_format="terminal",
            configured=_tool_available(codex_cmd),
            missing_env=[],
            endpoint="",
            queue="",
            notes=f"cmd={codex_cmd}",
        )
    )

    claude_cmd = env.get("DENIS_SPRINT_CLAUDE_CMD", "claude").strip()
    claude_missing = _missing(env, ["ANTHROPIC_API_KEY"])
    statuses.append(
        ProviderStatus(
            provider="claude_code",
            mode="terminal",
            request_format="terminal",
            configured=_tool_available(claude_cmd) and not claude_missing,
            missing_env=claude_missing,
            endpoint="",
            queue="",
            notes=f"cmd={claude_cmd}",
        )
    )

    opencode_missing = _missing(env, ["OPENAI_API_KEY"])
    opencode_endpoint = (env.get("LLM_BASE_URL") or "").strip()
    statuses.append(
        ProviderStatus(
            provider="opencode",
            mode="api",
            request_format="openai_chat",
            configured=not opencode_missing and bool(opencode_endpoint),
            missing_env=opencode_missing + (["LLM_BASE_URL"] if not opencode_endpoint else []),
            endpoint=opencode_endpoint,
            queue="",
            notes="uses LLM_BASE_URL + OPENAI_API_KEY",
        )
    )

    statuses.append(
        ProviderStatus(
            provider="legacy_core",
            mode="local",
            request_format="openai_chat",
            configured=True,
            missing_env=[],
            endpoint=(env.get("DENIS_MASTER_URL") or "").strip(),
            queue="",
            notes="local fallback provider",
        )
    )

    groq_missing = _missing(env, ["GROQ_API_KEY"])
    groq_endpoint = (env.get("DENIS_GROQ_URL") or "https://api.groq.com/openai/v1/chat/completions").strip()
    statuses.append(
        ProviderStatus(
            provider="groq",
            mode="api",
            request_format="openai_chat",
            configured=not groq_missing,
            missing_env=groq_missing,
            endpoint=groq_endpoint,
            queue="",
            notes="",
        )
    )

    openrouter_missing = _missing(env, ["OPENROUTER_API_KEY"])
    openrouter_endpoint = (
        env.get("DENIS_OPENROUTER_URL") or "https://openrouter.ai/api/v1/chat/completions"
    ).strip()
    statuses.append(
        ProviderStatus(
            provider="openrouter",
            mode="api",
            request_format="openai_chat",
            configured=not openrouter_missing,
            missing_env=openrouter_missing,
            endpoint=openrouter_endpoint,
            queue="",
            notes="",
        )
    )

    claude_missing = _missing(env, ["ANTHROPIC_API_KEY"])
    claude_endpoint = (env.get("DENIS_ANTHROPIC_URL") or "https://api.anthropic.com/v1/messages").strip()
    statuses.append(
        ProviderStatus(
            provider="claude",
            mode="api",
            request_format="anthropic_messages",
            configured=not claude_missing,
            missing_env=claude_missing,
            endpoint=claude_endpoint,
            queue="",
            notes="",
        )
    )

    vllm_endpoint = (env.get("DENIS_VLLM_URL") or "http://10.10.10.2:9999/v1/chat/completions").strip()
    statuses.append(
        ProviderStatus(
            provider="vllm",
            mode="api",
            request_format="openai_chat",
            configured=bool(vllm_endpoint),
            missing_env=[] if vllm_endpoint else ["DENIS_VLLM_URL"],
            endpoint=vllm_endpoint,
            queue="",
            notes="local vLLM endpoint",
        )
    )

    ollama_missing = _missing(env, ["OLLAMA_CLOUD_API_KEY"])
    ollama_endpoint = (env.get("DENIS_OLLAMA_CLOUD_URL") or "").strip()
    statuses.append(
        ProviderStatus(
            provider="ollama_cloud",
            mode="api",
            request_format="openai_chat",
            configured=not ollama_missing and bool(ollama_endpoint),
            missing_env=ollama_missing + (["DENIS_OLLAMA_CLOUD_URL"] if not ollama_endpoint else []),
            endpoint=ollama_endpoint,
            queue="",
            notes="",
        )
    )

    statuses.extend(
        _load_llama_worker_statuses(
            env=env,
            node="node1",
            default_queue="sprint:llama_node1",
            default_endpoint="http://10.10.10.1:8084/v1/chat/completions",
        )
    )
    statuses.extend(
        _load_llama_worker_statuses(
            env=env,
            node="node2",
            default_queue="sprint:llama_node2",
            default_endpoint="http://10.10.10.2:8084/v1/chat/completions",
        )
    )

    celery_missing = _missing(env, ["REDIS_URL"])
    statuses.append(
        ProviderStatus(
            provider="celery_crewai",
            mode="worker",
            request_format="celery_task",
            configured=not celery_missing,
            missing_env=celery_missing,
            endpoint="",
            queue=(env.get("DENIS_SPRINT_CREW_QUEUE") or "sprint:crewai").strip(),
            notes="recommended for distributed execution",
        )
    )

    return statuses


def _load_llama_worker_statuses(
    *,
    env: dict[str, str],
    node: str,
    default_queue: str,
    default_endpoint: str,
) -> list[ProviderStatus]:
    node_upper = node.upper()
    mode_key = f"DENIS_SPRINT_LLAMA_{node_upper}_MODE"
    endpoint_key = f"DENIS_SPRINT_LLAMA_{node_upper}_URL"
    queue_key = f"DENIS_SPRINT_LLAMA_{node_upper}_QUEUE"

    mode = (env.get(mode_key) or "celery").strip().lower()
    endpoint = (env.get(endpoint_key) or default_endpoint).strip()
    queue = (env.get(queue_key) or default_queue).strip()

    if mode not in {"celery", "direct"}:
        return [
            ProviderStatus(
                provider=f"llama_{node}",
                mode=mode,
                request_format="celery_task",
                configured=False,
                missing_env=[mode_key],
                endpoint=endpoint,
                queue=queue,
                notes="mode must be 'celery' or 'direct'",
            )
        ]

    if mode == "celery":
        missing = _missing(env, ["REDIS_URL"])
        return [
            ProviderStatus(
                provider=f"llama_{node}",
                mode=mode,
                request_format="celery_task",
                configured=not missing,
                missing_env=missing,
                endpoint="",
                queue=queue,
                notes="routes to Celery/CrewAI worker queue",
            )
        ]

    endpoint_missing: list[str] = []
    if not endpoint:
        endpoint_missing.append(endpoint_key)
    return [
        ProviderStatus(
            provider=f"llama_{node}",
            mode=mode,
            request_format="openai_chat",
            configured=not endpoint_missing,
            missing_env=endpoint_missing,
            endpoint=endpoint,
            queue="",
            notes="direct llama.cpp HTTP endpoint",
        )
    ]


def configured_provider_ids(statuses: list[ProviderStatus]) -> list[str]:
    return [item.provider for item in statuses if item.configured]


def provider_status_map(statuses: list[ProviderStatus]) -> dict[str, ProviderStatus]:
    return {item.provider: item for item in statuses}


def ordered_configured_provider_ids(
    *,
    config: SprintOrchestratorConfig,
    statuses: list[ProviderStatus],
) -> list[str]:
    configured = configured_provider_ids(statuses)
    configured_set = set(configured)

    ordered: list[str] = []
    for provider_id in config.provider_pool:
        if provider_id in configured_set and provider_id not in ordered:
            ordered.append(provider_id)
    for provider_id in configured:
        if provider_id not in ordered:
            ordered.append(provider_id)

    if config.pin_legacy_first and "legacy_core" in ordered:
        ordered = ["legacy_core"] + [item for item in ordered if item != "legacy_core"]
    return ordered
