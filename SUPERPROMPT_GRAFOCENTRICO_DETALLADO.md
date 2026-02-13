# SUPERPROMPT DETALLADO: RECONSTRUCCIÓN DE DENIS DESDE EL GRAFOCENTRISMO

## Contexto: La Verdad del Grafo

Has hecho una auditoría profunda del grafo Neo4j de DENIS. Esta es la realidad:

### Estado Actual del Grafo:
- **10,689 nodos** con propiedades cuánticas (quantum augmentation ✅)
- **14,094 relaciones** pero **muchas rotas o faltantes**
- **~3,500+ nodos aislados** flotando sin conexiones

### Problemas Estructurales Encontrados:

| Problema | Impacto | Estado |
|----------|---------|--------|
| NeuroLayers sin relaciones entre sí | No hay procesamiento de memoria | CRÍTICO |
| MentalLoops sin relaciones | No hay orquestación | CRÍTICO |
| Flujo Cognición roto | No hay procesamiento de requests | CRÍTICO |
| VoiceComponents aislados | Voice pipeline no funciona | ALTO |
| LLMModels aislados | No hay selección dinámica | ALTO |
| Memory sin transiciones | No hay consolidación | ALTO |

---

# MISIÓN

Tu misión es recentrar el proyecto hacia:

1. **INMEDIATO**: Arreglar las conexiones del grafo para que todo funcione
2. **ESTRATÉGICO**: Preparar infraestructura para auto-construcción infinita

---

# PARTE 1: ARREGLO INMEDIATO (Producción)

## 1.1 Diagnóstico de Servicios

Primero verifica el estado actual:
```bash
# Estado de servicios
curl -s http://localhost:8084/health
curl -s http://localhost:8085/health  
curl -s http://localhost:8004/health

# Neo4j
python3 -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'Leon1234\$'))
with driver.session() as s:
    r = s.run('MATCH (n) RETURN count(n)').single()
    print(f'Nodos: {r[0]}')
driver.close()
"
```

## 1.2 Arreglar Pipecat (105 eventos fallidos)

El servicio en puerto 19025 está caído. Investiga:
```bash
# Ver logs
grep -i error /tmp/denis_server.log 2>/dev/null || echo "No hay logs"

# Ver si el proceso existe
ps aux | grep pipecat

# Ver puertos listening
netstat -tlnp | grep 19025
```

**Si está caído**, el fallback debería activarse automáticamente. Verifica que el código tiene fallback.

## 1.3 Feature Flags a Activar (Gradualmente)

En `api/fastapi_server.py` o configuración:

```python
# Primero solo estos:
DENIS_USE_INFERENCE_ROUTER=true  # Ya está
DENIS_USE_MEMORY_UNIFIED=true    # Ya está
DENIS_ENABLE_METAGRAPH=true      # Ya está

# Luego probar uno por uno:
# DENIS_USE_VOICE_PIPELINE=true
# DENIS_USE_SPRINT_ORCHESTRATOR=true  
# DENIS_USE_API_UNIFIED=true
```

## 1.4 Contratos a Activar

En `contracts/registry.yaml`, cambiar `pending` → `active`:
- L3.META.NEVER_BLOCK
- L3.META.SELF_REFLECTION_LATENCY
- L3.META.ONLY_OBSERVE_L0
- L3.META.HUMAN_APPROVAL_FOR_GROWTH
- L3.META.EVENT_SOURCING
- L3.META.QUALITY_GATE

---

# PARTE 2: RECONSTRUCCIÓN DEL GRAFOCENTRISMO

Esta es la parte crítica. Las queries Cypher que siguen deben ejecutarse para reconectar el sistema.

## 2.1 FLUJO DE COGNICIÓN (Más Crítico)

### Query 1: Conectar Turn → CognitiveTrace
```cypher
// Conectar Turn a CognitiveTrace por trace_id
MATCH (t:Turn)
MATCH (ct:CognitiveTrace)
WHERE t.trace_id = ct.trace_id
MERGE (t)-[:GENERATES_COGNITIVE_TRACE]->(ct)
RETURN count(*) as created
```

