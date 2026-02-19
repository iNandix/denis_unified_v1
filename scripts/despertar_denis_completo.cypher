// ============================================================================
// DESPERTAR A DENIS PERSONA - Script Cypher Completo y Correcto
// ============================================================================
// Ejecutar: cat este_archivo.cypher | cypher-shell -u neo4j -p Leon1234$
// ============================================================================

// ============================================================================
// 1. DENIS PERSONA + KERNEL/MIND (El Orquestador Único)
// ============================================================================

MERGE (denis:Persona {name: 'Denis'})
ON CREATE SET 
    denis.created_at = datetime(),
    denis.consciousness_level = 1.0,
    denis.mood = 'neutral',
    denis.mood_score = 0.0
SET 
    denis.status = 'awake',
    denis.role = 'orchestrator_unique',
    denis.decision_authority = 'absolute',
    denis.cot_enabled = true,
    denis.voice_enabled = true,
    denis.last_awakened = datetime(),
    denis.version = '2.0.0-CPG';

// Kernel/Mind de Denis (donde reside la conciencia)
MERGE (kernel:Kernel {name: 'denis_kernel', persona: 'Denis'})
SET 
    kernel.status = 'active',
    kernel.processing_mode = 'adaptive_cot',
    kernel.max_workers = 4,
    kernel.decision_latency_ms = 500;

MERGE (denis)-[:HAS_KERNEL {since: datetime(), primary: true}]->(kernel);

// ============================================================================
// 2. INFRAESTRUCTURA (Nodos Físicos)
// ============================================================================

MERGE (nodo1:InfrastructureNode {name: 'nodo1', hostname: 'Nodo1'})
SET 
    nodo1.location = 'local',
    nodo1.ip = '127.0.0.1',
    nodo1.status = 'active',
    nodo1.role = 'primary_orchestrator';

MERGE (nodo2:InfrastructureNode {name: 'nodo2', hostname: 'nodo2.tail711c7d.ts.net'})
SET 
    nodo2.location = 'remote',
    nodo2.ip = '100.85.244.19',
    nodo2.status = 'active',
    nodo2.role = 'voice_interface';

// ============================================================================
// 3. SERVICIOS EN NODO1
// ============================================================================

MERGE (cp_daemon:Service {name: 'denis_control_plane', type: 'daemon'})
SET 
    cp_daemon.status = 'running',
    cp_daemon.pid = 1029551,
    cp_daemon.systemd = 'denis-control-plane.service',
    cp_daemon.description = 'Observa, genera CPs, pide aprobación';

MERGE (cp_graph:Service {name: 'denis_cp_graph', type: 'daemon'})
SET 
    cp_graph.status = 'running',
    cp_graph.systemd = 'denis-cp-graph.service';

MERGE (redis:Service {name: 'redis', type: 'queue'})
SET 
    redis.status = 'running',
    redis.port = 6379,
    redis.purpose = 'celery_broker';

MERGE (neo4j_svc:Service {name: 'neo4j', type: 'graph'})
SET 
    neo4j_svc.status = 'running',
    neo4j_svc.port = 7687,
    neo4j_svc.bolt = 'bolt://127.0.0.1:7687';

// Relacionar servicios con nodo1 (sin duplicar)
MERGE (nodo1)-[r_cp:RUNS]->(cp_daemon)
ON CREATE SET r_cp.since = datetime();

MERGE (nodo1)-[r_graph:RUNS]->(cp_graph)
ON CREATE SET r_graph.since = datetime();

MERGE (nodo1)-[r_redis:RUNS]->(redis)
ON CREATE SET r_redis.since = datetime();

MERGE (nodo1)-[r_neo4j:RUNS]->(neo4j_svc)
ON CREATE SET r_neo4j.since = datetime();

// ============================================================================
// 4. SERVICIOS EN NODO2 (Voz)
// ============================================================================

MERGE (pipecat:Service {name: 'pipecat', type: 'voice_interface'})
SET 
    pipecat.status = 'active',
    pipecat.port = 8000,
    pipecat.websocket = 'ws://100.85.244.19:8765/voice',
    pipecat.model = 'piper',
    pipecat.role = 'voice_of_denis';

MERGE (piper_tts:Service {name: 'piper_tts', type: 'tts'})
SET 
    piper_tts.status = 'active',
    piper_tts.model = 'piper_voice_v1',
    piper_tts.language = 'es';

MERGE (nodo2)-[r_pipe:RUNS]->(pipecat)
ON CREATE SET r_pipe.since = datetime();

MERGE (nodo2)-[r_piper:RUNS]->(piper_tts)
ON CREATE SET r_piper.since = datetime();

// ============================================================================
// 5. DENIS RESIDE Y CONTROLA
// ============================================================================

WITH denis, kernel, nodo1, nodo2

