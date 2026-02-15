"""LocalResponder - P1.3: Deterministic offline response without alucinaciones.

Orden de salida:
1. Retrieval local (parallel) - 260ms budget
2. LLM local optional - 1700ms
3. Template fallback - always available

Timeouts (P1.3):
- neo4j_query_ms: 140ms
- human_memory_query_ms: 180ms
- metagraph_route_ms: 220ms
- redis_context_ms: 60ms
- filesystem_probe_ms: 120ms
- retrieval_parallel_budget_ms: 260ms
- local_llm_total_ms: 1700ms
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from denis_unified_v1.telemetry.outcome_recorder import (
    ExecutionMode,
    InternetStatus,
    ReasonCode,
)


# P1.3 Timeouts (ms)
NEO4J_QUERY_MS = 140
HUMAN_MEMORY_QUERY_MS = 180
METAGRAPH_ROUTE_MS = 220
REDIS_CONTEXT_MS = 60
FILESYSTEM_PROBE_MS = 120
RETRIEVAL_PARALLEL_BUDGET_MS = 260
LOCAL_LLM_TOTAL_MS = 1700
LOCAL_LLM_FALLBACK_MS = 900


@dataclass
class RetrievalResult:
    """Result from local retrieval."""

    neo4j_data: Optional[Dict] = None
    memory_data: Optional[Dict] = None
    metagraph_data: Optional[Dict] = None
    redis_data: Optional[Dict] = None
    filesystem_data: Optional[Dict] = None
    success: bool = False
    reason_codes: List[str] = field(default_factory=list)
    duration_ms: int = 0


@dataclass
class LocalResponse:
    """Response from LocalResponder."""

    response: str
    mode: ExecutionMode
    degraded: bool = False
    reason_codes: List[str] = field(default_factory=list)
    retrieval_used: bool = False
    llm_used: bool = False
    evidence: List[str] = field(default_factory=list)
    duration_ms: int = 0


class LocalResponder:
    """Deterministic offline responder - no alucinaciones."""

    def __init__(self):
        self.reason_codes: List[str] = []

    async def respond(
        self,
        user_message: str,
        intent: str,
        confidence: float,
        internet_status: InternetStatus,
        allow_boosters: bool,
    ) -> LocalResponse:
        """Generate local response following P1.3 fallback chain."""
        start = datetime.now(timezone.utc)

        # Step 1: Parallel retrieval (260ms budget)
        retrieval = await self._parallel_retrieval(user_message)

        # Step 2: Decide response strategy
        if retrieval.success and retrieval.neo4j_data:
            # Have good local data - synthesize response
            response = self._synthesize_from_retrieval(retrieval, user_message)
            return LocalResponse(
                response=response,
                mode=ExecutionMode.DIRECT_LOCAL,
                degraded=False,
                reason_codes=retrieval.reason_codes,
                retrieval_used=True,
                llm_used=False,
                evidence=self._get_evidence_paths(retrieval),
                duration_ms=int(
                    (datetime.now(timezone.utc) - start).total_seconds() * 1000
                ),
            )

        # Step 3: Try local LLM if available
        llm_response = await self._try_local_llm(user_message, retrieval)
        if llm_response:
            return llm_response

        # Step 4: Fallback to template
        return self._template_fallback(
            user_message, intent, retrieval.reason_codes, start
        )

    async def _parallel_retrieval(self, user_message: str) -> RetrievalResult:
        """Execute parallel retrieval with budget."""
        start = datetime.now(timezone.utc)
        reason_codes: List[str] = []

        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    self._query_neo4j(user_message),
                    self._query_memory(user_message),
                    self._query_metagraph(user_message),
                    self._query_redis(user_message),
                    self._probe_filesystem(user_message),
                    return_exceptions=True,
                ),
                timeout=RETRIEVAL_PARALLEL_BUDGET_MS / 1000,
            )

            neo4j_data, memory_data, metagraph_data, redis_data, fs_data = results

            # Check results and collect reason codes
            success = any(
                [
                    neo4j_data and not isinstance(neo4j_data, Exception),
                    memory_data and not isinstance(memory_data, Exception),
                    metagraph_data and not isinstance(metagraph_data, Exception),
                    redis_data and not isinstance(redis_data, Exception),
                ]
            )

            if isinstance(neo4j_data, Exception):
                reason_codes.append("neo4j_timeout")
            if isinstance(memory_data, Exception):
                reason_codes.append("memory_timeout")
            if isinstance(metagraph_data, Exception):
                reason_codes.append("metagraph_timeout")
            if isinstance(redis_data, Exception):
                reason_codes.append("redis_timeout")

        except asyncio.TimeoutError:
            reason_codes.append("retrieval_timeout")
            success = False
            neo4j_data = memory_data = metagraph_data = redis_data = fs_data = None

        duration_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)

        return RetrievalResult(
            neo4j_data=neo4j_data if not isinstance(neo4j_data, Exception) else None,
            memory_data=memory_data if not isinstance(memory_data, Exception) else None,
            metagraph_data=metagraph_data
            if not isinstance(metagraph_data, Exception)
            else None,
            redis_data=redis_data if not isinstance(redis_data, Exception) else None,
            filesystem_data=fs_data if not isinstance(fs_data, Exception) else None,
            success=success,
            reason_codes=reason_codes,
            duration_ms=duration_ms,
        )

    async def _query_neo4j(self, query: str) -> Optional[Dict]:
        """Query Neo4j for context."""
        try:
            # Use timeout
            return await asyncio.wait_for(
                self._neo4j_query_impl(query),
                timeout=NEO4J_QUERY_MS / 1000,
            )
        except Exception as e:
            return e

    async def _neo4j_query_impl(self, query: str) -> Optional[Dict]:
        """Actual Neo4j query implementation."""
        try:
            from denis_unified_v1.connections import get_neo4j_driver

            driver = get_neo4j_driver()
            if not driver:
                return None

            async with driver.session() as session:
                result = await session.run("MATCH (n) RETURN count(n) as count LIMIT 1")
                record = await result.single()
                if record:
                    return {"node_count": record["count"]}
        except Exception:
            pass
        return None

    async def _query_memory(self, query: str) -> Optional[Dict]:
        """Query human memory."""
        try:
            return await asyncio.wait_for(
                self._memory_query_impl(query),
                timeout=HUMAN_MEMORY_QUERY_MS / 1000,
            )
        except Exception as e:
            return e

    async def _memory_query_impl(self, query: str) -> Optional[Dict]:
        """Actual memory query implementation."""
        try:
            from denis_unified_v1.memory.manager import get_memory_manager

            mm = get_memory_manager()
            if mm:
                result = mm.retrieve(query, top_k=2)
                return {"results": result} if result else None
        except Exception:
            pass
        return None

    async def _query_metagraph(self, query: str) -> Optional[Dict]:
        """Query metagraph."""
        try:
            return await asyncio.wait_for(
                self._metagraph_query_impl(query),
                timeout=METAGRAPH_ROUTE_MS / 1000,
            )
        except Exception as e:
            return e

    async def _metagraph_query_impl(self, query: str) -> Optional[Dict]:
        """Actual metagraph query."""
        # Placeholder - implement based on actual metagraph module
        return None

    async def _query_redis(self, query: str) -> Optional[Dict]:
        """Query Redis for context."""
        try:
            return await asyncio.wait_for(
                self._redis_query_impl(query),
                timeout=REDIS_CONTEXT_MS / 1000,
            )
        except Exception as e:
            return e

    async def _redis_query_impl(self, query: str) -> Optional[Dict]:
        """Actual Redis query."""
        try:
            from denis_unified_v1.connections import get_redis_client

            client = get_redis_client()
            if client:
                # Simple ping to check connectivity
                await client.ping()
                return {"status": "connected"}
        except Exception:
            pass
        return None

    async def _probe_filesystem(self, query: str) -> Optional[Dict]:
        """Probe filesystem for relevant files."""
        try:
            return await asyncio.wait_for(
                self._filesystem_probe_impl(query),
                timeout=FILESYSTEM_PROBE_MS / 1000,
            )
        except Exception as e:
            return e

    async def _filesystem_probe_impl(self, query: str) -> Optional[Dict]:
        """Actual filesystem probe."""
        # Quick probe - just check if we have access to key files
        return None

    def _synthesize_from_retrieval(
        self, retrieval: RetrievalResult, user_message: str
    ) -> str:
        """Synthesize response from retrieval data."""
        parts = []

        if retrieval.neo4j_data:
            parts.append(
                f"[Grafo: {retrieval.neo4j_data.get('node_count', '?')} nodos]"
            )

        if retrieval.memory_data:
            results = retrieval.memory_data.get("results", [])
            if results:
                parts.append(f"[Memoria: {len(results)} resultados]")

        if retrieval.redis_data:
            parts.append("[Redis: conectado]")

        if parts:
            return f"He recuperado información local: {' '.join(parts)}"

        return "Tengo acceso a módulos locales pero no encontré información relevante."

    async def _try_local_llm(
        self, user_message: str, retrieval: RetrievalResult
    ) -> Optional[LocalResponse]:
        """Try local LLM if available."""
        # Check if local LLM is available
        try:
            from denis_unified_v1.inference.router import InferenceRouter

            router = InferenceRouter()

            # Try to find a local engine
            local_engine = None
            for engine_id, engine in router.engine_registry.items():
                if engine.get("provider_key") == "llamacpp":
                    local_engine = engine_id
                    break

            if not local_engine:
                return None

            # Try with timeout
            response = await asyncio.wait_for(
                self._call_local_llm(router, user_message, local_engine),
                timeout=LOCAL_LLM_TOTAL_MS / 1000,
            )

            if response:
                return LocalResponse(
                    response=response,
                    mode=ExecutionMode.DIRECT_LOCAL,
                    degraded=False,
                    reason_codes=["local_llm_used"] + retrieval.reason_codes,
                    retrieval_used=True,
                    llm_used=True,
                    evidence=[],
                    duration_ms=LOCAL_LLM_TOTAL_MS,
                )

        except asyncio.TimeoutError:
            pass
        except Exception:
            pass

        return None

    async def _call_local_llm(
        self, router: Any, message: str, engine_id: str
    ) -> Optional[str]:
        """Call local LLM."""
        # Placeholder - implement actual call
        return None

    def _template_fallback(
        self,
        user_message: str,
        intent: str,
        reason_codes: List[str],
        start: datetime,
    ) -> LocalResponse:
        """Template fallback - always available, no alucinaciones."""

        # Determine template based on intent
        templates = {
            "debug_repo": (
                "He detectado que quieres debuggear. "
                "Para ayudarte necesito más contexto: "
                "¿Qué error ves? ¿En qué archivo? ¿Qué has intentado?"
            ),
            "run_tests_ci": (
                "Quieres ejecutar tests. "
                "Puedo ayudarte si me dices: "
                "¿Qué test? ¿En qué path? ¿Con qué entorno?"
            ),
            "implement_feature": (
                "Quieres implementar una feature. "
                "Necesito más detalles: "
                "¿Qué funcionalidad? ¿En qué módulo? ¿Tienes specs?"
            ),
            "refactor_migration": (
                "Quieres refactorizar o migrar código. "
                "¿Qué módulo? ¿Qué patrones quieres usar? "
                "¿Hay tests existentes?"
            ),
            "ops_health_check": (
                "Puedes ejecutar 'engine_probe --mode ping' para ver el estado de los engines. "
                "También puedo revisar logs o configuraciones específicas."
            ),
        }

        response = templates.get(
            intent,
            (
                "He procesado tu solicitud (modo local/sin internet). "
                "Para darte una respuesta más precisa, necesito más contexto. "
                "¿Puedes dar más detalles sobre lo que necesitas?"
            ),
        )

        duration_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)

        return LocalResponse(
            response=response,
            mode=ExecutionMode.DIRECT_LOCAL,
            degraded=True,
            reason_codes=["local_template_used"] + reason_codes,
            retrieval_used=False,
            llm_used=False,
            evidence=[],
            duration_ms=duration_ms,
        )

    def _get_evidence_paths(self, retrieval: RetrievalResult) -> List[str]:
        """Get evidence paths from retrieval."""
        paths = []
        # Add based on what was retrieved
        return paths


def create_local_responder() -> LocalResponder:
    """Factory for LocalResponder."""
    return LocalResponder()