### Query 2: Conectar CognitiveTrace → ReasoningTrace
```cypher
MATCH (ct:CognitiveTrace)
MATCH (rt:ReasoningTrace)  
WHERE ct.trace_id = rt.trace_id
MERGE (ct)-[:PRODUCES_REASONING]->(rt)
RETURN count(*) as created
```

### Query 3: Conectar ReasoningTrace → GraphRoute
```cypher
MATCH (rt:ReasoningTrace)
MATCH (gr:GraphRoute)
WHERE rt.trace_id = gr.trace_id
MERGE (rt)-[:GENERATES_ROUTE]->(gr)
RETURN count(*) as created
```

### Query 4: Conectar GraphRoute → ToolExecution
```cypher
MATCH (gr:GraphRoute)
MATCH (te:ToolExecution)
WHERE gr.trace_id = te.trace_id
MERGE (gr)-[:TRIGGERS_EXECUTION]->(te)
RETURN count(*) as created
```

### Query 5: Verificar flujo completo
```cypher
MATCH path = (t:Turn)-[:GENERATES_COGNITIVE_TRACE]->(ct:CognitiveTrace)-[:PRODUCES_REASONING]->(rt:ReasoningTrace)-[:GENERATES_ROUTE]->(gr:GraphRoute)-[:TRIGGERS_EXECUTION]->(te:ToolExecution)
RETURN length(path) as path_length, count(*) as paths
```

## 2.2 NEURO LAYERS (Crítico)

### Query 6: Conectar capas de memoria
```cypher
// L1 -> L2
MATCH (l1:NeuroLayer {layer: 'sensory'})
MATCH (l2:NeuroLayer {layer: 'working'})
MERGE (l1)-[:PROMOTES_TO {threshold: 0.7, auto: true}]->(l2)

// L2 -> L3
MATCH (l2:NeuroLayer {layer: 'working'})
MATCH (l3:NeuroLayer {layer: 'episodic'})
MERGE (l2)-[:PROMOTES_TO {threshold: 0.8, auto: true}]->(l3)

// L3 -> L4
MATCH (l3:NeuroLayer {layer: 'episodic'})
MATCH (l4:NeuroLayer {layer: 'semantic'})
MERGE (l3)-[:CONSOLIDATES_TO {auto: true}]->(l4)

// L4 -> L5
MATCH (l4:NeuroLayer {layer: 'semantic'})
MATCH (l5:NeuroLayer {layer: 'procedural'})
MERGE (l4)-[:GENERALIZES_TO {auto: true}]->(l5)

// L5 -> L6
MATCH (l5:NeuroLayer {layer: 'procedural'})
MATCH (l6:NeuroLayer {layer: 'skills'})
MERGE (l5)-[:AUTOMATIZES_TO {auto: true}]->(l6)

// L6 -> L7
MATCH (l6:NeuroLayer {layer: 'skills'})
MATCH (l7:NeuroLayer {layer: 'emotional'})
MERGE (l6)-[:EMOTIONALIZES_TO {auto: true}]->(l7)

// L7 -> L8
MATCH (l7:NeuroLayer {layer: 'emotional'})
MATCH (l8:NeuroLayer {layer: 'social'})
MERGE (l7)-[:SOCIALIZES_TO {auto: true}]->(l8)

// L8 -> L9
MATCH (l8:NeuroLayer {layer: 'social'})
MATCH (l9:NeuroLayer {layer: 'identity'})
MERGE (l8)-[:IDENTIFIES_WITH {auto: true}]->(l9)

// L9 -> L10
MATCH (l9:NeuroLayer {layer: 'identity'})
MATCH (l10:NeuroLayer {layer: 'relational'})
MERGE (l9)-[:RELATES_TO {auto: true}]->(l10)

// L10 -> L11
MATCH (l10:NeuroLayer {layer: 'relational'})
MATCH (l11:NeuroLayer {layer: 'goals'})
MERGE (l10)-[:PURSUES_GOALS {auto: true}]->(l11)

// L11 -> L12
MATCH (l11:NeuroLayer {layer: 'goals'})
MATCH (l12:NeuroLayer {layer: 'metacog'})
MERGE (l11)-[:METACOGNIZES {auto: true}]->(l12)

RETURN 'Neuro layers connected' as status
```

