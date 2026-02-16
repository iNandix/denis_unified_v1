// =============================================================================
// DENIS GRAPH BOOTSTRAP - Complete Graph Seeds (Normalized Model)
// =============================================================================
// Model: Node -> Interface -> Service -> Engine
// - Node: physical host (nodo1, nodo2, nodomac)
// - Interface: network interface (lan, dedicated, tailscale)
// - Service: process/daemon (llama.cpp, openrouter, groq)
// - Engine: inference endpoint
// =============================================================================

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
// 1. NODES (physical hosts)
// =============================================================================

MERGE (n1:Node {name:'nodo1'})
SET n1.ip = '10.10.10.1',
    n1.hostname = 'Nodo1',
    n1.is_host = true,
    n1.is_local = true;

MERGE (n2:Node {name:'nodo2'})
SET n2.ip = '10.10.10.2',
    n2.hostname = 'nodo2',
    n2.is_host = true,
    n2.is_local = false;

// =============================================================================
// 2. INTERFACES (network interfaces per node)
// =============================================================================

// nodo1 interfaces
MERGE (i1:Interface {name:'nodo1_lan'})
SET i1.ip = '192.168.1.34', i1.cidr = '192.168.1.0/24', i1.kind = 'lan';

MERGE (i2:Interface {name:'nodo1_dedicated'})
SET i2.ip = '10.10.10.1', i2.cidr = '10.10.10.0/24', i2.kind = 'dedicated';

MERGE (i3:Interface {name:'nodo1_tailscale'})
SET i3.ip = '100.64.1.10', i3.cidr = '100.64.0.0/10', i3.kind = 'tailscale';

// nodo2 interfaces
MERGE (i4:Interface {name:'nodo2_dedicated'})
SET i4.ip = '10.10.10.2', i4.cidr = '10.10.10.0/24', i4.kind = 'dedicated';

MERGE (i5:Interface {name:'nodo2_tailscale'})
SET i5.ip = '100.64.1.20', i5.cidr = '100.64.0.0/10', i5.kind = 'tailscale';

// Link interfaces to nodes
MERGE (n1)-[:HAS_IFACE]->(i1);
MERGE (n1)-[:HAS_IFACE]->(i2);
MERGE (n1)-[:HAS_IFACE]->(i3);
MERGE (n2)-[:HAS_IFACE]->(i4);
MERGE (n2)-[:HAS_IFACE]->(i5);

// =============================================================================
// 3. SERVICES (processes/daemons)
// =============================================================================

// Local services on nodo1 (listen on dedicated)
MERGE (s1:Service {name:'llm_local'})
SET s1.type = 'llm', s1.endpoint = 'http://10.10.10.1:9997';

MERGE (s2:Service {name:'coder_local'})
SET s2.type = 'llm', s2.endpoint = 'http://10.10.10.1:9998';

// Remote services on nodo2 (listen on dedicated)
MERGE (s3:Service {name:'llm_nodo2_8003'})
SET s3.type = 'llm', s3.endpoint = 'http://10.10.10.2:8003';

MERGE (s4:Service {name:'llm_nodo2_8005'})
SET s4.type = 'llm', s3.endpoint = 'http://10.10.10.2:8005';

MERGE (s5:Service {name:'llm_nodo2_8006'})
SET s5.type = 'llm', s5.endpoint = 'http://10.10.10.2:8006';

MERGE (s6:Service {name:'llm_nodo2_8007'})
SET s6.type = 'llm', s6.endpoint = 'http://10.10.10.2:8007';

MERGE (s7:Service {name:'llm_nodo2_8008'})
SET s7.type = 'llm', s7.endpoint = 'http://10.10.10.2:8008';

// Cloud services
MERGE (s8:Service {name:'openrouter'})
SET s8.type = 'cloud', s8.endpoint = 'https://openrouter.ai/api/v1/chat/completions';

MERGE (s9:Service {name:'groq'})
SET s9.type = 'cloud', s9.endpoint = 'groq://api.groq.com/openai/v1';

// IoT services (Home Assistant - LAN only)
MERGE (s10:Service {name:'home_assistant'})
SET s10.type = 'iot', s10.endpoint = 'http://192.168.1.10:8123';

// =============================================================================
// 4. HOSTS relationships (Node -> Service)
// =============================================================================

MERGE (n1)-[:HOSTS]->(s1);
MERGE (n1)-[:HOSTS]->(s2);
MERGE (n2)-[:HOSTS]->(s3);
MERGE (n2)-[:HOSTS]->(s4);
MERGE (n2)-[:HOSTS]->(s5);
MERGE (n2)-[:HOSTS]->(s6);
MERGE (n2)-[:HOSTS]->(s7);

// =============================================================================
// 5. LISTENS_ON relationships (Service -> Interface)
// =============================================================================

// Local services listen on dedicated
MERGE (s1)-[:LISTENS_ON]->(i2);
MERGE (s2)-[:LISTENS_ON]->(i2);

// nodo2 services listen on dedicated
MERGE (s3)-[:LISTENS_ON]->(i4);
MERGE (s4)-[:LISTENS_ON]->(i4);
MERGE (s5)-[:LISTENS_ON]->(i4);
MERGE (s6)-[:LISTENS_ON]->(i4);
MERGE (s7)-[:LISTENS_ON]->(i4);

