from __future__ import annotations

import importlib.util
import json
import logging
import os
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_OCEANAI_SEARCH_ROOTS = [
    "/media/jotah/SSD_denis/home_jotah/denis_unified_v1",
    "/media/jotah/SSD_denis/home_jotah",
]
_OCEANAI_CANDIDATES = [
    ("oceanaicorecomplete", ["chat_completion", "query", "ask"]),
    ("oceanai_client", ["query", "ask", "chat"]),
    ("perplexity_client", ["query", "ask"]),
]


@dataclass
class ConsultResult:
    summary: str
    full_response: Dict[str, Any]
    source: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error: str = ""


def _find_oceanai_fn():
    for root in _OCEANAI_SEARCH_ROOTS:
        for module_name, fn_names in _OCEANAI_CANDIDATES:
            path = os.path.join(root, f"{module_name}.py")
            if not os.path.isfile(path):
                continue
            try:
                spec = importlib.util.spec_from_file_location(module_name, path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                for fn_name in fn_names:
                    fn = getattr(mod, fn_name, None)
                    if callable(fn):
                        logger.debug("OceanAI client found: %s.%s", path, fn_name)
                        return fn
            except Exception as exc:
                logger.debug("OceanAI candidate %s failed to load: %s", path, exc)
    return None


def _parse_json_response(raw: str) -> dict:
    text = raw.strip()
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1].lstrip("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"summary": raw[:300], "advice": "", "confidence": 0.5}


def _call_oceanai(query: str, cp_summary: str) -> ConsultResult:
    fn = _find_oceanai_fn()
    if fn is None:
        raise RuntimeError("No OceanAI client found on disk")
    t0 = time.time()
    result = fn(
        system=(
            "Responde SOLO con JSON válido con estos campos: "
            "summary (string, max 300 chars), advice (string, max 200 chars), "
            "confidence (float 0-1). Idioma: español."
        ),
        user=f"CP Denis:\n{cp_summary}\n\nPregunta: {query}",
    )
    if isinstance(result, str):
        result = _parse_json_response(result)
    summary = result.get("summary", str(result)[:300])
    return ConsultResult(
        summary=summary,
        full_response=result if isinstance(result, dict) else {"raw": str(result)},
        source="oceanai",
    )


def _call_perplexity(query: str, cp_summary: str) -> ConsultResult:
    api_key = os.environ.get("PERPLEXITY_API_KEY", "")
    if not api_key:
        raise RuntimeError("PERPLEXITY_API_KEY not set")
    payload = json.dumps(
        {
            "model": "sonar",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Responde SOLO con JSON válido con estos campos: "
                        "summary (string, max 300 chars), advice (string, max 200 chars), "
                        "confidence (float 0-1). Idioma: español."
                    ),
                },
                {
                    "role": "user",
                    "content": f"CP Denis:\n{cp_summary}\n\nPregunta del usuario: {query}",
                },
            ],
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.perplexity.ai/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"Perplexity HTTP {exc.code}: {body[:200]}") from exc
    raw_text = data["choices"][0]["message"]["content"]
    parsed = _parse_json_response(raw_text)
    return ConsultResult(
        summary=parsed.get("summary", raw_text[:300]),
        full_response=parsed,
        source="perplexity",
    )


def consult_with_context(query: str, cp) -> ConsultResult:
    cp_summary = (
        f"Mission: {getattr(cp, 'mission', '')[:300]}\n"
        f"Model: {getattr(cp, 'model', 'unknown')}\n"
        f"Repo: {getattr(cp, 'repo_name', 'unknown')} "
        f"[{getattr(cp, 'branch', 'main')}]"
    )

    last_error = ""
    for label, fn in [("oceanai", _call_oceanai), ("perplexity", _call_perplexity)]:
        try:
            return fn(query, cp_summary)
        except Exception as exc:
            last_error = str(exc)
            logger.debug("%s consult failed: %s", label, exc)

    return ConsultResult(
        summary=("[consulta IA no disponible — revisa PERPLEXITY_API_KEY / OceanAI / conexión]"),
        full_response={},
        source="unavailable",
        error=last_error,
    )
