from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
import urllib.error
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ModelResponse:
    text: str
    model: str
    tokens_used: int
    latency_ms: float
    used_fallback: bool = False
    error: str = ""


def _call_groq(
    model_name: str, system_prompt: str, user_message: str, max_tokens: int
) -> ModelResponse:
    t0 = time.time()
    try:
        from groq import Groq
    except ImportError as exc:
        raise RuntimeError("groq package not installed — pip install groq") from exc
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set")
    client = Groq(api_key=api_key)
    r = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        max_tokens=max_tokens,
        timeout=15,
    )
    text = r.choices[0].message.content or ""
    tokens = r.usage.total_tokens if r.usage else len(text.split())
    return ModelResponse(
        text=text,
        model=f"groq/{model_name}",
        tokens_used=tokens,
        latency_ms=(time.time() - t0) * 1000,
    )


def _call_openrouter(
    model_name: str, system_prompt: str, user_message: str, max_tokens: int
) -> ModelResponse:
    t0 = time.time()
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    payload = json.dumps(
        {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": max_tokens,
        }
    ).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/jotah/denisunifiedv1",
            "X-Title": "Denis AI",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"openrouter HTTP {exc.code}: {body[:200]}") from exc
    text = data["choices"][0]["message"]["content"]
    tokens = data.get("usage", {}).get("total_tokens", len(text.split()))
    return ModelResponse(
        text=text,
        model=f"openrouter/{model_name}",
        tokens_used=tokens,
        latency_ms=(time.time() - t0) * 1000,
    )


def _call_llama_local(system_prompt: str, user_message: str, max_tokens: int) -> ModelResponse:
    t0 = time.time()
    full_prompt = f"<|system|>\n{system_prompt}\n<|user|>\n{user_message}\n<|assistant|>"
    payload = json.dumps(
        {
            "prompt": full_prompt,
            "max_tokens": max_tokens,
            "temperature": 0.7,
            "stop": ["<|user|>", "<|system|>"],
        }
    ).encode()
    req = urllib.request.Request(
        "http://localhost:8084/inference/local",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.URLError as exc:
        raise RuntimeError(f"llamaLocal unreachable: {exc}") from exc
    text = (
        data.get("text")
        or data.get("response")
        or data.get("content")
        or data.get("generated_text", "")
    )
    tokens = data.get("tokens_used", len(text.split()))
    return ModelResponse(
        text=text,
        model="llamaLocal",
        tokens_used=tokens,
        latency_ms=(time.time() - t0) * 1000,
    )


def _mark_quota_exhausted(model: str) -> None:
    try:
        from denisunifiedv1.inference.quotaregistry import QuotaRegistry

        QuotaRegistry().mark_quota_exhausted(model, reset_in_seconds=3600)
    except Exception:
        pass


def call_model(
    routed,
    system_prompt: str,
    user_message: str,
    max_tokens: int = 1024,
) -> ModelResponse:
    model: str = getattr(routed, "model", "") or "llamaLocal"

    attempts: list[tuple[str, object]] = []
    if model.startswith("groq/"):
        bare = model[len("groq/") :]
        attempts.append(("groq", lambda: _call_groq(bare, system_prompt, user_message, max_tokens)))
    elif model.startswith("openrouter/"):
        bare = model[len("openrouter/") :]
        attempts.append(
            ("openrouter", lambda: _call_openrouter(bare, system_prompt, user_message, max_tokens))
        )
    attempts.append(
        ("llamaLocal", lambda: _call_llama_local(system_prompt, user_message, max_tokens))
    )

    primary_label = attempts[0][0]
    last_error = ""

    for label, fn in attempts:
        try:
            resp = fn()
            resp.used_fallback = label != primary_label
            return resp
        except Exception as exc:
            last_error = str(exc)
            logger.warning("ModelCaller: %s failed — %s", label, exc)
            if any(kw in last_error.lower() for kw in ("429", "quota", "rate limit")):
                _mark_quota_exhausted(model)

    return ModelResponse(
        text="[Denis — motores no disponibles en este momento]",
        model="none",
        tokens_used=0,
        latency_ms=0.0,
        used_fallback=True,
        error=last_error,
    )
