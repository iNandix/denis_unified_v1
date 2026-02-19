// System State Seed - Idempotent
// Generated: 2026-02-16
// Run with: cypher-shell -u neo4j -p <password> < system_state_v1.cypher

// SystemState node
MERGE (s:SystemState {id: 'denis_unified_v1'})
SET s.generated_at = '2026-02-16T23:45:00Z',
    s.status = 'stable',
    s.confidence = 'high'
RETURN s;

// Components
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
MERGE (s)-[:HAS_COMPONENT]->(c_denis)

// Blockers (none currently)
MERGE (b_no_blockers:Blocker {id: 'no_critical_blockers'})
SET b_no_blockers.description = 'All claimed components exist in nodomac',
    b_no_blockers.status = 'resolved'

MERGE (s)-[:HAS_BLOCKER]->(b_no_blockers)

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
RETURN s, c_overlay, c_control_room, c_leases, c_heartbeats, c_snapshot, c_atlaslite, c_denis;
