// =============================================================================
// DENIS GRAPH BOOTSTRAP - Complete Graph Seeds
// =============================================================================
// Run with: cypher-shell -u neo4j -p <pass> < seeds/graph_bootstrap.cypher
// Or: :source seeds/graph_bootstrap.cypher in Neo4j Browser
// =============================================================================

// ---------- Parameters ----------
// Set these before running:
// :param NODEMAC_IP => '100.64.1.10';
// :param NODE2_IP => '100.64.1.20';

// ---------- Constraints ----------
CREATE CONSTRAINT intent_name IF NOT EXISTS FOR (i:Intent) REQUIRE i.name IS UNIQUE;
CREATE CONSTRAINT tool_name IF NOT EXISTS FOR (t:Tool) REQUIRE t.name IS UNIQUE;
CREATE CONSTRAINT action_name IF NOT EXISTS FOR (a:Action) REQUIRE a.name IS UNIQUE;
CREATE CONSTRAINT engine_name IF NOT EXISTS FOR (e:Engine) REQUIRE e.name IS UNIQUE;
CREATE CONSTRAINT layer_code IF NOT EXISTS FOR (n:NeuroLayer) REQUIRE n.code IS UNIQUE;
CREATE CONSTRAINT node_name IF NOT EXISTS FOR (n:Node) REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT svc_name IF NOT EXISTS FOR (s:Service) REQUIRE s.name IS UNIQUE;

// ---------- Indexes ----------
CREATE INDEX turn_ts IF NOT EXISTS FOR (t:Turn) ON (t.ts);
CREATE INDEX episode_sid IF NOT EXISTS FOR (e:Episode) ON (e.session_id);
CREATE INDEX tool_type IF NOT EXISTS FOR (t:Tool) ON (t.type);
CREATE INDEX engine_status IF NOT EXISTS FOR (e:Engine) ON (e.status);

// =============================================================================
// 1. INFRA MULTINODE: NODES + SERVICES + ENGINES
// =============================================================================

// ---------- Nodes ----------
MERGE (n1:Node {name:'nodo1'})
SET n1.ip = '10.10.10.1',
    n1.hostname = 'Nodo1',
    n1.tailscale = true,
    n1.is_local = true;

MERGE (n2:Node {name:'nodo2'})
SET n2.ip = '100.64.1.20',
    n2.hostname = 'nodo2',
    n2.tailscale = true,
    n2.is_local = false;

MERGE (n3:Node {name:'nodomac'})
SET n3.ip = '100.64.1.10',
    n3.hostname = 'nodomac',
    n3.tailscale = true,
    n3.is_local = false;

// ---------- Services ----------
MERGE (s1:Service {name:'llm_local'})
SET s1.type = 'llm',
    s1.endpoint = 'http://127.0.0.1:9997',
    s1.description = 'Local LLM on nodo1';

MERGE (s2:Service {name:'coder_local'})
SET s2.type = 'llm',
    s2.endpoint = 'http://127.0.0.1:9998',
    s2.description = 'Local Coder LLM on nodo1';

MERGE (s3:Service {name:'llm_nodo2'})
SET s3.type = 'llm',
    s3.endpoint = 'http://100.64.1.20:8003',
    s3.description = 'Remote LLM on nodo2';

MERGE (s4:Service {name:'llm_nodomac'})
SET s4.type = 'llm',
    s4.endpoint = 'http://100.64.1.10:9997',
    s4.description = 'Remote LLM on nodomac';

// ---------- Host relations ----------
MERGE (n1)-[:HOSTS]->(s1);
MERGE (n1)-[:HOSTS]->(s2);
MERGE (n2)-[:HOSTS]->(s3);
MERGE (n3)-[:HOSTS]->(s4);

// ---------- Engines ----------
MERGE (e1:Engine {name:'qwen3b_local'})
SET e1.endpoint = 'http://127.0.0.1:9997',
    e1.status = 'active',
    e1.model = 'qwen2.5-3b-instruct',
    e1.node = 'nodo1';

MERGE (e2:Engine {name:'qwen_coder7b_local'})
SET e2.endpoint = 'http://127.0.0.1:9998',
    e2.status = 'active',
    e2.model = 'qwen2.5-coder-7b',
    e2.node = 'nodo1';

MERGE (e3:Engine {name:'qwen05b_node2'})
SET e3.endpoint = 'http://10.10.10.2:8003',
    e3.status = 'unknown',
    e3.model = 'qwen2.5-0.5b',
    e3.node = 'nodo2';

MERGE (e4:Engine {name:'smollm_node2'})
SET e4.endpoint = 'http://10.10.10.2:8006',
    e4.status = 'unknown',
    e4.model = 'smollm2-1.7b',
    e4.node = 'nodo2';

