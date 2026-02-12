"""Universal payload adapter for heterogeneous model APIs."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
import urllib.error
import urllib.request

from .config import SprintOrchestratorConfig
from .providers import ProviderStatus, merged_env


@dataclass(frozen=True)
class ProviderRequest:
    provider: str
    endpoint: str
    method: str
    headers: dict[str, str]
    payload: dict[str, Any]
    request_format: str

    def as_dict(self, redact_headers: bool = True) -> dict[str, Any]:
        headers = dict(self.headers)
        if redact_headers and "Authorization" in headers:
            headers["Authorization"] = "Bearer ***"
        if redact_headers and "x-api-key" in headers:
            headers["x-api-key"] = "***"
        return {
            "provider": self.provider,
            "endpoint": self.endpoint,
            "method": self.method,
            "headers": headers,
            "payload": self.payload,
            "request_format": self.request_format,
        }


def _normalize_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for msg in messages:
        role = str(msg.get("role") or "user").strip().lower()
        if role not in {"system", "user", "assistant", "tool"}:
            role = "user"
        content = str(msg.get("content") or "").strip()
        if not content:
            continue
        out.append({"role": role, "content": content})
    return out or [{"role": "user", "content": "Hello"}]


def _as_anthropic_messages(messages: list[dict[str, str]]) -> tuple[str | None, list[dict[str, Any]]]:
    system_parts: list[str] = []
    conversational: list[dict[str, Any]] = []
    for msg in _normalize_messages(messages):
        if msg["role"] == "system":
            system_parts.append(msg["content"])
            continue
        role = msg["role"] if msg["role"] in {"user", "assistant"} else "user"
        conversational.append({"role": role, "content": msg["content"]})
    if not conversational:
        conversational = [{"role": "user", "content": "Hello"}]
    system_prompt = "\n\n".join(system_parts).strip() if system_parts else None
    return system_prompt, conversational


def _resolve_model(provider: str, env: dict[str, str]) -> str:
    mapping = {
        "denis_canonical": ("DENIS_CANONICAL_MODEL", "denis-cognitive"),
        "groq": ("DENIS_GROQ_MODEL", "llama-3.1-70b-versatile"),
        "openrouter": ("DENIS_OPENROUTER_MODEL", "openai/gpt-4o-mini"),
        "claude": ("DENIS_CLAUDE_MODEL", "claude-3-5-sonnet-20241022"),
        "vllm": ("DENIS_VLLM_MODEL", "deepseek-coder"),
        "opencode": ("LLM_MODEL", "gpt-4o-mini"),
        "legacy_core": ("LLM_MODEL", "denis-core"),
        "ollama_cloud": ("OLLAMA_CLOUD_MODEL", "llama3.1:8b"),
        "llama_node1": ("DENIS_SPRINT_LLAMA_NODE1_MODEL", "denis-node1"),
        "llama_node2": ("DENIS_SPRINT_LLAMA_NODE2_MODEL", "denis-node2"),
    }
    key, default = mapping.get(provider, ("LLM_MODEL", "gpt-4o-mini"))
    return (env.get(key) or default).strip()


def _resolve_endpoint(provider: str, status: ProviderStatus, env: dict[str, str]) -> str:
    explicit = (status.endpoint or "").strip()
    if explicit:
        return explicit
    defaults = {
        "denis_canonical": (env.get("DENIS_CANONICAL_URL") or "http://127.0.0.1:9999/v1/chat/completions").strip(),
        "groq": "https://api.groq.com/openai/v1/chat/completions",
        "openrouter": "https://openrouter.ai/api/v1/chat/completions",
        "claude": "https://api.anthropic.com/v1/messages",
        "vllm": "http://10.10.10.2:9999/v1/chat/completions",
        "opencode": (env.get("LLM_BASE_URL") or "").strip(),
        "legacy_core": (env.get("DENIS_MASTER_URL") or "http://127.0.0.1:8084/v1/chat/completions").strip(),
        "ollama_cloud": (env.get("DENIS_OLLAMA_CLOUD_URL") or "").strip(),
        "llama_node1": (env.get("DENIS_SPRINT_LLAMA_NODE1_URL") or "http://10.10.10.1:8084/v1/chat/completions").strip(),
        "llama_node2": (env.get("DENIS_SPRINT_LLAMA_NODE2_URL") or "http://10.10.10.2:8084/v1/chat/completions").strip(),
    }
    return defaults.get(provider, "").strip()


def _openai_payload(
    *,
    provider: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int | None,
    stream: bool,
    tools: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": _normalize_messages(messages),
        "temperature": temperature,
        "stream": stream,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if tools:
        payload["tools"] = tools
    if provider == "ollama_cloud":
        payload.setdefault("options", {})
    return payload


def _anthropic_payload(
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int | None,
) -> dict[str, Any]:
    system_prompt, conv = _as_anthropic_messages(messages)
    payload: dict[str, Any] = {
        "model": model,
        "messages": conv,
        "temperature": temperature,
        "max_tokens": max_tokens or 512,
    }
    if system_prompt:
        payload["system"] = system_prompt
    return payload


def build_provider_request(
    *,
    config: SprintOrchestratorConfig,
    status: ProviderStatus,
    messages: list[dict[str, str]],
    temperature: float = 0.2,
    max_tokens: int | None = None,
    stream: bool = False,
    tools: list[dict[str, Any]] | None = None,
) -> ProviderRequest:
    env = merged_env(config)
    provider = status.provider
    endpoint = _resolve_endpoint(provider, status, env)
    model = _resolve_model(provider, env)

    if status.request_format == "anthropic_messages":
        payload = _anthropic_payload(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        headers = {
            "content-type": "application/json",
            "x-api-key": (env.get("ANTHROPIC_API_KEY") or "").strip(),
            "anthropic-version": "2023-06-01",
        }
    elif status.request_format == "openai_chat":
        payload = _openai_payload(
            provider=provider,
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            tools=tools,
        )
        headers = {"Content-Type": "application/json"}
        token_map = {
            "denis_canonical": "DENIS_CANONICAL_API_KEY",
            "groq": "GROQ_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "opencode": "OPENAI_API_KEY",
            "ollama_cloud": "OLLAMA_CLOUD_API_KEY",
            "legacy_core": "LLM_API_KEY",
            "vllm": "DENIS_VLLM_API_KEY",
            "llama_node1": "DENIS_SPRINT_LLAMA_NODE1_API_KEY",
            "llama_node2": "DENIS_SPRINT_LLAMA_NODE2_API_KEY",
        }
        token_var = token_map.get(provider)
        token = (env.get(token_var) or "").strip() if token_var else ""
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if provider == "openrouter":
            site_url = (env.get("DENIS_OPENROUTER_SITE_URL") or "").strip()
            site_name = (env.get("DENIS_OPENROUTER_SITE_NAME") or "denis-unified-v1").strip()
            if site_url:
                headers["HTTP-Referer"] = site_url
            if site_name:
                headers["X-Title"] = site_name
    else:
        raise ValueError(
            f"Provider {provider} is request_format={status.request_format}; direct HTTP invoke is not supported"
        )

    if not endpoint:
        raise ValueError(f"Provider {provider} has no endpoint configured")

    return ProviderRequest(
        provider=provider,
        endpoint=endpoint,
        method="POST",
        headers=headers,
        payload=payload,
        request_format=status.request_format,
    )


def _parse_openai_response(data: dict[str, Any]) -> dict[str, Any]:
    choices = data.get("choices") or []
    first = choices[0] if choices else {}
    message = first.get("message") if isinstance(first, dict) else {}
    content = ""
    if isinstance(message, dict):
        content = str(message.get("content") or "")
    elif isinstance(first, dict):
        content = str(first.get("text") or "")

    usage = data.get("usage") or {}
    return {
        "text": content.strip(),
        "finish_reason": first.get("finish_reason") if isinstance(first, dict) else None,
        "tool_calls": (message.get("tool_calls") if isinstance(message, dict) else None) or [],
        "input_tokens": int(usage.get("prompt_tokens") or 0),
        "output_tokens": int(usage.get("completion_tokens") or 0),
        "raw": data,
    }


def _parse_anthropic_response(data: dict[str, Any]) -> dict[str, Any]:
    text_parts: list[str] = []
    for block in data.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            text_parts.append(str(block.get("text") or ""))
    usage = data.get("usage") or {}
    return {
        "text": "".join(text_parts).strip(),
        "finish_reason": data.get("stop_reason"),
        "tool_calls": [],
        "input_tokens": int(usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "raw": data,
    }


def parse_provider_response(status: ProviderStatus, data: dict[str, Any]) -> dict[str, Any]:
    if status.request_format == "anthropic_messages":
        return _parse_anthropic_response(data)
    return _parse_openai_response(data)


def invoke_provider_request(request: ProviderRequest, timeout_sec: float = 30.0) -> dict[str, Any]:
    body = json.dumps(request.payload).encode("utf-8")
    req = urllib.request.Request(
        url=request.endpoint,
        method=request.method,
        headers=request.headers,
        data=body,
    )

    try:
        with urllib.request.urlopen(req, timeout=max(0.5, timeout_sec)) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            status = int(resp.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore") if exc.fp else str(exc)
        raise RuntimeError(f"http_error_{exc.code}:{raw[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"network_error:{exc}") from exc

    try:
        data = json.loads(raw)
    except Exception as exc:
        raise RuntimeError(f"invalid_json_response:{raw[:200]}") from exc

    return {"http_status": status, "data": data}
