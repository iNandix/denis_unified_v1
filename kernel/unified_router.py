#!/usr/bin/env python3
"""UnifiedRouter MN2 - Orquestador central de tools para Denis.

MN2 = MetaNodo2 - El cerebro que decide qué tool usar.
DenisPersona usa UnifiedRouter para decidir cómo resolver cada request.

Tools disponibles:
- Rasa NLU → Entendimiento de lenguaje
- ParLAI → Templates de tareas
- NodoMacVampirizer → Engines vivos
- SymbolCypherRouter → Símbolos del grafo
- Memoria L1-L12 → Diferentes tipos de memoria
- ControlPlane → Ejecución de CPs
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Resultado de un tool."""

    tool: str
    success: bool
    data: Any
    latency_ms: float
    error: Optional[str] = None


@dataclass
class UnifiedDecision:
    """Decisión del UnifiedRouter."""

    intent: str
    primary_tool: str
    secondary_tools: List[str]
    engine: str
    context: Dict[str, Any]
    confidence: float
    reasoning: str


class UnifiedRouter:
    """
    MN2 - MetaNodo2: Orquestador de tools para Denis.

    Recibe requests y decide qué tools usar basándose en:
    - Intent del usuario
    - Estado actual de Denis (mood, consciousness)
    - Disponibilidad de tools
    - Contexto del grafo

    NO toma decisiones - DELega a DenisPersona para decisiones importantes,
    pero maneja la orquestación de tools.
    """

    def __init__(self):
        self._denis = None
        self._tools_initialized = False
        self._tool_status = {}

    def _get_denis(self):
        """Get Denis Persona singleton."""
        if self._denis is None:
            try:
                from kernel.denis_persona import get_denis_persona

                self._denis = get_denis_persona()
            except Exception as e:
                logger.warning(f"Could not load DenisPersona: {e}")
        return self._denis

    async def _init_tools(self):
        """Inicializar todos los tools disponibles."""
        if self._tools_initialized:
            return

        self._tool_status = {
            "rasa": {"available": False, "latency": 0},
            "parlai": {"available": False, "latency": 0},
            "vampirizer": {"available": False, "latency": 0},
            "symbol_cypher": {"available": False, "latency": 0},
            "memory": {"available": False, "latency": 0},
            "control_plane": {"available": False, "latency": 0},
        }

        # Check Rasa
        try:
            from denis_unified_v1.rasa.actions import get_action

            self._tool_status["rasa"]["available"] = True
            logger.info("Tool Rasa: AVAILABLE")
        except Exception as e:
            logger.debug(f"Tool Rasa unavailable: {e}")

        # Check ParLAI
        try:
            from denis_unified_v1.parlai.graph_templates import get_parlai_templates

            get_parlai_templates()
            self._tool_status["parlai"]["available"] = True
            logger.info("Tool ParLAI: AVAILABLE")
        except Exception as e:
            logger.debug(f"Tool ParLAI unavailable: {e}")

        # Check Vampirizer
        try:
            from kernel.nodomac_vampirizer import NodoMacVampirizer

            self._tool_status["vampirizer"]["available"] = True
            logger.info("Tool Vampirizer: AVAILABLE")
        except Exception as e:
            logger.debug(f"Tool Vampirizer unavailable: {e}")

        # Check SymbolCypher
        try:
            from kernel.ghostide.symbol_cypher_router import get_symbol_cypher_router

            get_symbol_cypher_router()
            self._tool_status["symbol_cypher"]["available"] = True
            logger.info("Tool SymbolCypher: AVAILABLE")
        except Exception as e:
            logger.debug(f"Tool SymbolCypher unavailable: {e}")

        # Check Memory
        try:
            from denis_unified_v1.denis_unified_v1.services.human_memory_manager import (
                HumanMemoryManager,
            )

            self._tool_status["memory"]["available"] = True
            logger.info("Tool Memory: AVAILABLE")
        except Exception as e:
            logger.debug(f"Tool Memory unavailable: {e}")

        # Check ControlPlane
        try:
            from control_plane.cp_generator import CPGenerator

            self._tool_status["control_plane"]["available"] = True
            logger.info("Tool ControlPlane: AVAILABLE")
        except Exception as e:
            logger.debug(f"Tool ControlPlane unavailable: {e}")

        self._tools_initialized = True

    async def route(self, prompt: str, session_id: str = "default") -> UnifiedDecision:
        """
        Receives prompt and decides which tools to use.

        Flow:
        1. Initialize tools if needed
        2. Get intent via SymbolCypher or Rasa
        3. Ask Denis for final decision
        4. Return orchestration plan
        """
        await self._init_tools()

        # Step 1: Get intent from SymbolCypher or fallback
        intent = await self._detect_intent(prompt)

        # Step 2: Get symbols context
        symbols = await self._get_symbols(intent, session_id)

        # Step 3: Ask Denis for decision
        denis = self._get_denis()
        if denis:
            try:
                denis_decision = await denis.decide(intent, session_id, [], prompt)
                engine = denis_decision.engine
                reasoning = denis_decision.reasoning
                confidence = denis_decision.confidence
            except Exception as e:
                logger.warning(f"Denis decide failed: {e}")
                engine = "groq_fallback"
                reasoning = "Denis unavailable"
                confidence = 0.3
        else:
            engine = "groq_fallback"
            reasoning = "Denis not loaded"
            confidence = 0.1

        # Step 4: Determine tools to use
        primary_tool, secondary_tools = self._select_tools(intent, symbols)

        return UnifiedDecision(
            intent=intent,
            primary_tool=primary_tool,
            secondary_tools=secondary_tools,
            engine=engine,
            context={
                "symbols": symbols,
                "session_id": session_id,
                "prompt": prompt[:100],
            },
            confidence=confidence,
            reasoning=reasoning,
        )

    async def _detect_intent(self, prompt: str) -> str:
        """Detect intent using available tools."""
        # Try SymbolCypher first
        try:
            from kernel.ghostide.symbol_cypher_router import get_symbol_cypher_router

            cypher = get_symbol_cypher_router()

            keywords = prompt.lower().split()
            for kw in keywords:
                if kw in ["crea", "implementa", "nueva"]:
                    return "implement_feature"
                if kw in ["arregla", "bug", "error"]:
                    return "debug_repo"
                if kw in ["test", "prueba"]:
                    return "run_tests_ci"
                if kw in ["refactor", "migra"]:
                    return "refactor_migration"
                if kw in ["explica", "qué es"]:
                    return "explain_concept"
        except Exception as e:
            logger.debug(f"Intent detection failed: {e}")

        return "implement_feature"

    async def _get_symbols(self, intent: str, session_id: str) -> List[Dict]:
        """Get relevant symbols from graph."""
        try:
            from kernel.ghostide.symbol_cypher_router import get_symbol_cypher_router

            cypher = get_symbol_cypher_router()
            symbols = cypher.get_symbols_context(intent, session_id, limit=5)
            return [{"name": s.name, "path": s.path, "kind": s.kind} for s in symbols]
        except Exception as e:
            logger.debug(f"Get symbols failed: {e}")
            return []

    def _select_tools(self, intent: str, symbols: List[Dict]) -> tuple[str, List[str]]:
        """Select primary and secondary tools based on intent."""

        # Map intents to tool preferences
        tool_prefs = {
            "implement_feature": {
                "primary": "control_plane",
                "secondary": ["symbol_cypher", "vampirizer"],
            },
            "debug_repo": {
                "primary": "control_plane",
                "secondary": ["symbol_cypher", "memory"],
            },
            "run_tests_ci": {
                "primary": "control_plane",
                "secondary": ["parlai"],
            },
            "refactor_migration": {
                "primary": "control_plane",
                "secondary": ["symbol_cypher", "parlai"],
            },
            "explain_concept": {
                "primary": "rasa",
                "secondary": ["memory", "symbol_cypher"],
            },
        }

        prefs = tool_prefs.get(
            intent,
            {
                "primary": "control_plane",
                "secondary": ["symbol_cypher"],
            },
        )

        # Filter to available tools
        primary = (
            prefs["primary"]
            if self._tool_status.get(prefs["primary"], {}).get("available")
            else "control_plane"
        )
        secondary = [s for s in prefs["secondary"] if self._tool_status.get(s, {}).get("available")]

        return primary, secondary

    async def execute_tool(self, tool_name: str, params: Dict) -> ToolResult:
        """Execute a specific tool and return result."""
        import time

        start = time.time()

        try:
            if tool_name == "rasa":
                from denis_unified_v1.rasa.actions import get_action

                action = get_action(params.get("action", "action_session_context"))
                result = action.run(
                    params.get("dispatcher"),
                    params.get("tracker"),
                    params.get("domain"),
                )
                return ToolResult(
                    tool=tool_name,
                    success=True,
                    data=result,
                    latency_ms=(time.time() - start) * 1000,
                )

            elif tool_name == "symbol_cypher":
                from kernel.ghostide.symbol_cypher_router import get_symbol_cypher_router

                cypher = get_symbol_cypher_router()
                result = cypher.get_symbols_context(
                    params.get("intent", ""), params.get("session_id")
                )
                return ToolResult(
                    tool=tool_name,
                    success=True,
                    data=result,
                    latency_ms=(time.time() - start) * 1000,
                )

            elif tool_name == "vampirizer":
                from kernel.nodomac_vampirizer import NodoMacVampirizer

                vamp = NodoMacVampirizer()
                result = await vamp.poll_hf_spaces()
                return ToolResult(
                    tool=tool_name,
                    success=True,
                    data=result,
                    latency_ms=(time.time() - start) * 1000,
                )

            elif tool_name == "control_plane":
                from control_plane.cp_generator import CPGenerator

                gen = CPGenerator()
                result = gen.from_agent_result(params.get("agent_result", {}))
                return ToolResult(
                    tool=tool_name,
                    success=True,
                    data=result.to_dict(),
                    latency_ms=(time.time() - start) * 1000,
                )

            else:
                return ToolResult(
                    tool=tool_name,
                    success=False,
                    data=None,
                    latency_ms=(time.time() - start) * 1000,
                    error=f"Unknown tool: {tool_name}",
                )

        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            return ToolResult(
                tool=tool_name,
                success=False,
                data=None,
                latency_ms=(time.time() - start) * 1000,
                error=str(e),
            )

    def get_tool_status(self) -> Dict:
        """Get status of all tools."""
        return self._tool_status.copy()


# Singleton
_router: Optional[UnifiedRouter] = None


def get_unified_router() -> UnifiedRouter:
    """Get UnifiedRouter singleton."""
    global _router
    if _router is None:
        _router = UnifiedRouter()
    return _router


__all__ = ["UnifiedRouter", "UnifiedDecision", "ToolResult", "get_unified_router"]