MERGE (e5:Engine {name:'gemma_node2'})
SET e5.endpoint = 'http://10.10.10.2:8007',
    e5.status = 'unknown',
    e5.model = 'gemma-3-1b',
    e5.node = 'nodo2';

MERGE (e6:Engine {name:'qwen15b_node2'})
SET e6.endpoint = 'http://10.10.10.2:8008',
    e6.status = 'unknown',
    e6.model = 'qwen2.5-1.5b',
    e6.node = 'nodo2';

MERGE (e7:Engine {name:'piper_tts'})
SET e7.endpoint = 'http://10.10.10.2:8005',
    e7.status = 'inactive',
    e7.model = 'piper-es',
    e7.node = 'nodo2';

MERGE (e8:Engine {name:'groq_booster'})
SET e8.endpoint = 'groq://api.groq.com/openai/v1',
    e8.status = 'unknown',
    e8.model = 'llama-3.1-8b-instant';

MERGE (e9:Engine {name:'openrouter_cloud'})
SET e9.endpoint = 'https://openrouter.ai/api/v1/chat/completions',
    e9.status = 'unknown',
    e9.model = 'gpt-4o-mini';

// ---------- Provide relations ----------
MERGE (s1)-[:PROVIDES]->(e1);
MERGE (s2)-[:PROVIDES]->(e2);

// =============================================================================
// 2. TOOLS + RISK LEVELS
// =============================================================================

// ---------- HIGH RISK ----------
MERGE (t1:Tool {name:'Reboot System'})
SET t1.type = 'system',
    t1.read_only = false,
    t1.risk_level = 'high',
    t1.requires_approval = true,
    t1.category = 'system';

MERGE (t2:Tool {name:'Deploy Code'})
SET t2.type = 'deployment',
    t2.read_only = false,
    t2.risk_level = 'high',
    t2.requires_approval = true,
    t2.category = 'deployment';

MERGE (t3:Tool {name:'Delete File'})
SET t3.type = 'filesystem',
    t3.read_only = false,
    t3.risk_level = 'high',
    t3.requires_approval = true,
    t3.category = 'filesystem';

// ---------- MEDIUM RISK ----------
MERGE (t4:Tool {name:'Execute SSH Command'})
SET t4.type = 'remote',
    t4.read_only = false,
    t4.risk_level = 'medium',
    t4.requires_approval = false,
    t4.category = 'remote';

MERGE (t5:Tool {name:'Restart Service'})
SET t5.type = 'system',
    t5.read_only = false,
    t5.risk_level = 'medium',
    t5.requires_approval = false,
    t5.category = 'system';

MERGE (t6:Tool {name:'Write File'})
SET t6.type = 'filesystem',
    t6.read_only = false,
    t6.risk_level = 'medium',
    t6.requires_approval = false,
    t6.category = 'filesystem';

MERGE (t7:Tool {name:'Edit File'})
SET t7.type = 'filesystem',
    t7.read_only = false,
    t7.risk_level = 'medium',
    t7.requires_approval = false,
    t7.category = 'filesystem';

MERGE (t8:Tool {name:'Git Commit'})
SET t8.type = 'version_control',
    t8.read_only = false,
    t8.risk_level = 'medium',
    t8.requires_approval = false,
    t8.category = 'version_control';

// ---------- SAFE / READ-ONLY ----------
MERGE (t9:Tool {name:'ha_query'})
SET t9.type = 'http_get',
    t9.read_only = true,
    t9.risk_level = 'safe',
    t9.requires_approval = false,
    t9.category = 'home_automation';

MERGE (t10:Tool {name:'ha_control'})
SET t10.type = 'http_post',
    t10.read_only = false,
    t10.risk_level = 'medium',
    t10.requires_approval = false,
    t10.category = 'home_automation';

MERGE (t11:Tool {name:'bash_execute'})
SET t11.type = 'local',
    t11.read_only = false,
    t11.risk_level = 'high',
    t11.requires_approval = true,
    t11.category = 'system';

MERGE (t12:Tool {name:'tts_synthesize'})
SET t12.type = 'http_post',
    t12.read_only = true,
    t12.risk_level = 'safe',
    t12.requires_approval = false,
    t12.category = 'voice';

MERGE (t13:Tool {name:'smx_response'})
SET t13.type = 'local',
    t13.read_only = true,
    t13.risk_level = 'safe',
    t13.requires_approval = false,
    t13.category = 'response';

MERGE (t14:Tool {name:'Read File'})
SET t14.type = 'filesystem',
    t14.read_only = true,
    t14.risk_level = 'safe',
    t14.requires_approval = false,
    t14.category = 'filesystem';

MERGE (t15:Tool {name:'code_search'})
SET t15.type = 'search',
    t15.read_only = true,
    t15.risk_level = 'safe',
    t15.requires_approval = false,
    t15.category = 'code';