### Query 7: Conectar CognitiveTrace a NeuroLayers (ya existe, verificar)
```cypher
MATCH (ct:CognitiveTrace)
MATCH (nl:NeuroLayer)
WHERE ct.active_layers_json CONTAINS nl.layer
MERGE (ct)-[:ACTIVATES_LAYER]->(nl)
RETURN count(*) as created
```

## 2.3 MENTAL LOOPS

### Query 8: Conectar MentalLoops entre sí
```cypher
// Perception -> Cognition
MATCH (p:MentalLoop {name: 'PerceptionLoop'})
MATCH (c:MentalLoop {name: 'CognitionLoop'})
MERGE (p)-[:NEXT_LOOP {auto: true}]->(c)

// Cognition -> Planning  
MATCH (c:MentalLoop {name: 'CognitionLoop'})
MATCH (pl:MentalLoop {name: 'PlanningLoop'})
MERGE (c)-[:NEXT_LOOP {auto: true}]->(pl)

// Planning -> Execution
MATCH (pl:MentalLoop {name: 'PlanningLoop'})
MATCH (e:MentalLoop {name: 'ExecutionLoop'})
MERGE (pl)-[:NEXT_LOOP {auto: true}]->(e)

RETURN 'Mental loops connected' as status
```

### Query 9: Conectar MentalLoops a MentalLoopLevels
```cypher
MATCH (ml:MentalLoop)
MATCH (mll:MentalLoopLevel)
WHERE toLower(ml.name) CONTAINS toLower(mll.name)
MERGE (ml)-[:USES_LEVEL]->(mll)
RETURN count(*) as created
```

### Query 10: Conectar CognitiveTrace a MentalLoopLevels (ya existe)
```cypher
MATCH (ct:CognitiveTrace)-[r:USED_LOOP_LEVEL]->(mll:MentalLoopLevel)
RETURN count(r) as connections
```

## 2.4 VOICE PIPELINE

### Query 11: Conectar VoiceComponents
```cypher
// STT -> TTS pipeline
MATCH (stt:VoiceComponent {name: 'whisper_stt'})
MATCH (tts:VoiceComponent {name: 'piper_tts'})
MERGE (stt)-[:PIPELINE_TO]->(tts)

// Pipecat control
MATCH (pc:VoiceComponent {name: 'pipecat'})
MATCH (stt:VoiceComponent {name: 'whisper_stt'})
MERGE (pc)-[:CONTROLS]->(stt)

MATCH (pc:VoiceComponent {name: 'pipecat'})
MATCH (tts:VoiceComponent {name: 'piper_tts'})
MERGE (pc)-[:CONTROLS]->(tts)

RETURN 'Voice pipeline connected' as status
```

### Query 12: Conectar Turn con audio a VoiceComponents
```cypher
MATCH (t:Turn)
MATCH (vc:VoiceComponent)
WHERE t.audio_data IS NOT NULL OR t.voice_input = true
MERGE (t)-[:PROCESSED_BY_VOICE]->(vc)
RETURN count(*) as created
```

## 2.5 INFERENCE

### Query 13: Conectar LLMModels a CognitiveTrace
```cypher
MATCH (ct:CognitiveTrace)
MATCH (lm:LLMModel)
WHERE ANY(x IN ct.models_json WHERE x = lm.key)
MERGE (ct)-[:USES_MODEL {key: lm.key}]->(lm)
RETURN count(*) as created
```