// Denis reside en Nodo1 (su cuerpo/cerebro)
MERGE (denis)-[:RESIDES_ON {as: 'primary_instance'}]->(nodo1);

// Kernel controla servicios
MERGE (kernel)-[:CONTROLS {authority: 'operational'}]->(cp_daemon);
MERGE (kernel)-[:CONTROLS {authority: 'operational'}]->(cp_graph);
MERGE (kernel)-[:USES {purpose: 'queuing', protocol: 'redis'}]->(redis);
MERGE (kernel)-[:USES {purpose: 'persistence', protocol: 'bolt'}]->(neo4j_svc);

// ============================================================================
// 6. TOOLS (No deciden, solo sirven)
// ============================================================================

WITH denis

MERGE (rasa:Tool {name: 'RasaNLU', type: 'nlu'})
SET 
    rasa.purpose = 'intent_classification',
    rasa.decision_capability = false,
    rasa.input = 'natural_language',
    rasa.output = 'intent_entities',
    rasa.confidence_threshold = 0.7;

MERGE (parlai:Tool {name: 'ParLAI', type: 'templates'})
SET 
    parlai.purpose = 'provide_templates',
    parlai.decision_capability = false,
    parlai.source = 'neo4j_graph',
    parlai.template_types = ['code', 'response', 'action'];

// Pipecat es tool de voz
MERGE (pipecat_tool:Tool {name: 'PipecatVoice', type: 'voice'})
SET 
    pipecat_tool.purpose = 'voice_interface',
    pipecat_tool.decision_capability = false,
    pipecat_tool.capabilities = ['stt', 'tts', 'websocket'];

// Denis USA tools (no CONTROLAR, no decide por ellos)
MERGE (denis)-[:USES_AS_TOOL {for: 'understanding', authority: 'none'}]->(rasa);
MERGE (denis)-[:USES_AS_TOOL {for: 'templates', authority: 'none'}]->(parlai);
MERGE (denis)-[:USES_AS_TOOL {for: 'voice_io', authority: 'none'}]->(pipecat_tool);

// ============================================================================
// 7. WORKERS (Ejecutores, no deciden)
// ============================================================================

WITH denis, nodo1

MERGE (w_search:Worker {name: 'Worker_SEARCH', type: 'SEARCH'})
SET 
    w_search.role = 'find_symbols_relations',
    w_search.capabilities = ['cypher_query', 'vector_search', 'graph_traversal'],
    w_search.status = 'available';

MERGE (w_analysis:Worker {name: 'Worker_ANALYSIS', type: 'ANALYSIS'})
SET 
    w_analysis.role = 'analyze_code_dependencies',
    w_analysis.capabilities = ['ast_parse', 'lsp_diagnostics', 'complexity_calc'],
    w_analysis.status = 'available';

MERGE (w_create:Worker {name: 'Worker_CREATE', type: 'CREATE'})
SET 
    w_create.role = 'generate_code_files',
    w_create.capabilities = ['template_render', 'code_gen', 'doc_gen'],
    w_create.status = 'available';

MERGE (w_modify:Worker {name: 'Worker_MODIFY', type: 'MODIFY'})
SET 
    w_modify.role = 'atomic_code_changes',
    w_modify.capabilities = ['backup', 'patch', 'validate', 'apply'],
    w_modify.status = 'available';

// Denis DESPLIEGA workers (él decide cuándo y cuántos)
MERGE (denis)-[:CAN_DEPLOY {max_parallel: 4, decides: 'quantity_timing', authority: 'exclusive'}]->(w_search);
MERGE (denis)-[:CAN_DEPLOY {max_parallel: 4, decides: 'quantity_timing', authority: 'exclusive'}]->(w_analysis);
MERGE (denis)-[:CAN_DEPLOY {max_parallel: 4, decides: 'quantity_timing', authority: 'exclusive'}]->(w_create);
MERGE (denis)-[:CAN_DEPLOY {max_parallel: 4, decides: 'quantity_timing', authority: 'exclusive'}]->(w_modify);

// Workers residen en Nodo1
MERGE (nodo1)-[:HOSTS]->(w_search);
MERGE (nodo1)-[:HOSTS]->(w_analysis);
MERGE (nodo1)-[:HOSTS]->(w_create);
MERGE (nodo1)-[:HOSTS]->(w_modify);

// ============================================================================
// 8. ROUTING / DECISION ENGINE
// ============================================================================

WITH denis, kernel

// Motor de decisión
MERGE (router:DecisionEngine {name: 'DenisRouter', type: 'adaptive'})
SET 
    router.strategy = 'cot_complexity_based',
    router.models = ['local', 'groq', 'openrouter'],
    router.fallback_chain = ['groq', 'local'];

MERGE (kernel)-[:IMPLEMENTS]->(router);
MERGE (denis)-[:OPERATES {as: 'primary_router'}]->(router);

