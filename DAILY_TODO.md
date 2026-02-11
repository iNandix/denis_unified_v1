# DENIS Unified - Daily TODO

Fecha: `2026-02-11`  
Estado: `activo`

## Objetivo del día
Cerrar el bloqueo de `Fase 1 (World Cortex/HASS)` y preparar arranque de `Fase 3 (Metagraph pasivo)` sin impacto en legacy.

## Prioridad 1 - Desbloquear HASS en Cortex
- `[ ]` Validar token HASS vigente (long-lived token correcto).
- `[ ]` Ejecutar smoke Cortex con config auto-resuelta.
- `[ ]` Confirmar `perceive_hass -> status=ok`.

Comando:
```bash
python3 /home/jotah/denis_unified_v1/scripts/phase2_cortex_smoke.py \
  --execute \
  --out-json /home/jotah/denis_unified_v1/phase2_cortex_smoke_execute.json
```

Criterio de done:
- En `phase2_cortex_smoke_execute.json`, `checks[perceive_hass].result.status == "ok"`.

## Prioridad 2 - Validación de estabilidad post-fase
- `[ ]` Regenerar baseline (`8084` core real).
- `[ ]` Confirmar `/health` `8084` y `8086` en `ok`.

Comando:
```bash
python3 /home/jotah/denis_unified_v1/scripts/unified_v1_baseline_check.py \
  --out-md /home/jotah/denis_unified_v1/DENIS_BASELINE.md \
  --out-json /home/jotah/denis_unified_v1/baseline_report.json
```

Criterio de done:
- `baseline_report.json.health` con `8084` y `8086` en `ok=true`.

## Prioridad 3 - Preparar Fase 3 (metagraph pasivo)
- `[ ]` Crear `metagraph/observer.py` (solo lectura).
- `[ ]` Crear `metagraph/pattern_detector.py` (solo reporte).
- `[ ]` Crear `metagraph/dashboard.py` (read-only).
- `[ ]` Definir salida de métricas (`json`) con timestamp y contadores base.

Criterio de done:
- Existe reporte de metagraph sin escritura en estructura de grafo.

## Riesgos hoy
- Token HASS inválido (bloquea prioridad 1).
- SSH a `node1` puede seguir denegado por llave; no bloquea Fase 1 si `node2` y ping están OK.

## Rollback rápido (si hay problema)
```bash
rm -f /home/jotah/denis_unified_v1/DAILY_TODO.md
```

## Referencias
- Plan maestro: `/home/jotah/denis_unified_v1/REFRACTOR_PHASED_TODO.md`
- Estado baseline: `/home/jotah/denis_unified_v1/baseline_report.json`
- Estado quantum: `/home/jotah/denis_unified_v1/phase1_augment_execute.json`
- Estado cortex: `/home/jotah/denis_unified_v1/phase2_cortex_smoke_execute.json`

