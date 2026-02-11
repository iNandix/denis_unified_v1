# DENIS Unified - Daily TODO

Fecha: `2026-02-11`  
Estado: `activo`

## Objetivo del día
Cerrar Fase 5 (orchestration augmentation) y dejar preparada la entrada a Fase 6.

## Prioridad 1 - Fase 5 (hecho)
- `[x]` Crear `orchestration/tool_executor.py`.
- `[x]` Crear `scripts/phase5_orchestration_smoke.py`.
- `[x]` Implementar `execute_with_cortex()` con fallback legacy.
- `[x]` Implementar retry/backoff + circuit breaker + logging Redis/Neo4j.
- `[x]` Validar plan de ejecución + degradación controlada por circuito.

Comando ejecutado:
```bash
NEO4J_URI='bolt://10.10.10.1:7687' NEO4J_USER='neo4j' NEO4J_PASSWORD='***' \
python3 /home/jotah/denis_unified_v1/scripts/phase5_orchestration_smoke.py \
  --out-json /home/jotah/denis_unified_v1/phase5_orchestration_smoke.json
```

Resultado:
- `phase5_orchestration_smoke.json` con `status=ok`.
- Plan de 4 tools ejecutado con `tools_succeeded=4`.
- Circuit breaker confirmado tras fallos consecutivos en `legacy.always_fail`.

## Prioridad 2 - Siguiente fase
- `[ ]` Iniciar Fase 6 (API unificada OpenAI-compatible incremental).
- `[ ]` Añadir rutas nuevas sin romper contrato actual.
- `[ ]` Definir smoke de `/health`, `/v1/models`, `/v1/chat/completions`.

## Riesgos activos
- `node3` sigue sin ruta por red en smoke de infraestructura.
- Credenciales Neo4j deben venir de config existente o env en ejecución de smokes.

## Rollback rápido Fase 5
```bash
rm -rf /home/jotah/denis_unified_v1/orchestration
rm -f /home/jotah/denis_unified_v1/scripts/phase5_orchestration_smoke.py
```

## Referencias
- Plan maestro: `/home/jotah/denis_unified_v1/REFRACTOR_PHASED_TODO.md`
- Evidencia Fase 3: `/home/jotah/denis_unified_v1/phase3_metagraph_snapshot.json`
- Evidencia Fase 4: `/home/jotah/denis_unified_v1/phase4_autopoiesis_smoke.json`
- Evidencia Fase 5: `/home/jotah/denis_unified_v1/phase5_orchestration_smoke.json`
