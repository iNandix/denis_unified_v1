// System State Seed - Idempotent (v3)
// Generated: 2026-02-17
// Canonical Graph Schema for Control Plane
// Run with: cypher-shell -u neo4j -p <password> < system_state_v3.cypher

// =============================================================================
// NODES (Physical/Logical Hosts)
// =============================================================================

MERGE (n_nodomac:Node {id: 'nodomac'})
SET n_nodomac.name = 'nodomac',
    n_nodomac.hostname = 'nodomac.local',
    n_nodomac.ip = '127.0.0.1',
    n_nodomac.platform = 'macOS',
    n_nodomac.is_local = true,
    n_nodomac.created_at = '2026-02-11T00:00:00Z'

MERGE (n_nodo1:Node {id: 'nodo1'})
SET n_nodo1.name = 'nodo1',
    n_nodo1.hostname = 'denis-server',
    n_nodo1.ip = 'localhost',
    n_nodo1.platform = 'Linux',
    n_nodo1.is_local = true,
    n_nodo1.created_at = '2026-02-11T00:00:00Z'

MERGE (n_nodo2:Node {id: 'nodo2'})
SET n_nodo2.name = 'nodo2',
    n_nodo2.hostname = 'nodo2',
    n_nodo2.ip = '10.10.10.2',
    n_nodo2.platform = 'Linux',
    n_nodo2.is_local = false,
    n_nodo2.gpu = '1050Ti 4GB',
    n_nodo2.created_at = '2026-02-11T00:00:00Z'

// Node relationships
MERGE (n_nodomac)-[:CONNECTED_TO {type: 'ssh', latency_ms: 5}]->(n_nodo1)
MERGE (n_nodo1)-[:CONNECTED_TO {type: 'ssh', latency_ms: 5}]->(n_nodomac)
MERGE (n_nodo1)-[:CONNECTED_TO {type: 'http', latency_ms: 2}]->(n_nodo2)
MERGE (n_nodo2)-[:CONNECTED_TO {type: 'http', latency_ms: 2}]->(n_nodo1)

// =============================================================================
// COMPONENTS (Software Services)
// =============================================================================

// Chat CP Layer
MERGE (c_chat_cp:Component {id: 'chat_cp'})
SET c_chat_cp.name = 'Chat Control Plane',
    c_chat_cp.type = 'service',
    c_chat_cp.location = '/media/jotah/SSD_denis/home_jotah/denis_unified_v1/denis_unified_v1/chat_cp',
    c_chat_cp.port = 9999,
    c_chat_cp.status = 'feature_flagged',
    c_chat_cp.version = '0.1.0',
    c_chat_cp.description = 'Multi-provider chat abstraction (OpenAI, Anthropic, Local)'

// Chat CP Providers
MERGE (c_openai:Provider {id: 'openai_chat'})
SET c_openai.name = 'OpenAI Chat',
    c_openai.type = 'provider',
    c_openai.parent = 'chat_cp',
    c_openai.status = 'configured',
    c_openai.model_default = 'gpt-4o-mini'

MERGE (c_anthropic:Provider {id: 'anthropic_chat'})
SET c_anthropic.name = 'Anthropic Chat',
    c_anthropic.type = 'provider',
    c_anthropic.parent = 'chat_cp',
    c_anthropic.status = 'configured',
    c_anthropic.model_default = 'claude-3-5-haiku-latest'

MERGE (c_local:Provider {id: 'local_chat'})
SET c_local.name = 'Local Fallback',
    c_local.type = 'provider',
    c_local.parent = 'chat_cp',
    c_local.status = 'available',
    c_local.model_default = 'local_stub'

// Component → Provider relationships
MERGE (c_chat_cp)-[:HAS_PROVIDER]->(c_openai)
MERGE (c_chat_cp)-[:HAS_PROVIDER]->(c_anthropic)
MERGE (c_chat_cp)-[:HAS_PROVIDER]->(c_local)

// Overlay Filesystem
MERGE (c_overlay:Component {id: 'overlay'})
SET c_overlay.name = 'Overlay Filesystem',
    c_overlay.type = 'service',
    c_overlay.location = '/home/jotah/nodomac/overlay',
    c_overlay.port = 19999,
    c_overlay.status = 'active',
    c_overlay.description = 'Logical-to-physical path resolver with manifests'