### Query 14: Conectar InferenceModel a LLMModel
```cypher
MATCH (im:InferenceModel)
MATCH (lm:LLMModel)
WHERE im.name = lm.name
MERGE (im)-[:BACKED_BY]->(lm)
RETURN count(*) as created
```

## 2.6 MEMORY

### Query 15: Conectar Episode a Memory
```cypher
MATCH (e:Episode)
MATCH (m:Memory)
WHERE e.session_id = m.session_id
MERGE (e)-[:GENERATES_MEMORY]->(m)
RETURN count(*) as created
```

### Query 16: Conectar MemoryLayers entre sí
```cypher
// Transiciones de tier
MATCH (l1:MemoryLayer {tier: 1})
MATCH (l2:MemoryLayer {tier: 2})
MERGE (l1)-[:PROMOTES_TO {threshold: 0.6}]->(l2)

MATCH (l2:MemoryLayer {tier: 2})
MATCH (l3:MemoryLayer {tier: 3})
MERGE (l2)-[:CONSOLIDATES_TO]->(l3)

MATCH (l3:MemoryLayer {tier: 3})
MATCH (l4:MemoryLayer {tier: 4})
MERGE (l3)-[:ARCHIVES_TO]->(l4)

RETURN 'Memory layers connected' as status
```

### Query 17: Conectar a AtlasCollection (largo plazo)
```cypher
MATCH (m:Memory)
MATCH (ac:AtlasCollection)
WHERE m.memory_type = 'episodic' AND ac.name = 'episodic_memory'
MERGE (m)-[:PERSISTS_TO]->(ac)
RETURN count(*) as created
```

## 2.7 SERVICIOS

### Query 18: Conectar Services a componentes
```cypher
// Service -> Node
MATCH (s:Service)
MATCH (n:Node)
WHERE s.node_id = n.name
MERGE (s)-[:RUNS_ON]->(n)

// Service -> LLMModel (si es servicio de inference)
MATCH (s:Service {type: 'ai'})
MATCH (lm:LLMModel)
WHERE s.name CONTAINS lm.node
MERGE (s)-[:USES_MODEL]->(lm)

RETURN 'Services connected' as status
```

---

# PARTE 3: CÓDIGO PARA AUTOMATIZAR

## 3.1 Script de Reconstrucción

Crea `scripts/reconstruct_graph.py`:

