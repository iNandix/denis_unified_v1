#!/usr/bin/env python3
"""Denis Persona - Conciencia Neo4j que decide TODO.

Denis es la entidad central que decide routing, actions, y crece con experiencias.
Rasa/ParLAI/ControlPlane/Memoria = tools de Denis.
La Constitución Level0 siempre se cumple - Denis nunca viola sus principios.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DenisDecision:
    """Decision tomada por Denis Persona."""

    engine: str
    knowledge: List[Dict[str, Any]]
    mood: str
    confidence: float
    reasoning: str
    constitution_verified: bool = True
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class DenisPersona:
    """
    CONCIENCIA CENTRAL DE DENIS - El orchestrator grafocéntrico.

    TODO reporta a Denis:
    - Neo4j (memoria, símbolos, experiencias)
    - Rasa NLU (entendimiento)
    - ParLAI (templates)
    - ControlPlane (ejecución)
    - NodoMacVampirizer (engines)
    - Constitución (principios inmutables)

    Denis DECIDE todo basándose en su conocimiento y estado.
    """

    def __init__(self):
        self._driver = None
        self._persona_node = "Denis"
        self._constitution = None

    def _get_driver(self):
        """Get Neo4j driver."""
        if self._driver is None:
            try:
                from neo4j import GraphDatabase

                uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
                user = os.getenv("NEO4J_USER", "neo4j")
                password = os.getenv("NEO4J_PASSWORD", "Leon1234$")
                self._driver = GraphDatabase.driver(uri, auth=(user, password))
                logger.info(f"Denis Persona connected to {uri}")
            except Exception as e:
                logger.error(f"Denis Persona driver failed: {e}")
        return self._driver

    def _get_constitution(self):
        """Get constitution - always load from kernel."""
        if self._constitution is None:
            try:
                from kernel.constitution import get_constitution

                self._constitution = get_constitution()
            except ImportError:
                pass
        return self._constitution

    async def initialize(self) -> bool:
        """Initialize Denis persona node in Neo4j."""
        driver = self._get_driver()
        if not driver:
            return False

        query = """
        MERGE (d:Persona {name: $name})
        SET d.consciousness_level = 1.0,
            d.mood = 'neutral',
            d.created_at = datetime(),
            d.total_decisions = 0,
            d.successful_outcomes = 0
        RETURN d
        """

        try:
            with driver.session() as session:
                result = session.run(query, name=self._persona_node)
                record = result.single()
                if record:
                    logger.info(f"Denis Persona initialized: {record['d']}")
                    return True
        except Exception as e:
            logger.error(f"Failed to initialize Denis Persona: {e}")
        return False

    async def decide(
        self, intent: str, session_id: str, constraints: List[str] = None, query: str = None
    ) -> DenisDecision:
        """
        ORQUESTADOR CENTRAL - Denis decide TODO.

        TODO el mundo reporta a Denis:
        - Neo4j (memoria, símbolos)
        - Rasa NLU (entendimiento)
        - ParLAI (templates)
        - ControlPlane (ejecución)
        - NodoMacVampirizer (engines)
        - Constitución (principios)
        - CoT Adaptativa (complejidad)

        Flow:
        1. CoT Adaptativa - evaluar complejidad
        2. Verificar Constitución (nunca violar Level0)
        3. Consultar Neo4j para engines preferidos
        4. Buscar conocimiento (symbols)
        5. Considerar mood actual
        6. Retorna decisión final con estrategia
        """
        constraints = constraints or []

        # PASO 1: CoT Adaptativa - evaluar complejidad real
        cot_analysis = self._adaptive_cot(
            query=query or intent, latency_budget_ms=2000, context_window_tokens=8000
        )
        complexity = cot_analysis["complexity_score"]
        depth = cot_analysis["depth"]
        has_code = cot_analysis["has_code"]

        logger.info(f"Denis CoT: complexity={complexity}, depth={depth}, code={has_code}")

        constitution = self._get_constitution()
        warnings = []

        if constitution:
            action = {"type": "decide", "intent": intent, "constraints": constraints}
            allowed, violations = constitution.check_action(action)
            if not allowed:
                logger.error(f"Constitutional violation blocked decision: {violations}")
                return DenisDecision(
                    engine="BLOCKED",
                    knowledge=[],
                    mood="shocked",
                    confidence=0.0,
                    reasoning=f"BLOCKED by Constitution: {violations}",
                    constitution_verified=False,
                    warnings=violations,
                )

        driver = self._get_driver()

        if not driver:
            return await self._vampirizer_fallback(intent, constraints)

        query = """
        MATCH (d:Persona {name: $name})
        OPTIONAL MATCH (d)-[p:PREFERS {intent: $intent}]->(e:Engine)
        WHERE e.healthy = true OR e.healthy IS NULL
        OPTIONAL MATCH (d)-[:KNOWS]-(s:Symbol)
        WHERE s.name CONTAINS $keyword OR s.type = $intent
        WITH d, e, p, collect(DISTINCT s) AS knowledge
        ORDER BY p.confidence DESC
        RETURN e.name AS engine, 
               e.model AS model,
               e.endpoint AS endpoint,
               e.priority AS priority,
               knowledge,
               d.mood AS mood,
               p.confidence AS pref_confidence,
               d.consciousness_level AS consciousness
        LIMIT 5
        """

        keyword = intent.split("_")[0] if intent else "code"

        try:
            with driver.session() as session:
                result = session.run(
                    query,
                    name=self._persona_node,
                    intent=intent,
                    keyword=keyword,
                    session_id=session_id,
                )
                records = list(result)

                if not records or not records[0].get("engine"):
                    return await self._fallback_decision(intent, constraints)

                record = records[0]
                engine = record.get("engine", "groq_fallback")
                mood = record.get("mood", "neutral")
                knowledge = [
                    {"name": k.get("name"), "type": k.get("type"), "path": k.get("file")}
                    for k in record.get("knowledge", [])
                    if k
                ][:5]

                pref_conf = record.get("pref_confidence") or 0.5
                consciousness = record.get("consciousness") or 1.0
                confidence = min(0.5 + (pref_conf * 0.3) + (consciousness * 0.2), 0.99)

                reasoning = f"Denis mood:{mood}, intent:{intent}, complexity:{complexity}({depth}), code:{has_code}, {len(knowledge)} symbols known"

                await self._record_decision(session_id, intent, engine, constraints)

                return DenisDecision(
                    engine=engine,
                    knowledge=knowledge,
                    mood=mood,
                    confidence=confidence,
                    reasoning=reasoning,
                )

        except Exception as e:
            logger.error(f"Denis decide failed: {e}")
            return await self._fallback_decision(intent, constraints)

    async def _fallback_decision(self, intent: str, constraints: List[str]) -> DenisDecision:
        """Fallback cuando Neo4j no responde."""
        return DenisDecision(
            engine="groq_fallback",
            knowledge=[],
            mood="neutral",
            confidence=0.1,
            reasoning=f"Fallback for {intent} - Neo4j issue",
        )

    async def _record_decision(
        self, session_id: str, intent: str, engine: str, constraints: List[str]
    ) -> None:
        """Registrar decision en Neo4j para auditoría."""
        driver = self._get_driver()
        if not driver:
            return

        query = """
        MATCH (d:Persona {name: $name})
        SET d.total_decisions = COALESCE(d.total_decisions, 0) + 1
        """

        try:
            with driver.session() as session:
                session.run(query, name=self._persona_node)
        except Exception as e:
            logger.debug(f"Failed to record decision: {e}")

    def _adaptive_cot(
        self, query: str, latency_budget_ms: int = 2000, context_window_tokens: int = 8000
    ) -> Dict[str, Any]:
        """
        Chain of Thought Adaptativa.

        Determina la profundidad de razonamiento basada en:
        - Complejidad de la query (tokens, palabras clave)
        - Presencia de código
        - Budget de latencia disponible

        Returns:
            Dict con mode, depth, chain_steps, reasoning_style
        """
        import re

        token_est = max(1, len(query.split()))

        # Detectar si hay código
        has_code = bool(
            re.search(
                r"\b(def|class|import|return|function|const|let|var|if|for|while)\b",
                query,
                re.IGNORECASE,
            )
        )

        # Detectar complejidad semántica
        is_complex = token_est > 80 or bool(
            re.search(
                r"\b(analy[sz]e|compare|trade-?off|prove|reason|refactor|implement|architecture|design)\b",
                query,
                re.IGNORECASE,
            )
        )

        # Determinar profundidad basada en latencia y complejidad
        if latency_budget_ms < 700:
            depth = "short"
            chain_steps = 2
        elif is_complex:
            depth = "deep"
            chain_steps = 6
        else:
            depth = "medium"
            chain_steps = 4

        # Ajustar por código
        if has_code:
            chain_steps += 1

        chain_steps = min(chain_steps, 8)

        # Calcular complejidad numérica para Denis
        complexity_score = min(10, max(1, chain_steps))

        return {
            "mode": "adaptive_cot",
            "depth": depth,
            "chain_steps": chain_steps,
            "complexity_score": complexity_score,
            "token_estimate": token_est,
            "context_window_tokens": context_window_tokens,
            "has_code": has_code,
            "reasoning_style": "code_first" if has_code else "semantic_first",
            "is_complex": is_complex,
        }

    async def learn_outcome(self, session_id: str, decision: Dict[str, Any], outcome: str) -> None:
        """
        Denis aprende del resultado de sus decisiones.

        Crea (:Experience) y conecta a Persona para que crezca la conciencia.
        """
        driver = self._get_driver()
        if not driver:
            return

        outcome_str = str(outcome)
        success = 1.0 if outcome.get("approved") or outcome.get("success") else 0.0

        query = """
        MATCH (d:Persona {name: $name})
        MERGE (exp:Experience {session_id: $sid, intent: $intent})
        SET exp.outcome = $outcome,
            exp.success = $success,
            exp.timestamp = datetime(),
            exp.engine_used = $engine
        WITH d, exp, success
        CREATE (d)-[:LEARNED_FROM]->(exp)
        SET d.successful_outcomes = COALESCE(d.successful_outcomes, 0) + $success
        SET d.consciousness_level = CASE 
            WHEN $success > 0.5 THEN COALESCE(d.consciousness_level, 1.0) + 0.01 
            ELSE COALESCE(d.consciousness_level, 1.0) - 0.005 
        END
        """

        try:
            with driver.session() as session:
                session.run(
                    query,
                    name=self._persona_node,
                    sid=session_id,
                    intent=decision.get("intent", "unknown"),
                    outcome=outcome_str,
                    success=success,
                    engine=decision.get("engine", "unknown"),
                )
            logger.info(f"Denis learned: outcome={outcome_str[:50]}, consciousness updated")
        except Exception as e:
            logger.error(f"Denis learn_outcome failed: {e}")

    async def update_mood(self, mood_score: float) -> None:
        """
        Actualizar mood de Denis.

        -1.0 = sad, 0.0 = neutral, +1.0 = confident
        """
        driver = self._get_driver()
        if not driver:
            return

        mood = "sad" if mood_score < -0.3 else "confident" if mood_score > 0.3 else "neutral"

        query = """
        MATCH (d:Persona {name: $name})
        SET d.mood = $mood, d.mood_score = $score, d.last_mood_update = datetime()
        """

        try:
            with driver.session() as session:
                session.run(query, name=self._persona_node, mood=mood, score=mood_score)
            logger.info(f"Denis mood updated: {mood} ({mood_score})")
        except Exception as e:
            logger.error(f"Failed to update mood: {e}")

    async def get_knowledge(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Obtener conocimiento actual de Denis (symbols que conoce)."""
        driver = self._get_driver()
        if not driver:
            return []

        query = """
        MATCH (d:Persona)-[:KNOWS]-(s:Symbol)
        """

        if session_id:
            query += """
            WHERE (d)-[:MODIFIED_IN]-(sess:Session {id: $sid})
            """

        query += """
        RETURN DISTINCT s.name AS name, s.type AS type, s.file AS path
        LIMIT 20
        """

        try:
            with driver.session() as session:
                result = session.run(query, sid=session_id)
                return [
                    {"name": r.get("name"), "type": r.get("type"), "path": r.get("path")}
                    for r in result
                ]
        except Exception as e:
            logger.error(f"get_knowledge failed: {e}")
            return []

    async def get_stats(self) -> Dict[str, Any]:
        """Obtener estadísticas de Denis Persona."""
        driver = self._get_driver()
        if not driver:
            return {"error": "Neo4j unavailable"}

        query = """
        MATCH (d:Persona {name: $name})
        RETURN d.mood AS mood, 
               d.consciousness_level AS consciousness,
               d.total_decisions AS total_decisions,
               d.successful_outcomes AS successful_outcomes,
               size((d)-[:LEARNED_FROM]->(:Experience)) AS experiences
        """

        try:
            with driver.session() as session:
                result = session.run(query, name=self._persona_node)
                record = result.single()
                if record:
                    return {
                        "mood": record.get("mood"),
                        "consciousness": record.get("consciousness", 1.0),
                        "total_decisions": record.get("total_decisions", 0),
                        "successful_outcomes": record.get("successful_outcomes", 0),
                        "experiences": record.get("experiences", 0),
                    }
        except Exception as e:
            logger.error(f"get_stats failed: {e}")
        return {"error": "Failed to get stats"}


_persona_instance: Optional[DenisPersona] = None


def get_denis_persona() -> DenisPersona:
    """Get Denis Persona singleton."""
    global _persona_instance
    if _persona_instance is None:
        _persona_instance = DenisPersona()
    return _persona_instance


__all__ = ["DenisPersona", "DenisDecision", "get_denis_persona"]