// Control Room
MERGE (c_control_room:Component {id: 'control_room'})
SET c_control_room.name = 'Control Room',
    c_control_room.type = 'orchestration',
    c_control_room.location = '/home/jotah/nodomac/control_room',
    c_control_room.status = 'active',
    c_control_room.description = 'Step-based automation (scan, index, verify, push)'

// Control Room Steps
FOREACH (step IN ['overlay_scan', 'overlay_manifest_push', 'nodomac_scrape_cycle', 'integration_smoke', 'multi_node_test', 'pytest_run'] |
    MERGE (s:Step {id: step})
    SET s.name = step,
        s.component = 'control_room'
    MERGE (c_control_room)-[:HAS_STEP]->(s)
)

// Inference Gateway
MERGE (c_inference:Component {id: 'inference_gateway'})
SET c_inference.name = 'Inference Gateway',
    c_inference.type = 'service',
    c_inference.location = '/media/jotah/SSD_denis/home_jotah/denis_unified_v1/denis_unified_v1/inference',
    c_inference.status = 'active',
    c_inference.description = 'Multi-provider LLM routing with fallback'

// AtlasLite
MERGE (c_atlaslite:Component {id: 'atlaslite'})
SET c_atlaslite.name = 'AtlasLite',
    c_atlaslite.type = 'service',
    c_atlaslite.location = '/home/jotah/nodomac',
    c_atlaslite.port = 19998,
    c_atlaslite.status = 'active',
    c_atlaslite.description = 'Metadata resolver and graph projection'

// Hardening Components
MERGE (c_leases:Component {id: 'lease_manager'})
SET c_leases.name = 'Lease Manager',
    c_leases.type = 'hardening',
    c_leases.location = '/home/jotah/nodomac/control_room/hardening/leases.py',
    c_leases.status = 'active'

MERGE (c_heartbeats:Component {id: 'heartbeat_manager'})
SET c_heartbeats.name = 'Heartbeat Manager',
    c_heartbeats.type = 'hardening',
    c_heartbeats.location = '/home/jotah/nodomac/control_room/hardening/heartbeats.py',
    c_heartbeats.status = 'active'

// =============================================================================
// NODE → COMPONENT DEPLOYMENTS
// =============================================================================

// nodomac hosts
MERGE (n_nodomac)-[:HOSTS {since: '2026-02-11'}]->(c_chat_cp)
MERGE (n_nodomac)-[:HOSTS {since: '2026-02-11'}]->(c_overlay)
MERGE (n_nodomac)-[:HOSTS {since: '2026-02-11'}]->(c_control_room)
MERGE (n_nodomac)-[:HOSTS {since: '2026-02-11'}]->(c_atlaslite)
MERGE (n_nodomac)-[:HOSTS {since: '2026-02-11'}]->(c_leases)
MERGE (n_nodomac)-[:HOSTS {since: '2026-02-11'}]->(c_heartbeats)

// nodo1 hosts
MERGE (n_nodo1)-[:HOSTS {since: '2026-02-11'}]->(c_inference)
MERGE (n_nodo1)-[:HOSTS {since: '2026-02-11'}]->(c_chat_cp)

// nodo2 hosts
MERGE (n_nodo2)-[:HOSTS {since: '2026-02-11'}]->(c_inference)

// =============================================================================
// FEATURE FLAGS
// =============================================================================

MERGE (ff1:FeatureFlag {id: 'DENIS_ENABLE_CHAT_CP'})
SET ff1.name = 'DENIS_ENABLE_CHAT_CP',
    ff1.default_value = false,
    ff1.description = 'Enable Chat Control Plane layer',
    ff1.component = 'chat_cp'

MERGE (ff2:FeatureFlag {id: 'DENIS_CHAT_CP_SHADOW_MODE'})
SET ff2.name = 'DENIS_CHAT_CP_SHADOW_MODE',
    ff2.default_value = false,
    ff2.description = 'Log Chat CP requests without executing',
    ff2.component = 'chat_cp'

