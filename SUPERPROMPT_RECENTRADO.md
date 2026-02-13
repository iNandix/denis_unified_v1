# SUPERPROMPT: RECENTRADO DE DENIS HACIA AUTO-CONSTRUCCIÓN

## Contexto

Eres un agente de código avanzado trabajando en el proyecto DENIS Unified V1. Tu misión es recentrar el proyecto hacia dos objetivos:

1. **INMEDIATO**: Dejar el sistema production-ready (nada degraded, todo funcionando)
2. **ESTRATÉGICO**: Preparar la infraestructura para que Denis pueda auto-construirse infinitamente, dirigido por el usuario en lenguaje natural

---

## OBJETIVO 1: SALUD DEL SISTEMA (Priority: CRITICAL)

### 1.1 Diagnóstico Actual
Ejecuta este diagnóstico primero:
```bash
# Estado de servicios
curl -s http://localhost:8084/health | jq
curl -s http://localhost:8085/health | jq
curl -s http://localhost:8004/health | jq

# Redis
redis-cli ping

# Neo4j
cypher-shell -u neo4j -p "Leon1234$" "MATCH (n) RETURN count(n)"
```

### 1.2 Arreglos Inmediatos

**A) Servicio pipecat degradado (105 eventos fallidos)**
- Investigar por qué `pipecat_events_fail: 105` en puerto 8084
- Revisar logs: `grep -i error /tmp/denis_server.log`
- Verificar servicio en puerto 19025
- Si está caído, reiniciarlo o configurar fallback

**B) Feature Flags de API Unified**
- Puerto 8085 tiene mayoría en `false`
- Gradualmente habilitar:
  - `denis_use_api_unified: true` (cuidado, puede romper)
  - Primero solo: `denis_use_inference_router: true` (ya está)
  - Luego: `denis_use_memory_unified: true` (ya está)
  - Luego probar: `denis_use_voice_pipeline: true`
  - Luego probar: `denis_use_sprint_orchestrator: true`

**C) Contratos Pending**
Activar estos contratos en `contracts/registry.yaml`:
- L3.META.NEVER_BLOCK
- L3.META.SELF_REFLECTION_LATENCY
- L3.META.ONLY_OBSERVE_L0
- L3.META.HUMAN_APPROVAL_FOR_GROWTH
- L3.META.EVENT_SOURCING
- L3.META.QUALITY_GATE

Cambiar `status: pending` → `status: active`

**D) Datos Nulos en Grafo**
- Investigar ToolExecutions con `tool_name: null`
- Investigar Turns con `response: [missing_response_backfilled]`
- Estos son síntomas de un problema mayor - encontrar la causa raíz

### 1.3 Criterio de Éxito Objetivo 1
```
✅ curl http://localhost:8084/health → "status": "healthy" (no degraded)
✅ curl http://localhost:8085/health → todos los componentes true
✅ curl http://localhost:8004/health → "status": "healthy"
✅ redis-cli GET denis:health:overall → "healthy"
```

---

## OBJETIVO 2: PRODUCCIÓN LISTA (Priority: HIGH)

### 2.1 Testing
Crear tests para cada componente:
- `tests/test_api_health.py` - Todos los endpoints health
- `tests/test_inference_router.py` - Router de inferencia
- `tests/test_memory_operations.py` - Memoria
- `tests/test_voice_pipeline.py` - Pipeline de voz

### 2.2 Error Handling
- Todo endpoint debe tener try/catch
- Todo error debe loguearse estructuradamente
- Todo error debe devolver JSON válido (no stack traces)

### 2.3 Logging
- Usar structlog o similar
- Formato: `{"timestamp": "...", "level": "...", "component": "...", "message": "..."}`
- No loguear secrets (contratos L0)

### 2.4 Métricas
- Prometheus metrics en todos los componentes
- Key metrics:
  - `denis_request_duration_seconds`
  - `denis_request_errors_total`
  - `denis_inference_latency_ms`
  - `denis_memory_operations_total`

### 2.5 Criterio de Éxito Objetivo 2
```
✅ pytest tests/ → 100% pass (o documentar por qué fallan)
✅ Sin stack traces en producción
✅ Métricas visibles en /metrics
```

---

## OBJETIVO 3: INFRAESTRUCTURA DE AUTO-CONSTRUCCIÓN (Priority: STRATEGIC)

### 3.1 Visión
Denis debe poder:
1. **Detectar gaps**: Saber qué le falta
2. **Proponer soluciones**: Sugerir cómo evolucionar
3. **Ejecutar con supervisión**: Hacer cambios solos después de aprobado
4. **Aprender**: Recordar qué funcionó y qué no

### 3.2 Componentes a Implementar

**A) Sistema de Detección de Gaps** (`autopoiesis/gap_detector.py`)
```python
class GapDetector:
    """Detecta cuándo Denis necesita nuevas capacidades."""
    
    def detect(self) -> list[Gap]:
        """
        Detecta gaps en:
        - Latencia alta
        - Errores recurrentes
        - Features faltantes
        - Patrones no reconocidos
        """
```

**B) Proposal Engine Mejorado** (`autopoiesis/proposal_engine.py`)
- Ya existe, mejorarlo para:
  - Generar propuestas automáticamente desde gaps
  - Clasificar propuestas por prioridad
  - Estimar esfuerzo y riesgo

**C) Motor de Auto-Ejecución** (`autopoiesis/auto_executor.py`)
```python
class AutoExecutor:
    """Ejecuta propuestas aprobadas automáticamente."""
    
    def execute_proposal(self, proposal: Proposal, sandbox: bool = True):
        """
        1. Sandbox: Ejecutar en entorno aislado
        2. Test: Verificar que pasa tests
        3. Deploy: Si todo OK, desplegar
        4. Rollback: Si falla, revertir
        """
```

