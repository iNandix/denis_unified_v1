#!/usr/bin/env python3
"""ModelCaller — Executes model calls with fallback chain."""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

FALLBACK_CHAIN = {
    "groq": ["llama_local"],
    "openrouter": ["groq", "llama_local"],
    "claude": ["openrouter", "groq", "llama_local"],
    "llama_local": [],
}


@dataclass
class ModelResponse:
    text: str
    model: str
    tokens_used: int = 0
    latency_ms: float = 0.0
    used_fallback: bool = False
    error: str = ""


def call_model(
    routed_request,
    system_prompt: str,
    user_message: str,
    max_tokens: int = 1024,
) -> ModelResponse:
    """Execute model call with fallback chain."""
    model = getattr(routed_request, "model", None) or "groq"

    intent = getattr(routed_request, "intent", "unknown")
    repo_id = getattr(routed_request, "repo_id", "")
    repo_name = getattr(routed_request, "repo_name", "")
    branch = getattr(routed_request, "branch", "")

    enhanced_prompt = _enhance_prompt(system_prompt, intent, repo_id, repo_name, branch)

    result = _try_model_chain(model, enhanced_prompt, user_message, max_tokens)

    return result


def _enhance_prompt(prompt: str, intent: str, repo_id: str, repo_name: str, branch: str) -> str:
    """Enhance system prompt with context."""
    context_parts = [prompt]

    if repo_name:
        context_parts.append(f"Repository: {repo_name}")
    if branch:
        context_parts.append(f"Branch: {branch}")
    if intent:
        context_parts.append(f"Intent: {intent}")

    return "\n".join(context_parts)


def _try_model_chain(
    model: str,
    system_prompt: str,
    user_message: str,
    max_tokens: int,
    tried_models: List[str] = None,
) -> ModelResponse:
    """Try model with fallback chain."""
    if tried_models is None:
        tried_models = []

    tried_models.append(model)

    result = _call_model(model, system_prompt, user_message, max_tokens)

    if result.error and model != "llama_local":
        fallbacks = FALLBACK_CHAIN.get(model, ["llama_local"])
        for fallback in fallbacks:
            if fallback not in tried_models:
                logger.info(f"{model} failed, trying fallback: {fallback}")
                result = _try_model_chain(
                    fallback, system_prompt, user_message, max_tokens, tried_models
                )
                result.used_fallback = True
                if not result.error:
                    return result

    if result.error:
        result.text = f"[Error: {result.error[:100]}]"

    return result


def _call_model(
    model: str, system_prompt: str, user_message: str, max_tokens: int
) -> ModelResponse:
    """Call a specific model."""
    if model.startswith("groq/"):
        return _call_groq(model, system_prompt, user_message, max_tokens)

    if model.startswith("openrouter/"):
        return _call_openrouter(model, system_prompt, user_message, max_tokens)

    if model in ["groq", "llama_local", "claude"]:
        if model == "groq":
            return _call_groq(
                "groq/llama-3.1-70b-versatile", system_prompt, user_message, max_tokens
            )
        elif model == "claude":
            return _call_openrouter(
                "openrouter/anthropic/claude-3.5-sonnet", system_prompt, user_message, max_tokens
            )

    return _call_llama_local(system_prompt, user_message, max_tokens)


def _call_groq(model: str, system_prompt: str, user_message: str, max_tokens: int) -> ModelResponse:
    """Call Groq API."""
    try:
        from groq import Groq

        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key:
            return ModelResponse(text="", model=model, error="GROQ_API_KEY not set")

        client = Groq(api_key=api_key)

        actual_model = model.replace("groq/", "") if model.startswith("groq/") else model

        response = client.chat.completions.create(
            model=actual_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=max_tokens,
            timeout=15,
        )

        return ModelResponse(
            text=response.choices[0].message.content or "",
            model=model,
            tokens_used=response.usage.total_tokens if response.usage else 0,
            latency_ms=0,
        )
    except Exception as e:
        return ModelResponse(text="", model=model, error=str(e))


def _call_openrouter(
    model: str, system_prompt: str, user_message: str, max_tokens: int
) -> ModelResponse:
    """Call OpenRouter API."""
    try:
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not api_key:
            return ModelResponse(text="", model=model, error="OPENROUTER_API_KEY not set")

        actual_model = (
            model.replace("openrouter/", "") if model.startswith("openrouter/") else model
        )

        payload = {
            "model": actual_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": max_tokens,
        }

        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://denis.local",
                "X-Title": "Denis",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=20) as response:
            data = json.loads(response.read())
            return ModelResponse(
                text=data["choices"][0]["message"]["content"],
                model=model,
                tokens_used=data.get("usage", {}).get("total_tokens", 0),
                latency_ms=0,
            )
    except Exception as e:
        return ModelResponse(text="", model=model, error=str(e))


def _call_llama_local(system_prompt: str, user_message: str, max_tokens: int) -> ModelResponse:
    """Call local llama server (service 8084)."""
    try:
        import requests

        url = "http://localhost:8084/inference/local"
        payload = {
            "prompt": f"{system_prompt}\n\nUser: {user_message}",
            "max_tokens": max_tokens,
        }

        response = requests.post(url, json=payload, timeout=30)

        if response.ok:
            data = response.json()
            return ModelResponse(
                text=data.get("text", data.get("response", "")),
                model="llama_local",
                tokens_used=data.get("tokens_used", 0),
                latency_ms=data.get("latency_ms", 0),
            )
        else:
            return ModelResponse(
                text="[Fallback unavailable]",
                model="llama_local",
                error=f"Status {response.status_code}",
            )
    except Exception as e:
        return ModelResponse(
            text="[No model available]",
            model="llama_local",
            error=str(e),
        )


def get_available_models() -> Dict[str, bool]:
    """Check which models are available."""
    models = {
        "groq": bool(os.getenv("GROQ_API_KEY")),
        "openrouter": bool(os.getenv("OPENROUTER_API_KEY")),
        "llama_local": _check_llama_local(),
    }
    return models


def _check_llama_local() -> bool:
    """Check if llama local is available."""
    try:
        import requests

        r = requests.get("http://localhost:8084/health", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


__all__ = ["ModelResponse", "call_model", "get_available_models"]