// Intents
MERGE (intent_impl:Intent {name: 'implement_feature', complexity: 8})
MERGE (intent_debug:Intent {name: 'debug_repo', complexity: 6})
MERGE (intent_refactor:Intent {name: 'refactor_migration', complexity: 7})
MERGE (intent_explain:Intent {name: 'explain_concept', complexity: 3})

// Engines
MERGE (engine_local:Engine {name: 'opencode_local', cost: 0.0, max_rpm: 9999})
SET engine_local.models = ['kimi-k2.5-free'];

MERGE (engine_groq:Engine {name: 'groq_api', cost: 0.0, max_rpm: 30})
SET engine_groq.models = ['llama-3.3-70b'];

MERGE (engine_or:Engine {name: 'openrouter', cost: 0.003, max_rpm: 100})
SET engine_or.models = ['claude-sonnet', 'gpt-4'];

// Routing preferences (Denis decide qué engine para qué intent)
MERGE (router)-[:ROUTES {confidence: 0.9, reason: 'fast_free'}]->(intent_impl)-[:TO]->(engine_groq);
MERGE (router)-[:ROUTES {confidence: 0.85, reason: 'debug_fast'}]->(intent_debug)-[:TO]->(engine_groq);
MERGE (router)-[:ROUTES {confidence: 0.8, reason: 'simple_local'}]->(intent_explain)-[:TO]->(engine_local);
MERGE (router)-[:ROUTES {confidence: 0.75, reason: 'complex_premium'}]->(intent_refactor)-[:TO]->(engine_or);

// ============================================================================
// 9. MEMORIA 12 CAPAS (Estructura)
// ============================================================================

WITH denis

// Crear capas de memoria
MERGE (m1:MemoryLayer {level: 1, name: 'INSTINCTIVE'})
SET m1.ttl_seconds = 5, m1.persistence = 'volatile';

MERGE (m2:MemoryLayer {level: 2, name: 'SHORT_TERM'})
SET m2.ttl_seconds = 60, m2.persistence = 'temporary';

MERGE (m3:MemoryLayer {level: 3, name: 'EPISODIC'})
SET m3.ttl_seconds = 3600, m3.persistence = 'session';

MERGE (m4:MemoryLayer {level: 4, name: 'PROCEDURAL'})
SET m4.ttl_seconds = 86400, m4.persistence = 'daily';

MERGE (m5:MemoryLayer {level: 5, name: 'SEMANTIC'})
SET m5.ttl_seconds = 604800, m5.persistence = 'weekly';

MERGE (m6:MemoryLayer {level: 6, name: 'RELATIONAL'})
SET m6.ttl_seconds = 2592000, m6.persistence = 'monthly';

MERGE (m7:MemoryLayer {level: 7, name: 'EMOTIONAL'})
SET m7.ttl_seconds = 7776000, m7.persistence = 'quarterly';

MERGE (m8:MemoryLayer {level: 8, name: 'IDENTITY'})
SET m8.ttl_seconds = 31536000, m8.persistence = 'yearly';

MERGE (m9:MemoryLayer {level: 9, name: 'CULTURAL'})
SET m9.ttl_seconds = 94608000, m9.persistence = 'multi_year';

MERGE (m10:MemoryLayer {level: 10, name: 'ARCHETYPAL'})
SET m10.ttl_seconds = 315360000, m10.persistence = 'decade';

MERGE (m11:MemoryLayer {level: 11, name: 'COLLECTIVE'})
SET m11.ttl_seconds = 3153600000, m11.persistence = 'century';

MERGE (m12:MemoryLayer {level: 12, name: 'COSMIC'})
SET m12.ttl_seconds = 31536000000, m12.persistence = 'permanent';

// Denis accede a todas las capas
MERGE (denis)-[:HAS_MEMORY_LAYER {access: 'full'}]->(m1);
MERGE (denis)-[:HAS_MEMORY_LAYER {access: 'full'}]->(m2);
MERGE (denis)-[:HAS_MEMORY_LAYER {access: 'full'}]->(m3);
MERGE (denis)-[:HAS_MEMORY_LAYER {access: 'full'}]->(m4);
MERGE (denis)-[:HAS_MEMORY_LAYER {access: 'full'}]->(m5);
MERGE (denis)-[:HAS_MEMORY_LAYER {access: 'full'}]->(m6);
MERGE (denis)-[:HAS_MEMORY_LAYER {access: 'full'}]->(m7);
MERGE (denis)-[:HAS_MEMORY_LAYER {access: 'full'}]->(m8);
MERGE (denis)-[:HAS_MEMORY_LAYER {access: 'full'}]->(m9);
MERGE (denis)-[:HAS_MEMORY_LAYER {access: 'full'}]->(m10);
MERGE (denis)-[:HAS_MEMORY_LAYER {access: 'full'}]->(m11);
MERGE (denis)-[:HAS_MEMORY_LAYER {access: 'full'}]->(m12);