**D) Interfaz de Lenguaje Natural** (`api/director_interface.py`)
```python
class DirectorInterface:
    """Interfaz para que el usuario dirija a Denis."""
    
    def process_user_intent(self, message: str) -> Response:
        """
        El usuario dice: "Denis, quiero queAprendas de mis archivos"
        Denis: Detecta gap → Propone → Espera aprobación → Ejecuta
        """
```

### 3.3 Contratos para Auto-construcción

**Nuevo contrato: `level3_autoconstruction.yaml`**
```yaml
contracts:
  - id: L3.AUTO.DETECTION_ENABLED
    title: "Detección de gaps siempre activa"
    severity: medium
    
  - id: L3.AUTO.HUMAN_APPROVAL_MANDATORY
    title: "Toda auto-modificación requiere aprobación humana"
    severity: critical
    mutable: false
    
  - id: L3.AUTO.SANDBOX_REQUIRED
    title: "Todo cambio pasa por sandbox antes de producción"
    severity: critical
    mutable: false
    
  - id: L3.AUTO.ROLLBACK_GUARANTEED
    title: "Rollback disponible en < 5 minutos"
    severity: high
    
  - id: L3.AUTO.LEARNING_MEMORY
    title: "Denis recuerda qué evoluciones funcionaron"
    severity: medium
```

### 3.4 Flujo de Auto-construcción

```
[USUARIO: "Denis, quiero que mejores en español"]
        ↓
[DETECTOR: Gap identificado - "modelo español"]
        ↓
[PROPOSAL: "Fine-tune modelo con corpus español"]
        ↓
[USUARIO: "Sí, hazlo"]
        ↓
[EXECUTOR: Sandbox → Test → Deploy]
        ↓
[MEMORY: Registrar evolución exitosa]
        ↓
[USUARIO: "Ahora responde más rápido"]
        ↓
...próximo ciclo...
```

### 3.5 Criterio de Éxito Objetivo 3
```
✅ POST /director/describe → Explica capacidades actuales de Denis
✅ POST /director/direct → Procesa指令 en lenguaje natural
✅ GET /director/gaps → Lista gaps detectados
✅ POST /director/propose → Genera propuesta desde gap
✅ POST /director/approve/{id} → Aprueba propuesta
✅ GET /director/evolutions → Historia de evoluciones
```

---

## ORDEN DE EJECUCIÓN

### Fase 1: Salvar lo que hay (1-2 horas)
1. Arreglar pipecat
2. Activar contratos pending
3. Verificar todos los health endpoints

### Fase 2: Production Hardening (2-4 horas)
1. Añadir tests faltantes
2. Mejorar error handling
3. Añadir métricas Prometheus

### Fase 3: Auto-construcción (4-8 horas)
1. Implementar GapDetector
2. Mejorar ProposalEngine
3. Crear DirectorInterface
4. Añadir contratos de auto-construcción

### Fase 4: Validación (1 hora)
1. Tests completos pasan
2. Smoke test de auto-construcción
3. Documentar如何使用

---

## RESTRICCIONES DE SEGURIDAD

**NUNCA HACER (contratos L0):**
- ❌ No loguear secrets/tokens/passwords
- ❌ No ejecutar código sin aprobación humana (para auto-modificación)
- ❌ No modificar sistema de archivos fuera de /media/jotah/SSD_denis/
- ❌ No hacer `git push --force`
- ❌ No commit sin revisar diff

**SIEMPRE HACER:**
- ✅ Commit frecuentes con mensajes descriptivos
- ✅ Tests antes de considerar "hecho"
- ✅ Rollback plan antes de cualquier cambio risky
- ✅ Consultar al usuario antes de ejecutar propuestas de auto-construcción

---

## EJEMPLO DE INTERACCIÓN USUARIO-DENIS

```bash
# Usuario le dice a Denis:
> "Denis, quiero que Aprendas de mis documentos de trabajo"

# Denis responde:
He detectado que no tengo acceso a tus documentos de trabajo.
Propongo: [1] Indexar directorio ~/documentos [2] Crear RAG pipeline [3] ambas
¿Cuál prefieres? (responde 1, 2, o 3)

# Usuario:
> "Haz la 3"

# Denis:
Ejecutando en sandbox...
✅ Test pasaron
✅ Desplegando...
✅ Listo. Ahora puedo responder preguntas sobre tus documentos.
Guardando evolución en memoria...

# Usuario:
> "¿De qué trataban mis documentos?"

# Denis:
[Responde basándose en el contenido indexado]
```

---

## COMANDOS DE VERIFICACIÓN

```bash
# Después de cada fase, verificar:

# Fase 1
curl http://localhost:8084/health | jq '.status'
# Debe ser "healthy", no "degraded"

# Fase 2  
pytest tests/ -v
# Debe tener > 80% pass rate

# Fase 3
curl -X POST http://localhost:8085/director/describe
# Debe devolver capabilities actuales

curl -X POST http://localhost:8085/director/direct \
  -H "Content-Type: application/json" \
  -d '{"message": "¿Cuáles son tus capacidades?"}'
# Debe responder en lenguaje natural
```

---

## NOTAS PARA EL AGENTE

1. **Trabaja incrementalmente**: No intentes hacer todo de golpe
2. **Commits pequeños**: Cada cambio pequeño = un commit
3. **Consulta antes de actuar**: Para cambios grandes, pregunta al usuario
4. **Documenta**: Cada feature nueva = documentación actualizada
5. **Tests**: Si no hay test, no está "hecho"

---

*Este prompt debe resultar en un sistema production-ready con infraestructura de autoconstrucción. El usuario podrá entonces dirigir a Denis en lenguaje natural para que evolucione continuamente.*
