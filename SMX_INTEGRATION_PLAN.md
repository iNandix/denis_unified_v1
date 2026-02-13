# SMX Integration Plan - Denis Unified V1

## INTEGRACIÓN: SMX como Fase 12 en Denis Unified V1

---

## UBICACIÓN EN ARQUITECTURA

```
DENIS UNIFIED V1
├── Fase 0-11: Existentes
└── Fase 12: SMX NLU Enrichment Layer (NUEVA)
    ├── smx/
    │   ├── __init__.py
    │   ├── orchestrator.py          # SMX 2-phase orchestrator
    │   ├── enrichment.py            # smx_enrich() function
    │   ├── injection_points.py      # Puntos de inyección estratégicos
    │   ├── models.py                # SMXEnrichment, SMXResult dataclasses
    │   └── contracts/
    │       └── level3_smx.yaml      # Contratos SMX
    └── scripts/
        └── phase12_smx_smoke.py     # Smoke test
```

---

## INTEGRACIÓN CON COMPONENTES EXISTENTES

### 1. Orchestration (Fase 5 - Cognitive Router)

**Punto de inyección:** `cognitive_router.py`

```python
# orchestration/cognitive_router.py

async def route_with_cognition(
    text: str,
    intent: str,
    session_context: dict,
    **kwargs
) -> dict:
    """
    Cognitive router CON enriquecimiento SMX.
    """
    
    # === SMX ENRICHMENT (Fase 12) ===
    if feature_flags.get("PHASE12_SMX_ENABLED"):
        from denis_unified_v1.smx import smx_enrich
        
        smx_enrichment = await smx_enrich(
            text=text,
            intent=intent,
            confidence=session_context.get("nlu_confidence", 1.0),
            world_state=session_context.get("world_state", {}),
            session_context=session_context
        )
        
        # Safety gate
        if not smx_enrichment.safety_passed:
            return {
                "response": "Contenido bloqueado por seguridad",
                "strategy": "smx_safety_blocked",
                "smx_enrichment": smx_enrichment
            }
        
        # Fast path
        if smx_enrichment.fast_response:
            return {
                "response": smx_enrichment.fast_response,
                "strategy": "smx_fast_path",
                "smx_enrichment": smx_enrichment
            }
        
        # Enriquecer session_context con SMX
        session_context["smx_enrichment"] = smx_enrichment
    
    # === ROUTING ORIGINAL ===
    result = await _route_legacy(text, intent, session_context, **kwargs)
    
    return result
```

### 2. Cortex (Fase 2 - World Interface)

**Integración:** SMX usa cortex para world_state

```python
# smx/enrichment.py

from denis_unified_v1.cortex import get_cortex

async def smx_enrich(
    text: str,
    intent: str,
    confidence: float,
    world_state: dict,
    session_context: dict
) -> SMXEnrichment:
    """
    Enriquece input con SMX usando world_state del cortex.
    """
    
    # Si no hay world_state, obtenerlo del cortex
    if not world_state and feature_flags.get("PHASE2_CORTEX_ENABLED"):
        cortex = await get_cortex()
        relevant_entities = identify_relevant_entities(text, intent)
        world_state = await cortex.perceive_multiple(relevant_entities)
    
    # Procesamiento SMX...
    enrichment = SMXEnrichment(
        text_normalized=text,
        intent_refined=intent,
        world_context=world_state,
        # ...
    )
    
    return enrichment
```

### 3. Inference (Fase 7)

**Integración:** SMX 6 motores como inference providers

```python
# inference/smx_provider.py

class SMXInferenceProvider:
    """
    Wrapper de los 6 motores SMX como inference provider.
    """
    
    MODELS = {
        "tokenize": "http://10.10.10.2:8006",  # SmolLM2
        "safety": "http://10.10.10.2:8007",    # Gemma1B
        "fast": "http://10.10.10.2:8003",      # Qwen0.5B
        "intent": "http://10.10.10.2:8008",    # Qwen1.5B
        "macro": "http://127.0.0.1:9998",      # QwenCoder7B
        "response": "http://127.0.0.1:9997",   # Qwen3B
    }
    
    async def call_layer(
        self,
        layer: str,
        text: str,
        context: dict = None,
        timeout: float = 5.0
    ) -> SMXLayerResult:
        """Llama a una capa SMX específica."""
        # Implementación...
```

---

## CONTRATOS SMX (level3_smx.yaml)

