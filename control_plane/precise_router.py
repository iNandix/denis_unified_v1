"""Precise Router - Graph-centric intent routing with caching.

Flow: Cypher → Rasa → ParLAI → SLM → Groq (CRITICAL only)
Target: 0 Groq for 90% of requests, cache TTL=1h
"""

import os
import time
import json
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

CACHE_FILE = "/tmp/denis_graph_cache.json"
CACHE_TTL_SECONDS = 3600  # 1 hour


@dataclass
class RouteResult:
    """Result from precise routing."""

    intent: str
    confidence: float
    engine_id: str
    endpoint: str
    routing: str  # "graph", "rasa", "parlai", "slm", "groq"
    code_stub: str
    slots: Dict[str, str]


class PreciseRouter:
    """
    Graph-centric precise router.

    Priority:
    1. Cypher (Neo4j) - get engine + symbols + template
    2. Rasa NLU - local intent classification
    3. ParLAI - template from graph
    4. SLM nodo1 - local fallback
    5. Groq - ONLY for critical/unknown

    Cache: /tmp/denis_graph_cache.json TTL=1h
    """

    def __init__(self):
        self._cache = self._load_cache()
        self._cypher_router = None
        self._slm_router = None
        self._parlai = None

    def _load_cache(self) -> Dict[str, Any]:
        """Load cache from file."""
        try:
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE) as f:
                    data = json.load(f)
                    # Check TTL
                    if time.time() - data.get("timestamp", 0) < CACHE_TTL_SECONDS:
                        return data
        except Exception:
            pass
        return {"timestamp": time.time(), "routes": {}}

    def _save_cache(self):
        """Save cache to file."""
        try:
            with open(CACHE_FILE, "w") as f:
                json.dump(self._cache, f)
        except Exception:
            pass

    def _get_cypher_router(self):
        if self._cypher_router is None:
            from kernel.ghostide.symbol_cypher_router import get_symbol_cypher_router

            self._cypher_router = get_symbol_cypher_router()
        return self._cypher_router

    def _get_slm_router(self):
        if self._slm_router is None:
            from control_plane.slm_router import get_slm_router

            self._slm_router = get_slm_router()
        return self._slm_router

    def _get_parlai(self):
        if self._parlai is None:
            from denis_unified_v1.parlai.graph_templates import get_parlai_templates

            self._parlai = get_parlai_templates()
        return self._parlai

    async def classify(self, prompt: str) -> RouteResult:
        """
        Classify and route prompt using graph-centric pipeline.

        Returns engine + code_stub ready to use.
        """
        # Check cache
        cache_key = f"route:{prompt[:50]}"
        if cache_key in self._cache.get("routes", {}):
            cached = self._cache["routes"][cache_key]
            if time.time() - cached.get("cached_at", 0) < CACHE_TTL_SECONDS:
                logger.debug("Using cached route")
                return RouteResult(**cached["result"])

        # 1. Try Graph (Cypher) - highest priority
        result = await self._try_graph(prompt)
        if result:
            self._cache_result(cache_key, result, "graph")
            return result

        # 2. Try Rasa NLU
        result = await self._try_rasa(prompt)
        if result:
            self._cache_result(cache_key, result, "rasa")
            return result

        # 3. Try SLM nodo1
        result = await self._try_slm(prompt)
        if result:
            self._cache_result(cache_key, result, "slm")
            return result

        # 4. LAST RESORT: Groq (only for critical)
        result = await self._try_groq(prompt)
        self._cache_result(cache_key, result, "groq")
        return result

    async def _try_graph(self, prompt: str) -> Optional[RouteResult]:
        """Try graph-based routing."""
        try:
            cypher = self._get_cypher_router()

            # Extract intent keywords
            intent = self._extract_intent(prompt)

            # Get engine
            engines = cypher.get_engine_for_intent(intent)
            if not engines:
                return None

            engine = engines[0]

            # Get symbols
            symbols = cypher.get_symbols_context(intent, limit=5)

            # Get ParLAI template
            parlai = self._get_parlai()
            template = parlai.get_template_for_intent(intent)

            return RouteResult(
                intent=intent,
                confidence=0.9,
                engine_id=engine.engine_id,
                endpoint=engine.endpoint,
                routing="graph",
                code_stub=template.code_stub if template else "# Generated",
                slots={s.name: s.path for s in symbols[:3]},
            )
        except Exception as e:
            logger.debug(f"Graph routing failed: {e}")
        return None

    async def _try_rasa(self, prompt: str) -> Optional[RouteResult]:
        """Try Rasa NLU."""
        try:
            slm = self._get_slm_router()
            result = await slm.classify(prompt)

            if result.local_routing == "local":
                cypher = self._get_cypher_router()
                engines = cypher.get_engine_for_intent(result.intent)

                if engines:
                    parlai = self._get_parlai()
                    template = parlai.get_template_for_intent(result.intent)

                    return RouteResult(
                        intent=result.intent,
                        confidence=result.confidence,
                        engine_id=engines[0].engine_id,
                        endpoint=engines[0].endpoint,
                        routing="rasa",
                        code_stub=template.code_stub if template else "",
                        slots={},
                    )
        except Exception as e:
            logger.debug(f"Rasa routing failed: {e}")
        return None

    async def _try_slm(self, prompt: str) -> Optional[RouteResult]:
        """Try SLM nodo1."""
        try:
            slm = self._get_slm_router()
            result = await slm.classify(prompt)

            # Always have fallback
            return RouteResult(
                intent=result.intent,
                confidence=result.confidence,
                engine_id="qwen3b_local",
                endpoint="http://127.0.0.1:9997",
                routing="slm",
                code_stub="# SLM generated",
                slots={},
            )
        except Exception as e:
            logger.debug(f"SLM routing failed: {e}")
        return None

    async def _try_groq(self, prompt: str) -> RouteResult:
        """Groq - LAST RESORT for critical."""
        return RouteResult(
            intent="unknown",
            confidence=0.1,
            engine_id="groq_booster",
            endpoint="https://api.groq.com/openai/v1",
            routing="groq",
            code_stub="# Groq fallback - CRITICAL",
            slots={},
        )

    def _extract_intent(self, prompt: str) -> str:
        """Extract intent from prompt."""
        prompt_lower = prompt.lower()

        if any(w in prompt_lower for w in ["crea", "implementa", "nueva"]):
            return "implement_feature"
        if any(w in prompt_lower for w in ["arregla", "bug", "error"]):
            return "debug_repo"
        if any(w in prompt_lower for w in ["test", "prueba"]):
            return "run_tests_ci"
        if any(w in prompt_lower for w in ["refactor", "migra"]):
            return "refactor_migration"
        if any(w in prompt_lower for w in ["explica", "qué es"]):
            return "explain_concept"

        return "implement_feature"

    def _cache_result(self, key: str, result: RouteResult, routing: str):
        """Cache routing result."""
        if "routes" not in self._cache:
            self._cache["routes"] = {}

        self._cache["routes"][key] = {
            "result": {
                "intent": result.intent,
                "confidence": result.confidence,
                "engine_id": result.engine_id,
                "endpoint": result.endpoint,
                "routing": routing,
                "code_stub": result.code_stub,
                "slots": result.slots,
            },
            "cached_at": time.time(),
        }
        self._save_cache()


# Singleton
_router: Optional[PreciseRouter] = None


def get_precise_router() -> PreciseRouter:
    """Get PreciseRouter singleton."""
    global _router
    if _router is None:
        _router = PreciseRouter()
    return _router
