# DENIS Unified - Daily TODO

Fecha: `2026-02-11`  
Estado: `activo`

## Objetivo del día
Cerrar Fase 6 (API unificada incremental) y dejar preparada la entrada a Fase 7.

## Prioridad 1 - Fase 6 (hecho)
- `[x]` Crear módulo `api/` (`fastapi_server.py`, `openai_compatible.py`, `query_interface.py`, `websocket_handler.py`, `sse_handler.py`).
- `[x]` Añadir middleware de auth/rate-limit/trace.
- `[x]` Exponer `/health`, `/v1/models`, `/v1/chat/completions`, `/v1/query/*`, `/v1/events`.
- `[x]` Crear `scripts/phase6_api_smoke.py`.
- `[x]` Validar compat OpenAI + stream + ruta websocket.

Comando ejecutado:
```bash
python3 /home/jotah/denis_unified_v1/scripts/phase6_api_smoke.py \
  --out-json /home/jotah/denis_unified_v1/phase6_api_smoke.json
```

Resultado:
- `phase6_api_smoke.json` con `status=ok`.
- `/health`, `/v1/models`, `/v1/chat/completions`, stream SSE y ruta `/v1/events` validados.

## Prioridad 2 - Siguiente fase
- `[ ]` Iniciar Fase 7 (router de inferencia con métricas y fallback).
- `[ ]` Conectar scoring por latencia/error/costo.
- `[ ]` Añadir smoke de router con fallback controlado.

## Riesgos activos
- `node3` sigue sin ruta por red en smoke de infraestructura.
- Credenciales Neo4j deben venir de config existente o env en ejecución de smokes.

## Rollback rápido Fase 6
```bash
rm -rf /home/jotah/denis_unified_v1/api
rm -f /home/jotah/denis_unified_v1/scripts/phase6_api_smoke.py
```

## Referencias
- Plan maestro: `/home/jotah/denis_unified_v1/REFRACTOR_PHASED_TODO.md`
- Evidencia Fase 3: `/home/jotah/denis_unified_v1/phase3_metagraph_snapshot.json`
- Evidencia Fase 4: `/home/jotah/denis_unified_v1/phase4_autopoiesis_smoke.json`
- Evidencia Fase 5: `/home/jotah/denis_unified_v1/phase5_orchestration_smoke.json`
- Evidencia Fase 6: `/home/jotah/denis_unified_v1/phase6_api_smoke.json`