// HA listens on LAN
MERGE (s10)-[:LISTENS_ON]->(i1);

// =============================================================================
// 6. ENGINES (inference endpoints)
// =============================================================================

// Local engines
MERGE (e1:Engine {name:'qwen3b_local'})
SET e1.endpoint = 'http://10.10.10.1:9997', e1.status = 'active', e1.model = 'qwen2.5-3b-instruct';

MERGE (e2:Engine {name:'qwen_coder7b_local'})
SET e2.endpoint = 'http://10.10.10.1:9998', e2.status = 'active', e2.model = 'qwen2.5-coder-7b';

// Remote engines
MERGE (e3:Engine {name:'qwen05b_node2'})
SET e3.endpoint = 'http://10.10.10.2:8003', e3.status = 'unknown', e3.model = 'qwen2.5-0.5b';

MERGE (e4:Engine {name:'smollm_node2'})
SET e4.endpoint = 'http://10.10.10.2:8006', e4.status = 'unknown', e4.model = 'smollm2-1.7b';

MERGE (e5:Engine {name:'gemma_node2'})
SET e5.endpoint = 'http://10.10.10.2:8007', e5.status = 'unknown', e5.model = 'gemma-3-1b';

MERGE (e6:Engine {name:'qwen15b_node2'})
SET e6.endpoint = 'http://10.10.10.2:8008', e6.status = 'unknown', e6.model = 'qwen2.5-1.5b';

MERGE (e7:Engine {name:'piper_tts'})
SET e7.endpoint = 'http://10.10.10.2:8005', e7.status = 'inactive', e7.model = 'piper-es';

// Cloud engines
MERGE (e8:Engine {name:'openrouter_cloud'})
SET e8.endpoint = 'https://openrouter.ai/api/v1/chat/completions', e8.status = 'unknown', e8.model = 'gpt-4o-mini';

MERGE (e9:Engine {name:'groq_booster'})
SET e9.endpoint = 'groq://api.groq.com/openai/v1', e9.status = 'unknown', e9.model = 'llama-3.1-8b-instant';

// =============================================================================
// 7. PROVIDES relationships (Service -> Engine)
// =============================================================================

MERGE (s1)-[:PROVIDES]->(e1);
MERGE (s2)-[:PROVIDES]->(e2);
MERGE (s3)-[:PROVIDES]->(e3);
MERGE (s4)-[:PROVIDES]->(e7);
MERGE (s5)-[:PROVIDES]->(e4);
MERGE (s6)-[:PROVIDES]->(e5);
MERGE (s7)-[:PROVIDES]->(e6);
MERGE (s8)-[:PROVIDES]->(e8);
MERGE (s9)-[:PROVIDES]->(e9);

// =============================================================================
// 8. TOOLS + RISK LEVELS
// =============================================================================

MERGE (t1:Tool {name:'Reboot System'})
SET t1.risk_level = 'high', t1.requires_approval = true;

MERGE (t2:Tool {name:'Deploy Code'})
SET t2.risk_level = 'high', t2.requires_approval = true;

MERGE (t3:Tool {name:'bash_execute'})
SET t3.risk_level = 'high', t3.requires_approval = true;

MERGE (t4:Tool {name:'Write File'})
SET t4.risk_level = 'medium';

MERGE (t5:Tool {name:'Edit File'})
SET t5.risk_level = 'medium';

MERGE (t6:Tool {name:'ha_control'})
SET t6.risk_level = 'medium';

MERGE (t7:Tool {name:'ha_query'})
SET t7.risk_level = 'safe';

MERGE (t8:Tool {name:'smx_response'})
SET t8.risk_level = 'safe';

MERGE (t9:Tool {name:'tts_synthesize'})
SET t9.risk_level = 'safe';

// =============================================================================
// 9. INTENTS -> TOOLS
// =============================================================================

MERGE (i1:Intent {name:'greeting'})
SET i1.description = 'Saludo';
MERGE (i2:Intent {name:'smart_home'})
SET i2.description = 'Domótica';
MERGE (i3:Intent {name:'run_tests_ci'})
SET i3.description = 'Tests CI';
MERGE (i4:Intent {name:'ops_health_check'})
SET i4.description = 'Health check';

MERGE (i1)-[:ACTIVATES {priority:1}]->(t8);
MERGE (i1)-[:ACTIVATES {priority:2}]->(t9);
MERGE (i2)-[:ACTIVATES {priority:1}]->(t6);
MERGE (i2)-[:ACTIVATES {priority:2}]->(t7);
MERGE (i3)-[:ACTIVATES {priority:1}]->(t3);
MERGE (i4)-[:ACTIVATES {priority:1}]->(t7);

// =============================================================================
// 10. PREFERRED ENGINES
// =============================================================================

MERGE (i1)-[:PREFERS_ENGINE]->(e1);
MERGE (i2)-[:PREFERS_ENGINE]->(e1);
MERGE (i3)-[:PREFERS_ENGINE]->(e2);
MERGE (i4)-[:PREFERS_ENGINE]->(e1);

// =============================================================================
// SUMMARY
// =============================================================================

RETURN 'Graph bootstrap complete - Network Model' as status;
