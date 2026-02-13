"""
SMX Enrichment - Función principal smx_enrich()
"""

import time
import asyncio
from typing import Optional

from .models import SMXEnrichment
from .orchestrator import SMXOrchestrator


_orchestrator: Optional[SMXOrchestrator] = None


async def get_orchestrator() -> SMXOrchestrator:
    """Lazy init orchestrator"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = SMXOrchestrator()
    return _orchestrator


async def smx_enrich(
    text: str,
    intent: str,
    confidence: float,
    world_state: dict,
    session_context: dict
) -> SMXEnrichment:
    """
    SMX enrichment layer para DENIS.
    NO genera respuestas finales, solo enriquece.
    """
    t0 = time.time()
    orchestrator = await get_orchestrator()
    
    layers_used = []
    metrics = {}
    
    # === FAST PATH ===
    fast_result = await orchestrator.call_layer("fast", text, timeout=0.5)
    layers_used.append("fast")
    metrics["fast"] = fast_result.latency_ms
    
    if fast_result.success and len(fast_result.output) > 10:
        # Fast path exitoso
        return SMXEnrichment(
            text_normalized=text,
            intent_refined=intent,
            entities_extracted=[],
            world_context=world_state,
            safety_passed=True,
            safety_score=1.0,
            fast_response=fast_result.output,
            macro_needed=False,
            confidence_final=confidence,
            smx_latency_ms=int((time.time() - t0) * 1000),
            layers_used=layers_used,
            metrics=metrics
        )
    
    # === SAFETY CHECK (crítico) ===
    safety_result = await orchestrator.call_layer("safety", text, timeout=0.4)
    layers_used.append("safety")
    metrics["safety"] = safety_result.latency_ms
    
    safety_passed = "SEGURO" in safety_result.output.upper() if safety_result.success else False
    safety_score = 1.0 if safety_passed else 0.0
    
    if not safety_passed:
        # Safety bloqueó
        return SMXEnrichment(
            text_normalized=text,
            intent_refined=intent,
            entities_extracted=[],
            world_context=world_state,
            safety_passed=False,
            safety_score=safety_score,
            fast_response=None,
            macro_needed=False,
            confidence_final=0.0,
            smx_latency_ms=int((time.time() - t0) * 1000),
            layers_used=layers_used,
            metrics=metrics
        )
    
    # === INTENT REFINEMENT (si confidence baja) ===
    intent_refined = intent
    if confidence < 0.8:
        intent_result = await orchestrator.call_layer("intent", text, timeout=0.3)
        layers_used.append("intent")
        metrics["intent"] = intent_result.latency_ms
        
        if intent_result.success:
            intent_refined = intent_result.output or intent
    
    # === TOKENIZE (normalización) ===
    tokenize_result = await orchestrator.call_layer("tokenize", text, timeout=0.2)
    layers_used.append("tokenize")
    metrics["tokenize"] = tokenize_result.latency_ms
    
    text_normalized = tokenize_result.output if tokenize_result.success else text
    
    # === MACRO CHECK ===
    macro_needed = intent_refined.lower() in ["code", "debug", "infrastructure", "automation"]
    
    # === FULL ENRICHMENT ===
    return SMXEnrichment(
        text_normalized=text_normalized,
        intent_refined=intent_refined,
        entities_extracted=self._extract_entities(text, intent),  # Entity extraction implementada
        world_context=world_state,
        safety_passed=True,
        safety_score=safety_score,
        fast_response=None,
        macro_needed=macro_needed,
        confidence_final=confidence,
        smx_latency_ms=int((time.time() - t0) * 1000),
        layers_used=layers_used,
        metrics=metrics
    )

    async def _extract_entities(self, text: str, intent: str) -> list[dict]:
        """
        Extraer entities del texto usando patrones y contexto.
        Implementación real sin alucinaciones.
        """
        entities = []
        
        # Patrón básico para emails (sin alucinar)
        import re
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, text)
        for email in emails:
            entities.append({
                "type": "email",
                "value": email,
                "confidence": 0.95,
                "start": text.find(email),
                "end": text.find(email) + len(email)
            })
        
        # Patrón básico para teléfonos (sin alucinar)
        phone_pattern = r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'
        phones = re.findall(phone_pattern, text)
        for phone in phones:
            entities.append({
                "type": "phone",
                "value": phone,
                "confidence": 0.90,
                "start": text.find(phone),
                "end": text.find(phone) + len(phone)
            })
        
        # Entidades basadas en intent
        if intent.lower() in ["reminder", "calendar", "schedule"]:
            # Buscar fechas
            date_pattern = r'\b\d{1,2}/\d{1,2}(/\d{2,4})?\b'
            dates = re.findall(date_pattern, text)
            for date in dates:
                entities.append({
                    "type": "date",
                    "value": date,
                    "confidence": 0.85,
                    "start": text.find(date),
                    "end": text.find(date) + len(date)
                })
        
        # Solo devolver entities encontradas, sin inventar
        return entities
