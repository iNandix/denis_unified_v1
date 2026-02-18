#!/usr/bin/env python3
"""
AI Consult - Adapter for consulting GPT/Perplexity with CP context.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ConsultResult:
    """Result from AI consultation."""

    summary: str
    full_response: Dict[str, Any]
    source: str
    timestamp: datetime

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "full_response": self.full_response,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
        }


class AIConsult:
    """Adapter for consulting external AI with CP context."""

    CONTEXT_FORMAT = """CONTEXTO DENIS CP:
- Repo: {repo_name} · {branch}
- Intent: {intent} ({confidence}%)
- Mission: {mission}
- Files: {files}
- Implicit tasks: {implicit_tasks}
- Model: {model}
- Constraints: {constraints}

PREGUNTA:
{query}"""

    def __init__(self):
        self._oceanai_client = None

    def _find_oceanai_client(self):
        """Find OceanAI client wrapper (Perplexity/GPT)."""
        if self._oceanai_client is not None:
            return self._oceanai_client

        ocean_path = os.environ.get("OCEAN_AI_CLIENT")
        if not ocean_path:
            result = subprocess.run(
                "find /media/jotah/SSD_denis -path '*oceanaiwrapper*' -name 'client.py' 2>/dev/null | grep -v venv | head -1",
                shell=True,
                capture_output=True,
                text=True,
            )
            ocean_path = result.stdout.strip()

        if not ocean_path or not os.path.exists(ocean_path):
            result = subprocess.run(
                "find /media/jotah/SSD_denis -path '*oceanai*' -name 'client.py' 2>/dev/null | grep -v venv | head -1",
                shell=True,
                capture_output=True,
                text=True,
            )
            ocean_path = result.stdout.strip()

        if ocean_path and os.path.exists(ocean_path):
            try:
                import importlib.util

                spec = importlib.util.spec_from_file_location("oceanai_client", ocean_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    self._oceanai_client = module
                    logger.info(f"Loaded OceanAI from {ocean_path}")
                    return self._oceanai_client
            except Exception as e:
                logger.warning(f"Could not load OceanAI from {ocean_path}: {e}")

        return None

    def _build_context(self, query: str, cp: Any) -> str:
        """Build context string from CP."""
        files = ", ".join(cp.files_to_read[:3]) if cp.files_to_read else "Ninguno"
        implicit = ", ".join(cp.implicit_tasks[:3]) if cp.implicit_tasks else "Ninguno"
        constraints = ", ".join(cp.constraints) if cp.constraints else "Ninguno"

        return self.CONTEXT_FORMAT.format(
            repo_name=cp.repo_name or "desconocido",
            branch=cp.branch or "unknown",
            intent=cp.intent or "unknown",
            confidence=int((cp.extra_context.get("confidence", 0.5)) * 100),
            mission=cp.mission[:200] if cp.mission else "Sin misión",
            files=files,
            implicit_tasks=implicit,
            model=cp.model or "groq",
            constraints=constraints,
            query=query,
        )

    async def consult_with_context(self, query: str, cp: Any) -> ConsultResult:
        """
        Consult AI with CP context.

        Priority:
        1. OceanAI wrapper (Perplexity/GPT session)
        2. HTTP to localhost:8084/api/consult
        3. Fallback error result
        """
        client = self._find_oceanai_client()
        if client:
            try:
                context = self._build_context(query, cp)
                response = await client.consult(context)
                return ConsultResult(
                    summary=response.get("summary", response.get("text", "")[:400]),
                    full_response=response,
                    source="oceanai",
                    timestamp=datetime.now(timezone.utc),
                )
            except AttributeError:
                try:
                    context = self._build_context(query, cp)
                    response = await client.client.ask(context, output_format="json")
                    return ConsultResult(
                        summary=response.get("answer", "")[:400],
                        full_response=response,
                        source="perplexity_gpt",
                        timestamp=datetime.now(timezone.utc),
                    )
                except Exception as e:
                    logger.warning(f"OceanAI consult failed: {e}")
            except Exception as e:
                logger.warning(f"OceanAI consult failed: {e}")

        try:
            import requests

            r = requests.get("http://localhost:8084/health", timeout=3)
            if r.status_code == 200:
                context = f"CP: {cp.cp_id} Mission: {cp.mission}"
                response = requests.post(
                    "http://localhost:8084/api/consult",
                    json={"query": query, "context": context},
                    timeout=15,
                )
                if response.ok:
                    data = response.json()
                    return ConsultResult(
                        summary=data.get("answer", "")[:400],
                        full_response=data,
                        source="service_8084",
                        timestamp=datetime.now(timezone.utc),
                    )
        except Exception as e:
            logger.warning(f"Local consult API failed: {e}")

        return ConsultResult(
            summary="[Sin IA disponible — aprobación manual OK]",
            full_response={"error": "AI services unavailable"},
            source="none",
            timestamp=datetime.now(timezone.utc),
        )

    def consult_with_context_sync(self, query: str, cp: Any) -> ConsultResult:
        """Synchronous wrapper for consult_with_context."""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.consult_with_context(query, cp))
                    return future.result(timeout=60)
            return loop.run_until_complete(self.consult_with_context(query, cp))
        except RuntimeError:
            return asyncio.run(self.consult_with_context(query, cp))


__all__ = ["AIConsult", "ConsultResult"]
