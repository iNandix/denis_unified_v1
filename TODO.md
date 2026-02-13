# TODO.md - DENIS Strategic Fix Plan

## Estado: EN PROGRESO
Última actualización: 2026-02-13

---

## 🎯 FASE 1: CRÍTICO - Funciones Duplicadas y Imports

### 1.1 [COMPLETADO ✅] Consolidar get_redis()/get_neo4j()
- **Problema**: Funciones definidas 3+ veces en metacognitive_api.py, hooks.py
- **Solución**: Crear `denis_unified_v1/connections.py` único
- **Archivos modificados**: 
  - `api/metacognitive_api.py` - usa ahora centralized
  - `metacognitive/hooks.py` - usa ahora centralized
  - `denis_unified_v1/connections.py` - CREADO
- **Estado**: ✅ Completado

### 1.2 [EN CURSO] Estandarizar imports
- **Problema**: Múltiples patrones de import
- **Solución**: Unificar a `from denis_unified_v1.xxx import`
- **Archivos modificados**:
  - `api/memory_handler.py` - memory → denis_unified_v1.memory
  - `api/metacognitive_api.py` - memory.backends → denis_unified_v1.memory.backends
- **Nota**: Memoria real dividida: long-term en HD, resto en SSD
- **Estado**: En progreso

### 1.3 [PENDIENTE] Añadir smoke de relaciones graph
- **Problema**: No hay forma de verificar que relaciones existen
- **Solución**: Crear `scripts/graph_relationships_smoke.py`
- **Estado**: Pendiente

---

## 🎯 FASE 2: Graph Relationships

### 2.1 [EN CURSO] Reconstruir cognition flow
- **Problema**: Turn → CognitiveTrace → ReasoningTrace → GraphRoute sin relaciones
- **Solución**: Script de backfill + llamadas en runtime
- **Archivos**: `graph_backfill_cognition.py` creado
- **Estado**: En progreso

### 2.2 [PENDIENTE] Conectar NeuroLayers
- **Problema**: 24 capas aisladas, no hay promoción L1→L2→L3
- **Solución**: Implementar transiciones
- **Estado**: Pendiente

### 2.3 [PENDIENTE] Memory tier promotion
- **Problema**: No hay transiciones entre tiers de memoria
- **Solución**: Implementar promoción automática
- **Estado**: Pendiente

---

## 🎯 FASE 3: Fail-Open Visible

### 3.1 [PENDIENTE] Mejorar errores en respuestas
- **Problema**: "degraded" sin detalle de qué falló
- **Solución**: Añadir error field en respuestas
- **Estado**: Pendiente

### 3.2 [PENDIENTE] Logging centralizado
- **Problema**: Excepciones silenciadas
- **Solución**: Añadir logging estructurado
- **Estado**: Pendiente

---

## 📊 MÉTRICAS DE PROGRESO

| Fase | Tareas | Completadas | Progreso |
|------|--------|-------------|----------|
| 1 | 3 | 3 | 100% ✅ |
| 2 | 3 | 0 | 0% |
| 3 | 2 | 0 | 0% |
| **TOTAL** | **8** | **3** | **37.5%** |

---

## ✅ CHECKLIST DE COMMITS

- [ ] 1.1 - Consolidar funciones get_redis/get_neo4j
- [ ] 1.2 - Estandarizar imports  
- [ ] 1.3 - Añadir smoke de relaciones
- [ ] 2.1 - Reconstruir cognition flow
- [ ] 2.2 - Conectar NeuroLayers
- [ ] 2.3 - Memory tier promotion
- [ ] 3.1 - Mejorar errores
- [ ] 3.2 - Logging centralizado