// =============================================================================
// 3. INTENTS -> TOOLS (ACTIVATES)
// =============================================================================

// ---------- Intents ----------
MERGE (i1:Intent {name:'greeting'})
SET i1.description = 'Saludo o conversación social';

MERGE (i2:Intent {name:'smart_home'})
SET i2.description = 'Control domótico';

MERGE (i3:Intent {name:'run_tests_ci'})
SET i3.description = 'Ejecutar tests CI';

MERGE (i4:Intent {name:'ops_health_check'})
SET i4.description = 'Chequeo de salud del sistema';

MERGE (i5:Intent {name:'debug_repo'})
SET i5.description = 'Depurar errores en repositorio';

MERGE (i6:Intent {name:'implement_feature'})
SET i6.description = 'Implementar nueva funcionalidad';

// ---------- Direct activations ----------
MERGE (i1)-[:ACTIVATES {priority:1, confidence_min:0.5}]->(t13);
MERGE (i1)-[:ACTIVATES {priority:2, confidence_min:0.5}]->(t12);

MERGE (i2)-[:ACTIVATES {priority:1, confidence_min:0.5}]->(t10);
MERGE (i2)-[:ACTIVATES {priority:2, confidence_min:0.5}]->(t9);

MERGE (i3)-[:ACTIVATES {priority:1, confidence_min:0.8}]->(t11);
MERGE (i3)-[:ACTIVATES {priority:2, confidence_min:0.5}]->(t15);

MERGE (i4)-[:ACTIVATES {priority:1, confidence_min:0.5}]->(t9);
MERGE (i4)-[:ACTIVATES {priority:2, confidence_min:0.3}]->(t5);

MERGE (i5)-[:ACTIVATES {priority:1, confidence_min:0.5}]->(t15);
MERGE (i5)-[:ACTIVATES {priority:2, confidence_min:0.5}]->(t14);
MERGE (i5)-[:ACTIVATES {priority:3, confidence_min:0.7}]->(t11);

MERGE (i6)-[:ACTIVATES {priority:1, confidence_min:0.6}]->(t15);
MERGE (i6)-[:ACTIVATES {priority:2, confidence_min:0.5}]->(t14);
MERGE (i6)-[:ACTIVATES {priority:3, confidence_min:0.7}]->(t6);
MERGE (i6)-[:ACTIVATES {priority:4, confidence_min:0.8}]->(t7);

// =============================================================================
// 4. TOOLCHAINS (for complex intents)
// =============================================================================

// smart_home: perceive -> decide -> act
MERGE (step1:ToolchainStep {name:'smart_home_perceive'})
SET step1.order = 1,
    step1.tool_name = 'ha_query';

MERGE (step2:ToolchainStep {name:'smart_home_act'})
SET step2.order = 2,
    step2.tool_name = 'ha_control';

MERGE (i2)-[:HAS_CHAIN]->(step1);
MERGE (step1)-[:NEXT_STEP]->(step2);
MERGE (step1)-[:USES_TOOL]->(t9);
MERGE (step2)-[:USES_TOOL]->(t10);

// =============================================================================
// 5. NEUROLAYERS
// =============================================================================

MERGE (nl1:NeuroLayer {code:'SEMANTIC', name:'Semantic Memory'})
SET nl1.layer = 'semantic';

MERGE (nl2:NeuroLayer {code:'SENSOR', name:'Sensory Memory'})
SET nl2.layer = 'sensory';

MERGE (nl3:NeuroLayer {code:'EPISODIC', name:'Episodic Memory'})
SET nl3.layer = 'episodic';

MERGE (nl4:NeuroLayer {code:'PROCEDURAL', name:'Procedural Memory'})
SET nl4.layer = 'procedural';

// ---------- Process relations ----------
MERGE (nl1)-[:PROCESSES]->(i1);
MERGE (nl1)-[:PROCESSES]->(i2);
MERGE (nl1)-[:PROCESSES]->(i3);
MERGE (nl2)-[:PROCESSES]->(i2);

// =============================================================================
// 6. PREFERRED ENGINES
// =============================================================================

MERGE (i1)-[:PREFERS_ENGINE {reason:'fast_social'}]->(e1);
MERGE (i2)-[:PREFERS_ENGINE {reason:'fast_home'}]->(e1);
MERGE (i3)-[:PREFERS_ENGINE {reason:'code_execution'}]->(e2);
MERGE (i4)-[:PREFERS_ENGINE {reason:'read_only'}]->(e1);
MERGE (i5)-[:PREFERS_ENGINE {reason:'code_analysis'}]->(e2);
MERGE (i6)-[:PREFERS_ENGINE {reason:'code_generation'}]->(e2);

// =============================================================================
// SUMMARY
// =============================================================================

RETURN 'Graph bootstrap complete' as status;
