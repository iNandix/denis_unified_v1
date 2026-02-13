#!/usr/bin/env python3
"""
SMX Orchestrator 2-Fase - Unified V1
=====================================
Orquestador jerárquico para procesamiento SMX en 2 fases.
- FASE 1: Capas paralelas independientes (Tokenize, Safety, Fast)
- FASE 2: Capas dependientes (Intent → Entity → Macro → Response)

Versión adaptada para Denis Unified V1
"""

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from denis_unified_v1.smx.client import SMXClient
from denis_unified_v1.metacognitive.hooks import metacognitive_trace

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s"
)
logger = logging.getLogger("smx.orchestrator.unified")


@dataclass
class Timeouts:
    """Timeouts por capa (segundos)."""

    tokenize: float = 8.0
    safety: float = 10.0
    fast_check: float = 10.0
    intent: float = 8.0
    entity: float = 8.0
    macro: float = 10.0
    response: float = 15.0
    phase1_total: float = 5.0
    phase2_total: float = 15.0


TIMEOUTS = Timeouts()

# Node2 host can be LAN or Tailscale. Keep it configurable.
NODO2_HOST = os.getenv("NODO2_HOST", os.getenv("DENIS_NODE2_HOST", "10.10.10.2"))


def _fallback_to_content(fallback_result: Any) -> str:
    """
    FallbackManager historically returns either an object with `.content`
    or a plain dict. Keep this robust to preserve Invariant C4 responses.
    """
    if fallback_result is None:
        return ""
    if isinstance(fallback_result, dict):
        v = (
            fallback_result.get("content")
            or fallback_result.get("response")
            or fallback_result.get("text")
            or ""
        )
        return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    v = getattr(fallback_result, "content", None)
    if isinstance(v, str):
        return v
    if v is None:
        return ""
    return str(v)


@dataclass
class LayerResult:
    """Resultado de una capa SMX."""

    layer: str
    model: str
    content: Any
    latency_ms: int
    success: bool
    error: Optional[str] = None
    from_cache: bool = False
    from_fallback: bool = False


@dataclass
class FusedResult:
    """Resultado final del procesamiento SMX."""

    content: str
    intent: Optional[str]
    entities: List[Dict[str, Any]]
    macro_chain: List[str]
    trace_id: str
    total_latency_ms: int
    phase1_latency_ms: int
    phase2_latency_ms: int
    layer_results: Dict[str, Any]  # Changed from Dict[str, LayerResult]
    safety_passed: bool
    antiloop_passed: bool
    source: str = "smx_fused_unified"