MERGE (ff3:FeatureFlag {id: 'DENIS_CHAT_CP_GRAPH_WRITE'})
SET ff3.name = 'DENIS_CHAT_CP_GRAPH_WRITE',
    ff3.default_value = false,
    ff3.description = 'Write Chat CP traces to Neo4j',
    ff3.component = 'chat_cp'

// Feature flags belong to components
MERGE (c_chat_cp)-[:HAS_FEATURE_FLAG]->(ff1)
MERGE (c_chat_cp)-[:HAS_FEATURE_FLAG]->(ff2)
MERGE (c_chat_cp)-[:HAS_FEATURE_FLAG]->(ff3)

// =============================================================================
// HEALTH & STATE
// =============================================================================

// Node states
MERGE (hs_nodomac:HealthState {id: 'nodomac_health'})
SET hs_nodomac.node_id = 'nodomac',
    hs_nodomac.status = 'alive',
    hs_nodomac.checked_at = '2026-02-17T00:00:00Z',
    hs_nodomac.details = {}

MERGE (hs_nodo1:HealthState {id: 'nodo1_health'})
SET hs_nodo1.node_id = 'nodo1',
    hs_nodo1.status = 'alive',
    hs_nodo1.checked_at = '2026-02-17T00:00:00Z',
    hs_nodo1.details = {}

MERGE (hs_nodo2:HealthState {id: 'nodo2_health'})
SET hs_nodo2.node_id = 'nodo2',
    hs_nodo2.status = 'alive',
    hs_nodo2.checked_at = '2026-02-17T00:00:00Z',
    hs_nodo2.details = {}

// Link health to nodes
MERGE (n_nodomac)-[:HAS_HEALTH]->(hs_nodomac)
MERGE (n_nodo1)-[:HAS_HEALTH]->(hs_nodo1)
MERGE (n_nodo2)-[:HAS_HEALTH]->(hs_nodo2)

// =============================================================================
// SYSTEM STATE ROOT
// =============================================================================

MERGE (s:SystemState {id: 'denis_unified_v1'})
SET s.generated_at = '2026-02-17T00:00:00Z',
    s.version = 'v3',
    s.status = 'stable',
    s.confidence = 'high'

// System state references all components
MERGE (s)-[:HAS_COMPONENT]->(c_chat_cp)
MERGE (s)-[:HAS_COMPONENT]->(c_overlay)
MERGE (s)-[:HAS_COMPONENT]->(c_control_room)
MERGE (s)-[:HAS_COMPONENT]->(c_inference)
MERGE (s)-[:HAS_COMPONENT]->(c_atlaslite)
MERGE (s)-[:HAS_COMPONENT]->(c_leases)
MERGE (s)-[:HAS_COMPONENT]->(c_heartbeats)

// System state references all nodes
MERGE (s)-[:HAS_NODE]->(n_nodomac)
MERGE (s)-[:HAS_NODE]->(n_nodo1)
MERGE (s)-[:HAS_NODE]->(n_nodo2)

// =============================================================================
// ARTIFACTS & OVERLAY MAPPING (Reference for Overlay/Atlas)
// =============================================================================

// Root definitions (overlay_roots equivalent)
FOREACH (root IN ['denis_repo', 'artifacts', 'datasets', 'config'] |
    MERGE (r:OverlayRoot {id: root})
    SET r.logical_prefix = 'overlay://' + root,
        r.description = 'Root: ' + root
    MERGE (c_overlay)-[:DEFINES_ROOT]->(r)
)

// Manifests (reference)
MERGE (m:Manifest {id: 'default_manifest'})
SET m.root_id = 'denis_repo',
    m.generated_at = '2026-02-17T00:00:00Z',
    m.status = 'current'
MERGE (c_overlay)-[:HAS_MANIFEST]->(m)

// Return summary
RETURN 'Graph v3 seeded successfully' AS result,
    size([(n:Node) | n]) AS node_count,
    size([(c:Component) | c]) AS component_count,
    size([(p:Provider) | p]) AS provider_count,
    size([(ff:FeatureFlag) | ff]) AS flag_count;
