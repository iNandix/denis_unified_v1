// System State Seed - Idempotent (v2)
// Generated: 2026-02-16
// Includes: Chat CP Layer
// Run with: cypher-shell -u neo4j -p <password> < system_state_v2.cypher

// SystemState node
MERGE (s:SystemState {id: 'denis_unified_v1'})
SET s.generated_at = '2026-02-16T23:45:00Z',
    s.version = 'v2',
    s.status = 'stable',
    s.confidence = 'high'
RETURN s;

// Overlay Components
MERGE (c_overlay:Component {id: 'overlay_filesystem'})
SET c_overlay.location = '/home/jotah/nodomac/overlay/',
    c_overlay.present = true,
    c_overlay.description = 'Filesystem overlay with resolve, verify, index, sync'

MERGE (c_control_room:Component {id: 'control_room_steps'})
SET c_control_room.location = '/home/jotah/nodomac/control_room/steps/',
    c_control_room.present = true,
    c_control_room.description = 'Control room steps: scan, push, scrape, smoke, test'

MERGE (c_leases:Component {id: 'lease_manager'})
SET c_leases.location = '/home/jotah/nodomac/control_room/hardening/leases.py',
    c_leases.present = true

MERGE (c_heartbeats:Component {id: 'heartbeat_manager'})
SET c_heartbeats.location = '/home/jotah/nodomac/control_room/hardening/heartbeats.py',
    c_heartbeats.present = true

MERGE (c_snapshot:Component {id: 'snapshot_manager'})
SET c_snapshot.location = '/home/jotah/nodomac/control_room/snapshot_manager.py',
    c_snapshot.present = true

MERGE (c_atlaslite:Component {id: 'atlaslite_api'})
SET c_atlaslite.location = '/home/jotah/nodomac/atlaslite_api.py',
    c_atlaslite.present = true

// Chat CP Layer (v2 new)
MERGE (c_chat_cp:Component {id: 'chat_cp_layer'})
SET c_chat_cp.location = '/media/jotah/SSD_denis/home_jotah/denis_unified_v1/denis_unified_v1/chat_cp/',
    c_chat_cp.present = true,
    c_chat_cp.integration_status = 'feature_flagged',
    c_chat_cp.description = 'Chat Control Plane - multi-provider routing (OpenAI, Anthropic, local)'

MERGE (c_openai_chat:Component {id: 'openai_chat'})
SET c_openai_chat.location = '/media/jotah/SSD_denis/home_jotah/denis_unified_v1/denis_unified_v1/chat_cp/providers/openai_chat.py',
    c_openai_chat.present = true,
    c_openai_chat.parent = 'chat_cp_layer'

MERGE (c_anthropic_chat:Component {id: 'anthropic_chat'})
SET c_anthropic_chat.location = '/media/jotah/SSD_denis/home_jotah/denis_unified_v1/denis_unified_v1/chat_cp/providers/anthropic_chat.py',
    c_anthropic_chat.present = true,
    c_anthropic_chat.parent = 'chat_cp_layer'

MERGE (c_local_chat:Component {id: 'local_chat_fallback'})
SET c_local_chat.location = '/media/jotah/SSD_denis/home_jotah/denis_unified_v1/denis_unified_v1/chat_cp/providers/local_chat.py',
    c_local_chat.present = true,
    c_local_chat.parent = 'chat_cp_layer'

// Denis Core
MERGE (c_denis:Component {id: 'denis_unified_v1'})
SET c_denis.location = '/media/jotah/SSD_denis/home_jotah/denis_unified_v1/',
    c_denis.present = true,
    c_denis.port = 9999

// Relationships: SystemState HAS_COMPONENT
MERGE (s)-[:HAS_COMPONENT]->(c_overlay)
MERGE (s)-[:HAS_COMPONENT]->(c_control_room)
MERGE (s)-[:HAS_COMPONENT]->(c_leases)
MERGE (s)-[:HAS_COMPONENT]->(c_heartbeats)
MERGE (s)-[:HAS_COMPONENT]->(c_snapshot)
MERGE (s)-[:HAS_COMPONENT]->(c_atlaslite)
MERGE (s)-[:HAS_COMPONENT]->(c_chat_cp)
MERGE (s)-[:HAS_COMPONENT]->(c_openai_chat)
MERGE (s)-[:HAS_COMPONENT]->(c_anthropic_chat)
MERGE (s)-[:HAS_COMPONENT]->(c_local_chat)
MERGE (s)-[:HAS_COMPONENT]->(c_denis)

// Chat CP dependencies (chat_cp_layer DEPENDS_ON)
MERGE (c_chat_cp)-[:DEPENDS_ON]->(c_openai_chat)
MERGE (c_chat_cp)-[:DEPENDS_ON]->(c_anthropic_chat)
MERGE (c_chat_cp)-[:DEPENDS_ON]->(c_local_chat)

// Blockers (none currently)
MERGE (b_no_blockers:Blocker {id: 'no_critical_blockers'})
SET b_no_blockers.description = 'All claimed components exist',
    b_no_blockers.status = 'resolved'

MERGE (s)-[:HAS_BLOCKER]->(b_no_blockers)

// Feature Flags
MERGE (ff1:FeatureFlag {id: 'DENIS_ENABLE_CHAT_CP'})
SET ff1.default = false,
    ff1.description = 'Enable Chat Control Plane layer'

MERGE (ff2:FeatureFlag {id: 'DENIS_CHAT_CP_SHADOW_MODE'})
SET ff2.default = false,
    ff2.description = 'Chat CP shadow mode - log without executing'

MERGE (ff3:FeatureFlag {id: 'DENIS_CHAT_CP_GRAPH_WRITE'})
SET ff3.default = false,
    ff3.description = 'Write Chat CP traces to Neo4j graph'

MERGE (s)-[:HAS_FEATURE_FLAG]->(ff1)
MERGE (s)-[:HAS_FEATURE_FLAG]->(ff2)
MERGE (s)-[:HAS_FEATURE_FLAG]->(ff3)

// Network topology
MERGE (n_nodomac:Node {id: 'nodomac'})
SET n_nodomac.ip = 'local',
    n_nodomac.services = ['atlaslite_api:19998', 'overlay_api:19999']

MERGE (n_nodo1:Node {id: 'nodo1'})
SET n_nodo1.ip = 'localhost',
    n_nodo1.services = ['denis_api:9999']

MERGE (n_nodo2:Node {id: 'nodo2'})
SET n_nodo2.ip = '10.10.10.2',
    n_nodo2.services = ['llm:8003-8008']

// Relationships: network
MERGE (n_nodomac)-[:CONNECTED_TO]->(n_nodo1)
MERGE (n_nodo1)-[:CONNECTED_TO]->(n_nodo2)
MERGE (n_nodomac)-[:CONNECTED_TO]->(n_nodo2)

// Done
RETURN s, c_overlay, c_control_room, c_chat_cp, c_openai_chat, c_anthropic_chat, c_local_chat;
