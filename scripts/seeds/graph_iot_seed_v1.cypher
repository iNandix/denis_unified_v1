// Graph IoT Seed v1 - Idempotent
// Run: cypher-shell -u neo4j -p <password> < graph_iot_seed_v1.cypher

// Indexes
CREATE INDEX device_id IF NOT EXISTS FOR (d:Device) ON (d.id);
CREATE INDEX event_timestamp IF NOT EXISTS FOR (e:Event) ON (e.timestamp_ms);
CREATE INDEX alert_severity IF NOT EXISTS FOR (a:Alert) ON (a.severity);

// Rooms
MERGE (r1:Room {id: 'living_room'}) SET r1.name = 'Living Room', r1.floor = 1;
MERGE (r2:Room {id: 'kitchen'}) SET r2.name = 'Kitchen', r2.floor = 1;

// Person
MERGE (p:Person {id: 'jota'}) SET p.name = 'Jota', p.type = 'admin';

// Devices - Camera
MERGE (cam:Camera {id: 'cam_front'}) SET cam.name = 'Front Door Cam', cam.type = 'camera', cam.status = 'online';

// Devices - Sensor
MERGE (s:Sensor {id: 'temp_living'}) SET s.name = 'Temp Sensor', s.type = 'temperature', s.unit = 'celsius';

// HASS Entity
MERGE (h:HassEntity {entity_id: 'camera.front_door'}) SET h.domain = 'camera', h.state = 'recording';

// Relationships
MERGE (p)-[:OWNS]->(cam);
MERGE (cam)-[:LOCATED_IN]->(r1);
MERGE (cam)-[:LINKS_TO]->(h);

// Sample Event
MERGE (e:Event {id: 'evt_001'}) SET e.event_type = 'motion', e.timestamp_ms = timestamp(), e.source_id = 'cam_front';
MERGE (e)-[:GENERATED_BY]->(cam);

// Sample Alert
MERGE (a:Alert {id: 'alert_001'}) SET a.severity = 'warning', a.subject = 'Motion Detected', a.source = 'cam_front';
MERGE (e)-[:TRIGGERS]->(a);

RETURN 'IoT seed completed';
