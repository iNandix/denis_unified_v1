# DENIS Unified - Daily TODO

Fecha: `2026-02-11`  
Estado: `activo`

## Objetivo del día
Cerrar Fase 4 (autopoiesis supervisada) y dejar preparada la entrada a Fase 5.

## Prioridad 1 - Fase 4 (hecho)
- `[x]` Crear `autopoiesis/proposal_engine.py`.
- `[x]` Crear `autopoiesis/dashboard.py`.
- `[x]` Crear `scripts/phase4_autopoiesis_smoke.py`.
- `[x]` Validar generación de propuestas + sandbox rollback + aprobación supervisada.

Comando ejecutado:
```bash
NEO4J_URI='bolt://10.10.10.1:7687' NEO4J_USER='neo4j' NEO4J_PASSWORD='***' \
python3 /home/jotah/denis_unified_v1/scripts/phase4_autopoiesis_smoke.py \
  --approve-first \
  --out-json /home/jotah/denis_unified_v1/phase4_autopoiesis_smoke.json
```

Resultado:
- `phase4_autopoiesis_smoke.json` con `status=ok`.
- `generated_count=2`.
- Sandbox con `rollback` y counters de cambios simulados.

## Prioridad 2 - Siguiente fase
- `[ ]` Iniciar Fase 5 (`orchestration` incremental con fallback legacy).
- `[ ]` Definir primer smoke de `execute_with_cortex()`.
- `[ ]` Añadir métrica de success-rate y latencia p95 comparada.

## Riesgos activos
- `node3` sigue sin ruta por red en smoke de infraestructura.
- Credenciales Neo4j deben venir de config existente o env en ejecución de smokes.

## Rollback rápido Fase 4
```bash
rm -rf /home/jotah/denis_unified_v1/autopoiesis
rm -f /home/jotah/denis_unified_v1/scripts/phase4_autopoiesis_smoke.py
```

## Referencias
- Plan maestro: `/home/jotah/denis_unified_v1/REFRACTOR_PHASED_TODO.md`
- Evidencia Fase 3: `/home/jotah/denis_unified_v1/phase3_metagraph_snapshot.json`
- Evidencia Fase 4: `/home/jotah/denis_unified_v1/phase4_autopoiesis_smoke.json`