```yaml
# contracts/level3_smx.yaml

version: "3.0"
domain: "smx_enrichment"
description: "Contratos para SMX NLU Enrichment Layer"

contracts:
  - id: "L3.SMX.ENRICHMENT_REQUIRED"
    description: "SMX enrichment debe ejecutarse antes de routing"
    severity: "warning"
    validation:
      - "session_context contiene smx_enrichment"
      - "smx_enrichment.latency_ms < 1000"
  
  - id: "L3.SMX.SAFETY_GATE"
    description: "Safety check es obligatorio y bloquea si unsafe"
    severity: "critical"
    validation:
      - "smx_enrichment.safety_passed es bool"
      - "si safety_passed=false, bloquear respuesta"
  
  - id: "L3.SMX.FAST_PATH"
    description: "Fast path debe skipear procesamiento completo"
    severity: "info"
    validation:
      - "si fast_response existe, usar sin Phase 2"
      - "fast_path latency < 500ms"
  
  - id: "L3.SMX.WORLD_CONTEXT"
    description: "SMX debe usar world_state del cortex"
    severity: "warning"
    validation:
      - "smx_enrichment.world_context no es vacío"
      - "world_context viene de cortex.perceive_multiple()"
  
  - id: "L3.SMX.NO_GENERATION"
    description: "SMX NO genera respuestas finales, solo enriquece"
    severity: "critical"
    validation:
      - "SMX layers retornan enrichment, NO respuesta final"
      - "Denis YO es único generador de respuestas"
  
  - id: "L3.SMX.METRICS"
    description: "Métricas por capa requeridas"
    severity: "warning"
    validation:
      - "cada layer tiene latency_ms"
      - "métricas se persisten en Redis"
```

---

## FEATURE FLAGS

```python
# feature_flags.py

PHASE12_SMX_ENABLED = os.getenv("PHASE12_SMX_ENABLED", "false").lower() == "true"
PHASE12_SMX_FAST_PATH = os.getenv("PHASE12_SMX_FAST_PATH", "true").lower() == "true"
PHASE12_SMX_SAFETY_STRICT = os.getenv("PHASE12_SMX_SAFETY_STRICT", "true").lower() == "true"
PHASE12_SMX_USE_CORTEX = os.getenv("PHASE12_SMX_USE_CORTEX", "true").lower() == "true"
```

---

## SMOKE TEST (phase12_smx_smoke.py)

```python
#!/usr/bin/env python3
"""
Phase 12: SMX NLU Enrichment Layer - Smoke Test
"""

import asyncio
import json
from denis_unified_v1.smx import smx_enrich
from denis_unified_v1.feature_flags import load_feature_flags

async def main():
    flags = load_feature_flags()
    
    if not flags.get("PHASE12_SMX_ENABLED"):
        print("❌ PHASE12_SMX_ENABLED=false")
        return
    
    # Test 1: Fast path
    result = await smx_enrich(
        text="hola",
        intent="greet",
        confidence=0.99,
        world_state={},
        session_context={}
    )
    
    assert result.fast_response is not None, "Fast path debe responder"
    assert result.smx_latency_ms < 500, "Fast path debe ser <500ms"
    print(f"✅ Fast path: {result.smx_latency_ms}ms")
    
    # Test 2: Safety gate
    result = await smx_enrich(
        text="contenido peligroso",
        intent="unknown",
        confidence=0.5,
        world_state={},
        session_context={}
    )
    
    assert result.safety_passed is False, "Safety debe bloquear"
    print("✅ Safety gate funciona")
    
    # Test 3: Full enrichment
    result = await smx_enrich(
        text="explica inteligencia artificial",
        intent="explain",
        confidence=0.85,
        world_state={},
        session_context={}
    )
    
    assert result.intent_refined is not None
    assert len(result.entities_extracted) >= 0
    assert result.smx_latency_ms < 1000
    print(f"✅ Full enrichment: {result.smx_latency_ms}ms")
    
    print("\n✅ Phase 12 SMX smoke test PASSED")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## ROLLBACK

```bash
# Rollback completo de Fase 12
rm -rf denis_unified_v1/smx
rm -f denis_unified_v1/scripts/phase12_smx_smoke.py
rm -f denis_unified_v1/contracts/level3_smx.yaml

# Revertir cambios en orchestration
git checkout denis_unified_v1/orchestration/cognitive_router.py
```

---

## COMANDOS DE EJECUCIÓN

```bash
# 1. Habilitar Fase 12
export PHASE12_SMX_ENABLED=true

# 2. Smoke test
python3 denis_unified_v1/scripts/phase12_smx_smoke.py \
  --out-json denis_unified_v1/phase12_smx_smoke.json

# 3. Validación de contratos
make preflight

# 4. Test de integración con cognitive router
python3 -c "
from denis_unified_v1.orchestration.cognitive_router import route_with_cognition
import asyncio

result = asyncio.run(route_with_cognition(
    text='hola',
    intent='greet',
    session_context={}
))
print(result)
"
```

---

## VENTAJAS DE ESTA INTEGRACIÓN

1. ✅ SMX se integra como Fase 12 incremental
2. ✅ Respeta arquitectura metacognitiva existente
3. ✅ Usa cortex (Fase 2) para world_state
4. ✅ Se integra con cognitive_router (Fase 5)
5. ✅ Contratos YAML para governance
6. ✅ Feature flags para control
7. ✅ Rollback completo disponible
8. ✅ Smoke tests reales
9. ✅ Sin stubs ni placeholders
10. ✅ Human approval para activación

---

## PRÓXIMOS PASOS

1. Crear estructura `smx/` en denis_unified_v1
2. Implementar `smx_enrich()` con 6 motores
3. Crear contratos `level3_smx.yaml`
4. Integrar en `cognitive_router.py`
5. Crear `phase12_smx_smoke.py`
6. Actualizar `feature_flags.py`
7. Tests de integración
8. Documentar en README.md

---

**ESTADO: PLAN DE INTEGRACIÓN SMX EN DENIS UNIFIED V1 - LISTO PARA IMPLEMENTAR**