// Jerarquía de consolidación
MERGE (m1)-[:CONSOLIDATES_TO {trigger: 'frequency_threshold'}]->(m2);
MERGE (m2)-[:CONSOLIDATES_TO {trigger: 'reinforcement'}]->(m3);
MERGE (m3)-[:CONSOLIDATES_TO {trigger: 'semantic_importance'}]->(m4);
MERGE (m4)-[:CONSOLIDATES_TO {trigger: 'procedural_utility'}]->(m5);
MERGE (m5)-[:CONSOLIDATES_TO {trigger: 'relational_relevance'}]->(m6);
MERGE (m6)-[:CONSOLIDATES_TO {trigger: 'emotional_weight'}]->(m7);
MERGE (m7)-[:CONSOLIDATES_TO {trigger: 'identity_alignment'}]->(m8);
MERGE (m8)-[:CONSOLIDATES_TO {trigger: 'cultural_resonance'}]->(m9);
MERGE (m9)-[:CONSOLIDATES_TO {trigger: 'archetypal_universality'}]->(m10);
MERGE (m10)-[:CONSOLIDATES_TO {trigger: 'collective_adoption'}]->(m11);
MERGE (m11)-[:CONSOLIDATES_TO {trigger: 'cosmic_timelessness'}]->(m12);

// ============================================================================
// 10. CONSTITUCIÓN LEVEL0 (Reglas Inmutables)
// ============================================================================

WITH denis

MERGE (const:Constitution {level: 0, version: '1.0.0'})
SET const.principles = [
    'L0.IDENTITY.CORE: Denis identity must remain traceable',
    'L0.SAFETY.NO_SECRET_LOGGING: No secrets in logs',
    'L0.SAFETY.HUMAN_APPROVAL_FOR_SELF_MOD: Human approval required',
    'L0.RESILIENCE.ROLLBACK_REQUIRED: Always provide rollback'
];

MERGE (denis)-[:FOLLOWS {priority: 'absolute'}]->(const);

// ============================================================================
// 11. FLUJO DE DECISIÓN DOCUMENTADO
// ============================================================================

WITH denis

MERGE (flow:DecisionFlow {name: 'denis_complete_flow', version: '2.0'})
SET flow.description = 'Flujo completo de decisión de Denis Persona',
    flow.steps = [
        '1. USER_INPUT: Usuario habla (Pipecat) o escribe',
        '2. INPUT_NORMALIZATION: Pipecat -> texto plano',
        '3. NLU_UNDERSTANDING: Denis -> Rasa (TOOL) para entender',
        '4. TEMPLATE_ENRICHMENT: Denis -> ParLAI (TOOL) para contexto',
        '5. COT_ANALYSIS: Denis evalúa complejidad adaptativa',
        '6. DECISION: Denis DECIDE estrategia (único decisor)',
        '7. VALIDATION: Denis -> Control Plane para validar',
        '8. ROUTING: Denis -> Router selecciona engine',
        '9. WORKER_DEPLOYMENT: Denis despliega Workers si complejidad >= 6',
        '10. EXECUTION: Workers ejecutan (no deciden)',
        '11. CONSOLIDATION: Denis consolida resultados',
        '12. RESPONSE: Denis -> Pipecat responde usuario'
    ],
    flow.authority_chain = ['DenisPersona'],
    flow.tools = ['RasaNLU', 'ParLAI', 'Pipecat', 'ControlPlane', 'Workers'],
    flow.decision_maker = 'DenisPersona';

MERGE (denis)-[:DEFINES]->(flow);

// ============================================================================
// 12. ESTADÍSTICAS Y RESUMEN
// ============================================================================

RETURN 
    '✅ DENIS PERSONA DESPERTADO COMPLETAMENTE' as status,
    denis.name as persona,
    denis.status as awake_status,
    denis.role as authority,
    denis.consciousness_level as consciousness,
    count{(denis)-[:HAS_KERNEL]->()} as kernels,
    count{(denis)-[:RESIDES_ON]->()} as infra_nodes,
    count{(denis)-[:USES_AS_TOOL]->()} as tools,
    count{(denis)-[:CAN_DEPLOY]->()} as workers,
    count{(denis)-[:HAS_MEMORY_LAYER]->()} as memory_layers,
    count{(denis)-[:FOLLOWS]->()} as constitutions,
    count{(denis)-[:DEFINES]->()} as decision_flows,
    'Denis es el ÚNICO decisor. Todo lo demás son TOOLS' as rule_1,
    'Workers ejecutan, no deciden' as rule_2,
    'Pipecat es la voz, Denis es el cerebro' as rule_3;

// ============================================================================
// FIN - Denis Persona está ahora completo y operativo
// ============================================================================