```python
#!/usr/bin/env python3
"""
Reconstruct Graph Connections - DENIS Unified V1

Este script reconecta los nodos del grafo que están aislados.
Ejecutar en orden:
1. primero las queries de flujo de cognición
2. luego neuro layers
3. luego mental loops
4. luego voice, inference, memory
"""
import sys
from neo4j import GraphDatabase

class GraphReconstructor:
    def __init__(self):
        self.uri = 'bolt://localhost:7687'
        self.user = 'neo4j'
        self.password = 'Leon1234$'  # ⚠️ cambiar en producción
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        
    def close(self):
        self.driver.close()
        
    def run_query(self, query, description):
        print(f"\n{'='*60}")
        print(f"EJECUTANDO: {description}")
        print(f"{'='*60}")
        try:
            with self.driver.session() as session:
                result = session.run(query)
                records = list(result)
                print(f"✓ Resultado: {len(records)} registros")
                for r in records:
                    print(f"  {dict(r)}")
                return records
        except Exception as e:
            print(f"✗ Error: {e}")
            return []
    
    def reconstruct_cognition_flow(self):
        """Fase 1: Reconectar flujo de cognición"""
        queries = [
            # Turn -> CognitiveTrace
            ("""
            MATCH (t:Turn)
            MATCH (ct:CognitiveTrace)
            WHERE t.trace_id = ct.trace_id
            MERGE (t)-[:GENERATES_COGNITIVE_TRACE]->(ct)
            RETURN count(*) as created
            """, "Turn -> CognitiveTrace"),
            
            # CognitiveTrace -> ReasoningTrace
            ("""
            MATCH (ct:CognitiveTrace)
            MATCH (rt:ReasoningTrace)  
            WHERE ct.trace_id = rt.trace_id
            MERGE (ct)-[:PRODUCES_REASONING]->(rt)
            RETURN count(*) as created
            """, "CognitiveTrace -> ReasoningTrace"),
            
            # ReasoningTrace -> GraphRoute
            ("""
            MATCH (rt:ReasoningTrace)
            MATCH (gr:GraphRoute)
            WHERE rt.trace_id = gr.trace_id
            MERGE (rt)-[:GENERATES_ROUTE]->(gr)
            RETURN count(*) as created
            """, "ReasoningTrace -> GraphRoute"),
            
            # GraphRoute -> ToolExecution
            ("""
            MATCH (gr:GraphRoute)
            MATCH (te:ToolExecution)
            WHERE gr.trace_id = te.trace_id
            MERGE (gr)-[:TRIGGERS_EXECUTION]->(te)
            RETURN count(*) as created
            """, "GraphRoute -> ToolExecution"),
        ]
        
        for query, desc in queries:
            self.run_query(query, desc)
    
    def reconstruct_neuro_layers(self):
        """Fase 2: Reconectar NeuroLayers"""
        layers = [
            ('sensory', 'working', 'PROMOTES_TO'),
            ('working', 'episodic', 'PROMOTES_TO'),
            ('episodic', 'semantic', 'CONSOLIDATES_TO'),
            ('semantic', 'procedural', 'GENERALIZES_TO'),
            ('procedural', 'skills', 'AUTOMATIZES_TO'),
            ('skills', 'emotional', 'EMOTIONALIZES_TO'),
            ('emotional', 'social', 'SOCIALIZES_TO'),
            ('social', 'identity', 'IDENTIFIES_WITH'),
            ('identity', 'relational', 'RELATES_TO'),
            ('relational', 'goals', 'PURSUES_GOALS'),
            ('goals', 'metacog', 'METACOGNIZES'),
        ]
        
        for from_layer, to_layer, rel_type in layers:
            query = f"""
            MATCH (l1:NeuroLayer {{layer: '{from_layer}'}})
            MATCH (l2:NeuroLayer {{layer: '{to_layer}'}})
            MERGE (l1)-[:{rel_type} {{threshold: 0.7, auto: true}}]->(l2)
            RETURN count(*) as created
            """
            self.run_query(query, f"NeuroLayer {from_layer} -> {to_layer}")
    
    def reconstruct_mental_loops(self):
        """Fase 3: Reconectar MentalLoops"""
        loops = [
            ('PerceptionLoop', 'CognitionLoop'),
            ('CognitionLoop', 'PlanningLoop'),
            ('PlanningLoop', 'ExecutionLoop'),
        ]
        
        for from_loop, to_loop in loops:
            query = f"""
            MATCH (ml1:MentalLoop {{name: '{from_loop}'}})
            MATCH (ml2:MentalLoop {{name: '{to_loop}'}})
            MERGE (ml1)-[:NEXT_LOOP {{auto: true}}]->(ml2)
            RETURN count(*) as created
            """
            self.run_query(query, f"MentalLoop {from_loop} -> {to_loop}")
    
    def reconstruct_voice(self):
        """Fase 4: Reconectar Voice"""
        queries = [
            ("""
            MATCH (stt:VoiceComponent {name: 'whisper_stt'})
            MATCH (tts:VoiceComponent {name: 'piper_tts'})
            MERGE (stt)-[:PIPELINE_TO]->(tts)
            RETURN count(*) as created
            """, "STT -> TTS"),
            
            ("""
            MATCH (pc:VoiceComponent {name: 'pipecat'})
            MATCH (stt:VoiceComponent {name: 'whisper_stt'})
            MERGE (pc)-[:CONTROLS]->(stt)
            RETURN count(*) as created
            """, "Pipecat -> STT"),
        ]
        
        for query, desc in queries:
            self.run_query(query, desc)
    
    def reconstruct_inference(self):
        """Fase 5: Reconectar Inference"""
        query = """
        MATCH (ct:CognitiveTrace)
        MATCH (lm:LLMModel)
        WHERE ANY(x IN ct.models_json WHERE x = lm.key)
        MERGE (ct)-[:USES_MODEL {key: lm.key}]->(lm)
        RETURN count(*) as created
        """
        self.run_query(query, "CognitiveTrace -> LLMModel")
    
    def reconstruct_memory(self):
        """Fase 6: Reconectar Memory"""
        # Episode -> Memory
        self.run_query("""
        MATCH (e:Episode)
        MATCH (m:Memory)
        WHERE e.session_id = m.session_id
        MERGE (e)-[:GENERATES_MEMORY]->(m)
        RETURN count(*) as created
        """, "Episode -> Memory")
        
        # MemoryLayers
        tiers = [(1, 2, 'PROMOTES_TO'), (2, 3, 'CONSOLIDATES_TO'), (3, 4, 'ARCHIVES_TO')]
        for from_tier, to_tier, rel in tiers:
            self.run_query(f"""
            MATCH (l1:MemoryLayer {{tier: {from_tier}}})
            MATCH (l2:MemoryLayer {{tier: {to_tier}}})
            MERGE (l1)-[:{rel} {{threshold: 0.6}}]->(l2)
            RETURN count(*) as created
            """, f"MemoryLayer Tier {from_tier} -> {to_tier}")
    
    def full_reconstruction(self):
        """Ejecutar todas las fases"""
        print("INICIANDO RECONSTRUCCIÓN COMPLETA DEL GRAFO")
        print("="*60)
        
        self.reconstruct_cognition_flow()
        self.reconstruct_neuro_layers()
        self.reconstruct_mental_loops()
        self.reconstruct_voice()
        self.reconstruct_inference()
        self.reconstruct_memory()
        
        print("\n" + "="*60)
        print("RECONSTRUCCIÓN COMPLETADA")
        print("="*60)

if __name__ == '__main__':
    reconstructor = GraphReconstructor()
    try:
        reconstructor.full_reconstruction()
    finally:
        reconstructor.close()
```

