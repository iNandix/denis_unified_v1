// =============================================================================
// DENIS GRAPH SEEDS - Graph-Centric Infrastructure
// =============================================================================
// This script creates the baseline graph topology for Denis graph-centric mode.
// Run with: cypher-shell -u neo4j -p <password> < seeds.graph.cypher
// =============================================================================

// -----------------------------------------------------------------------------
// NODES - Physical/VM nodes in the network
// -----------------------------------------------------------------------------

// nodo1 = this machine (local)
MERGE (n1:Node {name: 'nodo1'})
SET n1.ip = '10.10.10.1',
    n1.hostname = 'Nodo1',
    n1.tailscale = true,
    n1.is_local = true,
    n1.last_seen = datetime();

// nodo2 = remote node
MERGE (n2:Node {name: 'nodo2'})
SET n2.ip = '100.64.1.20',
    n2.hostname = 'nodo2',
    n2.tailscale = true,
    n2.is_local = false,
    n2.last_seen = datetime();

// nodomac = macOS node
MERGE (n3:Node {name: 'nodomac'})
SET n3.ip = '100.64.1.10',
    n3.hostname = 'nodomac',
    n3.tailscale = true,
    n3.is_local = false,
    n3.last_seen = datetime();

// -----------------------------------------------------------------------------
// SERVICES - Service endpoints on nodes
// -----------------------------------------------------------------------------

// Local LLM services on nodo1
MERGE (s1:Service {name: 'llm_local'})
SET s1.type = 'llm',
    s1.endpoint = 'http://127.0.0.1:9997',
    s1.description = 'Local LLM (qwen2.5-3b)';

MERGE (s2:Service {name: 'coder_local'})
SET s2.type = 'llm',
    s2.endpoint = 'http://127.0.0.1:9998',
    s2.description = 'Local Coder LLM (qwen2.5-coder-7b)';

// Remote LLM services on nodo2
MERGE (s3:Service {name: 'llm_nodo2'})
SET s3.type = 'llm',
    s3.endpoint = 'http://100.64.1.20:8003',
    s3.description = 'Remote LLM on nodo2';

// nodomac services
MERGE (s4:Service {name: 'llm_nodomac'})
SET s4.type = 'llm',
    s4.endpoint = 'http://100.64.1.10:9997',
    s4.description = 'Remote LLM on nodomac';

// -----------------------------------------------------------------------------
// HOSTS relationships
// -----------------------------------------------------------------------------

MATCH (n1:Node {name: 'nodo1'}), (s1:Service {name: 'llm_local'})
MERGE (n1)-[:HOSTS]->(s1);

MATCH (n1:Node {name: 'nodo1'}), (s2:Service {name: 'coder_local'})
MERGE (n1)-[:HOSTS]->(s2);

MATCH (n2:Node {name: 'nodo2'}), (s3:Service {name: 'llm_nodo2'})
MERGE (n2)-[:HOSTS]->(s3);

MATCH (n3:Node {name: 'nodomac'}), (s4:Service {name: 'llm_nodomac'})
MERGE (n3)-[:HOSTS]->(s4);

// -----------------------------------------------------------------------------
// ENGINE STATUS - Update from 'unknown' to realistic defaults
// -----------------------------------------------------------------------------

// Local engines (active)
MATCH (e:Engine {name: 'qwen3b_local'})
SET e.status = 'active',
    e.node = 'nodo1';

MATCH (e:Engine {name: 'qwen_coder7b_local'})
SET e.status = 'active',
    e.node = 'nodo1';

// Remote engines on nodo2 (unknown - need healthcheck)
MATCH (e:Engine {name: 'qwen05b_node2'})
SET e.status = 'unknown',
    e.node = 'nodo2',
    e.endpoint = 'http://10.10.10.2:8003';

MATCH (e:Engine {name: 'smollm_node2'})
SET e.status = 'unknown',
    e.node = 'nodo2',
    e.endpoint = 'http://10.10.10.2:8006';

MATCH (e:Engine {name: 'gemma_node2'})
SET e.status = 'unknown',
    e.node = 'nodo2',
    e.endpoint = 'http://10.10.10.2:8007';

MATCH (e:Engine {name: 'qwen15b_node2'})
SET e.status = 'unknown',
    e.node = 'nodo2',
    e.endpoint = 'http://10.10.10.2:8008';

// Cloud/external engines
MATCH (e:Engine {name: 'piper_tts'})
SET e.status = 'inactive',
    e.node = 'nodo2';

MATCH (e:Engine {name: 'groq_booster'})
SET e.status = 'unknown';

// Connect engines to services
MATCH (s1:Service {name: 'llm_local'}), (e:Engine {name: 'qwen3b_local'})
MERGE (s1)-[:PROVIDES]->(e);

MATCH (s2:Service {name: 'coder_local'}), (e:Engine {name: 'qwen_coder7b_local'})
MERGE (s2)-[:PROVIDES]->(e);

// -----------------------------------------------------------------------------
// TOOL RISK LEVELS - Security classification
// -----------------------------------------------------------------------------

// HIGH RISK - Always require human approval
MATCH (t:Tool {name: 'Reboot System'})
SET t.risk_level = 'high',
    t.requires_approval = true;

MATCH (t:Tool {name: 'Deploy Code'})
SET t.risk_level = 'high',
    t.requires_approval = true;

MATCH (t:Tool {name: 'Delete File'})
SET t.risk_level = 'high',
    t.requires_approval = true;

// MEDIUM RISK - Require approval on low confidence
MATCH (t:Tool {name: 'Execute SSH Command'})
SET t.risk_level = 'medium';

MATCH (t:Tool {name: 'Restart Service'})
SET t.risk_level = 'medium';

MATCH (t:Tool {name: 'Write File'})
SET t.risk_level = 'medium';

MATCH (t:Tool {name: 'Edit File'})
SET t.risk_level = 'medium';

MATCH (t:Tool {name: 'Git Commit'})
SET t.risk_level = 'medium';

// SAFE - No approval needed
MATCH (t:Tool)
WHERE t.name IN ['smx_response', 'smx_fast_path', 'Read File', 'grep_search', 
                'code_search', 'List UPnP Ports', 'Check Network Port', 'Tailscale Status']
SET t.risk_level = 'safe';

// -----------------------------------------------------------------------------
// INTENT -> TOOL RELATIONSHIPS (already exist, just verify)
// -----------------------------------------------------------------------------

// greeting intent
MATCH (i:Intent {name: 'greeting'}), (t:Tool {name: 'smx_response'})
MERGE (i)-[:ACTIVATES {priority: 1, confidence_min: 0.5}]->(t);

// smart_home intent
MATCH (i:Intent {name: 'smart_home'}), (t:Tool {name: 'ha_control'})
MERGE (i)-[:ACTIVATES {priority: 1, confidence_min: 0.5}]->(t);

// run_tests_ci intent
MATCH (i:Intent {name: 'run_tests_ci'}), (t:Tool {name: 'bash_execute'})
MERGE (i)-[:ACTIVATES {priority: 1, confidence_min: 0.5}]->(t);

// -----------------------------------------------------------------------------
// SUMMARY
// -----------------------------------------------------------------------------

RETURN 'Graph seeds applied successfully' as status,
       size((:Node)) as nodes,
       size((:Service)) as services,
       size((:Engine)) as engines,
       size((:Tool)) as tools,
       size((:Intent)) as intents;