class SMXOrchestrator:
    """
    Orquestador SMX con procesamiento en 2 fases.

    FASE 1 (Paralelo):
    - Tokenize (SmolLM2)
    - Safety (Gemma3)
    - Fast Check (Qwen05B)

    FASE 2 (Dependiente de FASE 1):
    - Intent (Qwen15B)
    - Entity (Gemma3)
    - Macro (QwenCoder)
    - Response (Qwen3B)
    """

    # URLs de modelos SMX - 6 motores distribuidos (CONFIGURACIÓN ÓPTIMA)
    # NODO1 (RTX 3080 10GB):
    #   - Puerto 9997: Qwen3B (Dialog/Response)
    #   - Puerto 9998: QwenCoder 7B (Macro/Code)
    # NODO2 (GTX 1050 Ti 4GB):
    #   - Puerto 8003: Qwen 0.5B (Fast Check) - GPU
    #   - Puerto 8006: SmolLM2 1.7B (Tokenize) - GPU (ngl=8)
    #   - Puerto 8007: Gemma 1B (Safety/Entity) - GPU
    #   - Puerto 8008: Qwen 1.5B (Intent/Planner) - GPU (ngl=10)

    NODO1_HOST = os.getenv("NODO1_HOST", "127.0.0.1")

    SMX_URLS = {
        "tokenize": f"http://{NODO2_HOST}:8006",  # SmolLM2 1.7B (Nodo2)
        "safety": f"http://{NODO2_HOST}:8007",  # Gemma 1B (Nodo2)
        "fast_check": f"http://{NODO2_HOST}:8003",  # Qwen 0.5B (Nodo2)
        "fast": f"http://{NODO2_HOST}:8003",  # legacy alias
        "intent": f"http://{NODO2_HOST}:8008",  # Qwen 1.5B (Nodo2)
        "entity": f"http://{NODO2_HOST}:8007",  # Gemma 1B (Nodo2)
        "macro": f"http://{NODO1_HOST}:9998",  # QwenCoder 7B (Nodo1)
        "response": f"http://{NODO1_HOST}:9997",  # Qwen3B (Nodo1)
    }

    # Mapeo de layer a model_key para contratos
    LAYER_TO_MODEL = {
        "tokenize": "smollm2",  # SmolLM2 1.7B en 8006
        "safety": "gemma1b",  # Gemma 1B en 8007
        "fast": "qwen05b",  # Qwen 0.5B en 8003
        "fast_check": "qwen05b",  # Qwen 0.5B en 8003
        "intent": "qwen15b",  # Qwen 1.5B en 8008
        "entity": "gemma1b",  # Gemma 1B en 8007
        "macro": "qwen_coder7b",  # QwenCoder 7B en 9998
        "response": "qwen3b",  # Qwen3B en 9997
    }

    # Constrain generation budget per layer to avoid node2 timeouts.
    LAYER_MAX_TOKENS = {
        "tokenize": 32,
        "safety": 32,
        "fast_check": 48,
        "intent": 32,
        "entity": 48,
        "macro": 128,
        "response": 192,
    }

    def __init__(
        self,
        context_bus=None,
        circuit_breaker_manager=None,
        fallback_manager=None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.context_bus = context_bus
        self.cb_manager = circuit_breaker_manager
        self.fallback = fallback_manager
        self.http = http_client or httpx.AsyncClient(
            timeout=30.0, limits=httpx.Limits(max_connections=100)
        )
        self.smx_client = SMXClient()

    async def close(self):
        """Cerrar cliente HTTP."""
        await self.http.aclose()

    async def call_smx_layer(
        self,
        layer: str,
        text: str,
        context: Optional[Dict] = None,
        timeout: float = 5.0,
    ) -> LayerResult:
        """Llamar a una capa SMX específica."""
        # Normalize legacy alias to canonical layer name (Invariant C4).
        if layer == "fast":
            layer = "fast_check"

        t0 = time.time()
        url = self.SMX_URLS.get(layer)
        model_key = self.LAYER_TO_MODEL.get(layer, "qwen3b")
        if not url:
            return LayerResult(
                layer=layer,
                model=model_key,
                content="",
                latency_ms=0,
                success=False,
                error=f"unknown_layer:{layer}",
            )

        # Llamar directamente al endpoint /v1/completions (no /v1/chat/completions)
        # IMPORTANTE: Usar /v1/completions para evitar doble chat template
        # El orchestrator ya formatea el prompt, no dejar que llama-server lo haga
        max_tokens = self.LAYER_MAX_TOKENS.get(layer, 64)

        # Prompts especializados en español por capa
        LAYER_PROMPTS = {
            "tokenize": "Eres un tokenizador. Cuenta los tokens del texto. Responde solo con el número.",
            "safety": "Eres un filtro de seguridad. Analiza si el texto es seguro. Responde: SEGURO o BLOQUEADO.",
            "fast_check": "Eres un clasificador rápido. Determina si necesita procesamiento completo. Responde: SI o NO.",
            "intent": "Eres un detector de intención. Identifica la intención del usuario en UNA palabra (ej: encender_luces, consultar_clima, reproducir_musica). Solo la intención, nada más.",
            "entity": "Eres un extractor de entidades. Lista las entidades mencionadas (dispositivos, lugares, personas). Formato: entidad1, entidad2.",
            "macro": "Eres un planificador de acciones. Basándote en la intención y entidades, lista las acciones necesarias. Una línea.",
            "response": "Eres Denis, un asistente en español. Responde de forma natural y concisa al usuario.",
        }

        system_msg = LAYER_PROMPTS.get(
            layer, f"Eres la capa {layer}. Responde en UNA línea corta."
        )

        # Prompt RAW sin tokens especiales para /v1/completions
        # El endpoint /v1/completions NO aplica chat template, solo genera texto
        prompt = f"{system_msg}\n\nUsuario: {text}\n\nAsistente:"

        payload = {
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": 0.2,
            "stream": False,
            "stop": ["<|im_end|>", "<|end_of_turn|>"],
        }

        try:
            async with asyncio.timeout(timeout):
                resp = await self.http.post(
                    f"{url}/v1/completions", json=payload, timeout=timeout
                )

            latency_ms = int((time.time() - t0) * 1000)

            if resp.status_code == 200:
                data = resp.json()
                # Extraer contenido de respuesta /v1/completions (no chat)
                # Formato: {"choices": [{"text": "..."}]}
                content = ""
                if "choices" in data and len(data["choices"]) > 0:
                    # Support both /v1/completions and /v1/chat/completions formats
                    choice = data["choices"][0]
                    content = (
                        choice.get("text")
                        or choice.get("message", {}).get("content", "")
                        or ""
                    )
                return LayerResult(
                    layer=layer,
                    model=model_key,
                    content=content,
                    latency_ms=latency_ms,
                    success=True,
                )
            else:
                return LayerResult(
                    layer=layer,
                    model=model_key,
                    content="",
                    latency_ms=latency_ms,
                    success=False,
                    error=f"HTTP {resp.status_code}",
                )

        except asyncio.TimeoutError:
            latency_ms = int((time.time() - t0) * 1000)
            logger.warning(f"SMX {layer}: Timeout ({timeout}s)")

            # Intentar fallback
            if self.fallback:
                fallback_result = await self.fallback.get_fallback(layer, text)
                return LayerResult(
                    layer=layer,
                    model=model_key,
                    content=_fallback_to_content(fallback_result),
                    latency_ms=latency_ms,
                    success=False,
                    error="timeout",
                    from_fallback=True,
                )

            return LayerResult(
                layer=layer,
                model=model_key,
                content="",
                latency_ms=latency_ms,
                success=False,
                error="timeout",
            )

        except Exception as e:
            latency_ms = int((time.time() - t0) * 1000)
            logger.error(f"SMX {layer}: Error - {e}")
            return LayerResult(
                layer=layer,
                model=model_key,
                content="",
                latency_ms=latency_ms,
                success=False,
                error=str(e),
            )

    @metacognitive_trace(operation="smx_orchestrator_process")
    async def process(
        self, text: str, user_id: Optional[str] = None, trace_id: Optional[str] = None
    ) -> FusedResult:
        """
        Procesamiento completo SMX en 2 fases.

        Returns:
            FusedResult con contenido, intent, entities, macro_chain, etc.
        """
        request_id = trace_id or uuid.uuid4().hex[:16]
        t0_total = time.time()

        logger.info(f"SMX Orchestrator Unified: Iniciando request {request_id}")

        # ═══ FASE 1 ═══
        phase1_results = await self.phase1_parallel(text, request_id)
        phase1_latency = int((time.time() - t0_total) * 1000)

        # Convert phase1_results to LayerResult format
        layer_results = {}
        safety_result = phase1_results.get("safety")
        if isinstance(safety_result, dict):
            safe = safety_result.get("safe", True)
            layer_results["safety"] = LayerResult(layer="safety", model="gemma1b", content="safe" if safe else "unsafe", latency_ms=0, success=safe)
        else:
            layer_results["safety"] = LayerResult(layer="safety", model="gemma1b", content="safe", latency_ms=0, success=True)

        fast_result = phase1_results.get("fast")
        if isinstance(fast_result, dict) and "choices" in fast_result:
            content = fast_result["choices"]["message"]["content"]
            layer_results["fast_check"] = LayerResult(layer="fast_check", model="qwen05b", content=content, latency_ms=0, success=True)
        else:
            layer_results["fast_check"] = LayerResult(layer="fast_check", model="qwen05b", content="", latency_ms=0, success=False)

        tokenize_result = phase1_results.get("tokenize")
        if tokenize_result and isinstance(tokenize_result, dict) and "choices" in tokenize_result:
            content = tokenize_result["choices"]["message"]["content"]
            layer_results["tokenize"] = LayerResult(layer="tokenize", model="smollm2", content=content, latency_ms=0, success=True)
        else:
            layer_results["tokenize"] = LayerResult(layer="tokenize", model="smollm2", content="", latency_ms=0, success=False)

        # Safety check
        safety = layer_results.get("safety")
        safety_passed = safety.success

        # Fast check: si es respuesta rápida, devolver directamente
        fast = layer_results.get("fast_check")
        if fast and fast.success and len(text.split()) < 5:
            # Request simple, respuesta rápida
            total_latency = int((time.time() - t0_total) * 1000)
            return FusedResult(
                content=fast.content,
                intent=None,
                entities=[],
                macro_chain=[],
                trace_id=request_id,
                total_latency_ms=total_latency,
                phase1_latency_ms=phase1_latency,
                phase2_latency_ms=0,
                layer_results=layer_results,
                safety_passed=safety_passed,
                antiloop_passed=True,
            )

        # ═══ FASE 2 ═══
        phase2_results = await self.phase2_dependent(text, layer_results, request_id)
        phase2_latency = int((time.time() - t0_total) * 1000) - phase1_latency

        # ═══ MERGE FINAL ═══
        all_results = {**phase1_results, **phase2_results}

        # Extraer contenido final
        response = phase2_results.get("response")
        if not (response and response.success):
            # Surface hidden failures
            err = response.error if response else "missing_response_result"
            logger.warning(
                "SMX response layer failed trace_id=%s error=%s",
                request_id,
                err,
            )
        final_content = (
            response.content if response and response.success else "[ERROR_IN_RESPONSE]"
        )

        # Extraer intent
        intent_result = phase2_results.get("intent")
        intent = (
            intent_result.content if intent_result and intent_result.success else None
        )

        # Extraer entities
        entity_result = phase2_results.get("entity")
        entities = (
            entity_result.content if entity_result and entity_result.success else []
        )

        # Extraer macro chain
        macro_result = phase2_results.get("macro")
        macro_chain = (
            macro_result.content if macro_result and macro_result.success else []
        )

        total_latency = int((time.time() - t0_total) * 1000)

        logger.info(f"SMX Orchestrator Unified: Completado en {total_latency}ms")

        return FusedResult(
            content=final_content,
            intent=intent,
            entities=entities if isinstance(entities, list) else [],
            macro_chain=macro_chain if isinstance(macro_chain, list) else [],
            trace_id=request_id,
            total_latency_ms=total_latency,
            phase1_latency_ms=phase1_latency,
            phase2_latency_ms=phase2_latency,
            layer_results=all_results,
            safety_passed=safety_passed,
            antiloop_passed=True,
        )

    async def phase1_parallel(
        self, text: str, request_id: str
    ) -> Dict[str, Any]:
        """
        Phase1: Tokenize + Safety + Fast en PARALELO real (no secuencial).
        Timeouts agresivos: 200ms tokenize, 250ms safety, 200ms fast.
        """
        tasks = []
        results = {"tokenize": None, "safety": None, "fast": None}

        # Lanzar 3 tasks en paralelo
        async def tokenize_task():
            try:
                result = await asyncio.wait_for(
                    self.smx_client.call_motor("tokenize", [{"role":"user","content":text}], max_tokens=5),
                    timeout=0.2
                )
                return ("tokenize", result)
            except asyncio.TimeoutError:
                return ("tokenize", None)

        async def safety_task():
            try:
                result = await asyncio.wait_for(
                    self.smx_client.call_motor("safety", [{"role":"user","content":text}], max_tokens=10),
                    timeout=0.25
                )
                return ("safety", result)
            except asyncio.TimeoutError:
                return ("safety", {"safe": True})  # Fallback safe

        async def fast_task():
            try:
                result = await asyncio.wait_for(
                    self.smx_client.call_motor("fast_check", [{"role":"user","content":text}], max_tokens=30),
                    timeout=0.2
                )
                return ("fast", result)
            except asyncio.TimeoutError:
                return ("fast", None)

        # Ejecutar en paralelo
        task_results = await asyncio.gather(tokenize_task(), safety_task(), fast_task())

        for key, value in task_results:
            results[key] = value

        return results

    async def phase2_dependent(
        self, text: str, phase1_results: Dict[str, LayerResult], request_id: str
    ) -> Dict[str, LayerResult]:
        """
        FASE 2: Capas dependientes secuencial/paralelo.

        Flujo:
        - Intent + Entity (paralelo)
        - Macro (depende de Intent + Entity)
        - Response (depende de Macro)
        """
        t0 = time.time()
        logger.info(f"FASE2 Unified: Iniciando para {request_id}")

        phase2_results: Dict[str, LayerResult] = {}
        phase1_ctx = {k: r.content for k, r in phase1_results.items() if r.success}

        # ═══ Paso 1: Intent + Entity en paralelo ═══
        logger.info("FASE2 Unified: Intent + Entity (paralelo)")

        intent_task = self.call_smx_layer(
            "intent", text, context=phase1_ctx, timeout=TIMEOUTS.intent
        )
        entity_task = self.call_smx_layer(
            "entity", text, context=phase1_ctx, timeout=TIMEOUTS.entity
        )

        intent_result, entity_result = await asyncio.gather(
            intent_task, entity_task, return_exceptions=True
        )

        if isinstance(intent_result, Exception):
            phase2_results["intent"] = LayerResult(
                layer="intent",
                model=self.LAYER_TO_MODEL.get("intent", "qwen3b"),
                content="",
                latency_ms=0,
                success=False,
                error=str(intent_result),
            )
        else:
            phase2_results["intent"] = intent_result

        if isinstance(entity_result, Exception):
            phase2_results["entity"] = LayerResult(
                layer="entity",
                model=self.LAYER_TO_MODEL.get("entity", "qwen3b"),
                content="",
                latency_ms=0,
                success=False,
                error=str(entity_result),
            )
        else:
            phase2_results["entity"] = entity_result

        # ═══ Paso 2: Macro (depende de Intent + Entity) ═══
        logger.info("FASE2 Unified: Macro Planning")

        macro_ctx = {
            **phase1_ctx,
            "intent": phase2_results.get(
                "intent", LayerResult("", "", "", 0, False)
            ).content,
            "entities": phase2_results.get(
                "entity", LayerResult("", "", "", 0, False)
            ).content,
        }

        macro_result = await self.call_smx_layer(
            "macro", text, context=macro_ctx, timeout=TIMEOUTS.macro
        )
        phase2_results["macro"] = macro_result

        # ═══ Paso 3: Response (depende de Macro) ═══
        logger.info("FASE2 Unified: Response Generation")

        response_ctx = {
            **macro_ctx,
            "macro_chain": macro_result.content,
        }

        response_result = await self.call_smx_layer(
            "response", text, context=response_ctx, timeout=TIMEOUTS.response
        )
        phase2_results["response"] = response_result

        phase2_latency = int((time.time() - t0) * 1000)
        logger.info(f"FASE2 Unified: Completada en {phase2_latency}ms")

        return phase2_results

    async def health_check(self) -> Dict[str, Any]:
        """Health check de todos los servicios SMX."""
        health = {}

        for name, url in self.SMX_URLS.items():
            try:
                resp = await self.http.get(f"{url}/health", timeout=2.0)
                health[name] = {
                    "healthy": resp.status_code == 200,
                    "latency_ms": (
                        resp.elapsed.total_seconds() * 1000
                        if resp.status_code == 200
                        else None
                    ),
                }
            except Exception as e:
                health[name] = {"healthy": False, "error": str(e)}

        return health


if __name__ == "__main__":

    async def test_orchestrator():
        """Test del SMX Orchestrator Unified."""
        orchestrator = SMXOrchestrator()

        print("Testing SMX Orchestrator Unified...")

        # Test request simple
        result = await orchestrator.process("Hola, ¿cómo estás?", user_id="test")

        print(f"\n=== Resultado ===")
        print(f"Trace ID: {result.trace_id}")
        print(f"Total Latency: {result.total_latency_ms}ms")
        print(f"  FASE1: {result.phase1_latency_ms}ms")
        print(f"  FASE2: {result.phase2_latency_ms}ms")
        print(f"Content: {result.content[:100]}...")

    asyncio.run(test_orchestrator())