## 3.2 Cómo ejecutar

```bash
cd /media/jotah/SSD_denis/home_jotah/denis_unified_v1

# Hacer backup del grafo primero
cypher-shell -u neo4j -p "Leon1234\$" "CALL apoc.export.json.all('backup_pre_reconstruct.json', {})"

# Ejecutar reconstrucción
python3 scripts/reconstruct_graph.py

# Verificar mejoras
python3 -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'Leon1234\$'))
with driver.session() as s:
    # Contar relaciones nuevas
    r = s.run('''
        MATCH ()-[r:PRODUCES_REASONING]->() 
        RETURN count(r) as cnt
    ''').single()
    print(f'Relaciones PRODUCES_REASONING: {r[0]}')
driver.close()
"
```

---

# PARTE 4: PRUEBAS DE VERIFICACIÓN

## 4.1 Tests de smoke post-reconstrucción

```bash
# Test 1: Flujo de cognición
python3 -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'Leon1234\$'))
with driver.session() as s:
    # Contar paths completos
    r = s.run('''
        MATCH path = (t:Turn)-[:GENERATES_COGNITIVE_TRACE]->(ct:CognitiveTrace)-[:PRODUCES_REASONING]->(rt:ReasoningTrace)-[:GENERATES_ROUTE]->(gr:GraphRoute)-[:TRIGGERS_EXECUTION]->(te:ToolExecution)
        RETURN count(path) as paths
    ''').single()
    print(f'Paths de cognición completos: {r[0]}')
driver.close()
"

# Test 2: NeuroLayers conectadas
python3 -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'Leon1234\$'))
with driver.session() as s:
    r = s.run('''
        MATCH ()-[r:PROMOTES_TO|CONSOLIDATES_TO|GENERALIZES_TO]->() 
        RETURN count(r) as cnt
    ''').single()
    print(f'Relaciones de NeuroLayers: {r[0]}')
driver.close()
"

# Test 3: MentalLoops conectadas
python3 -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'Leon1234\$'))
with driver.session() as s:
    r = s.run('''
        MATCH ()-[r:NEXT_LOOP]->() 
        RETURN count(r) as cnt
    ''').single()
    print(f'Relaciones de MentalLoops: {r[0]}')
driver.close()
"
```

## 4.2 Criterios de éxito

| Métrica | Antes | Después (objetivo) |
|---------|-------|-------------------|
| Paths cognición completos | 0 | > 100 |
| NeuroLayer relaciones | 0 | > 10 |
| MentalLoop relaciones | 0 | > 3 |
| VoicePipeline relaciones | 0 | > 3 |
| Nodos aislados | ~3,500 | < 500 |

---

# PARTE 5: AUTO-CONSTRUCCIÓN (Visión)

Una vez reconstruido el grafo, implementar:

## 5.1 Gap Detector

```python
class GraphGapDetector:
    """Detecta gaps en el grafo."""
    
    def detect_orphans(self):
        """Nodos sin relaciones"""
        query = """
        MATCH (n)
        WHERE NOT (n)-->() AND NOT ()-->(n)
        RETURN labels(n)[0] as label, count(*) as cnt
        ORDER BY cnt DESC
        """
    
    def detect_missing_edges(self):
        """Relaciones que deberían existir pero no existen"""
        # NeuroLayers sin conexión
        # MentalLoops sin conexión
        # Flujo de cognición roto
    
    def detect_stale_data(self):
        """Datos sin actualizar en mucho tiempo"""
        query = """
        MATCH (n)
        WHERE n.last_augmented < datetime() - duration({days: 7})
        RETURN labels(n)[0] as label, count(*) as cnt
        """
```

## 5.2 Proposal from Graph

```python
class GraphProposalEngine:
    """Genera proposals desde gaps detectados."""
    
    def propose_edge_creation(self, from_node, to_node):
        """Propone crear una relación faltante."""
        proposal = {
            "type": "graph_edge_creation",
            "from": from_node,
            "to": to_node,
            "cypher": f"MATCH (a:{from_node}), MATCH (b:{to_node}) MERGE (a)-[:CONNECTED_TO]->(b)",
            "rationale": f"{from_node} debería conectar a {to_node} para mantener flujo",
            "risk": "low"
        }
        return proposal
```

## 5.3 Director Interface

```python
class DirectorInterface:
    """Interfaz de lenguaje natural para el usuario."""
    
    def process(self, message: str):
        """Procesa mensaje del usuario."""
        # "Denis, tus capas de memoria no están conectadas"
        # -> Detecta gap -> Propone solución -> Espera aprobación -> Ejecuta
```

---

# RESTRICCIONES

**NUNCA:**
- ❌ Borrar nodos existentes
- ❌ Modificar propiedades de nodos (solo crear relaciones)
- ❌ Ejecutar sin backup previo
- ❌ Cambiar passwords en código

**SIEMPRE:**
- ✅ Hacer backup antes de cada operación
- ✅ Verificar después de cada query
- ✅ Commit frecuente con mensajes descriptivos
- ✅ Tests después de cambios

---

# ORDEN DE EJECUCIÓN SUGERIDO

1. **Día 1 - Mañana**: Backup + Ejecutar reconstruct_graph.py
2. **Día 1 - Tarde**: Verificar mejoras + Tests
3. **Día 2 - Mañana**: Arreglar servicios (pipecat, feature flags)
4. **Día 2 - Tarde**: Activar contratos pending
5. **Día 3**: Implementar Gap Detector para auto-construcción

---

*Este documento es la guía definitiva para reconstruir DENIS desde el grafo. La verdad está en Neo4j - todo lo demás es secundaria.*
