# Graph IoT Schema

## Overview

Extension of the DENIS graph schema for IoT, Care, and Home Assistant integration.

---

## Node Types

### 1. Device

IoT devices and sensors.

```cypher
(:Device {
    id: String,              -- unique identifier
    name: String,           -- display name
    type: String,          -- camera, sensor, switch, light, lock
    model: String,         -- device model
    manufacturer: String,  -- manufacturer
    status: String,        -- online, offline, error
    battery_level: Integer, -- percentage (0-100)
    last_seen: ISO8601,    -- last communication
    hass_entity_id: String -- Home Assistant entity ID
})
```

### 2. Camera

Security cameras and visual sensors.

```cypher
(:Camera {
    id: String,
    name: String,
    resolution: String,    -- "1080p", "4K"
    fps: Integer,         -- frames per second
    has_audio: Boolean,   -- microphone available
    has_night_vision: Boolean,
    motion_detection: Boolean,
    last_frame_url: String
})
```

### 3. Sensor

Physical sensors measuring environmental conditions.

```cypher
(:Sensor {
    id: String,
    name: String,
    type: String,         -- temperature, humidity, motion, light, air_quality
    unit: String,         -- celsius, percent, lux, ppm
    min_value: Float,     -- sensor range minimum
    max_value: Float,     -- sensor range maximum
    current_value: Float, -- last reading
    last_updated: ISO8601
})
```

### 4. Room

Physical spaces in the environment.

```cypher
(:Room {
    id: String,
    name: String,
    floor: Integer,
    area_sqm: Float,
    room_type: String     -- bedroom, living_room, kitchen, office
})
```

### 5. Person

Users and occupants.

```cypher
(:Person {
    id: String,
    name: String,
    type: String,         -- user, guest, admin
    preferences: Map,     -- personalization settings
    home_location: Point  -- home GPS coordinates
})
```

### 6. Presence

Current location of persons.

```cypher
(:Presence {
    id: String,
    person_id: String,
    location_type: String, -- home, away, room_id
    confidence: Float,    -- 0.0 to 1.0
    detected_at: ISO8601,
    expires_at: ISO8601
})
```

### 7. GeoPoint

GPS coordinates for devices and persons.

```cypher
(:GeoPoint {
    id: String,
    lat: Float,          -- latitude
    lon: Float,          -- longitude
    accuracy: Float,     -- accuracy in meters
    altitude: Float,     -- meters above sea level
    timestamp: ISO8601
})
```

### 8. HassEntity

Home Assistant entity abstraction.

```cypher
(:HassEntity {
    entity_id: String,   -- unique HASS entity ID
    domain: String,      -- light, sensor, camera, switch
    friendly_name: String,
    state: String,       -- current state
    attributes: Map,     -- HASS attributes
    last_changed: ISO8601,
    last_updated: ISO8601
})
```

### 9. Event

Generic event from devices or system.

```cypher
(:Event {
    id: String,
    event_type: String,  -- motion, state_change, alert, command
    source_id: String,   -- device/person that generated it
    timestamp_ms: Integer,  -- REQUIRED
    payload: Map,        -- event-specific data
    processed: Boolean   -- whether action was taken
})
```

### 10. Alert

Care alerts and notifications.

```cypher
(:Alert {
    id: String,
    severity: String,    -- info, warning, critical
    subject: String,     -- what/who is affected
    source: String,      -- which device/system triggered it
    message: String,
    created_at: ISO8601,
    acknowledged: Boolean,
    acknowledged_by: String,
    resolved_at: ISO8601
})
```

---

## Relationship Types

| Relationship | From | To | Properties |
|--------------|------|-----|------------|
| OWNS | Person | Device | `since: ISO8601` |
| LOCATED_IN | Device | Room | `installed_at: ISO8601` |
| REPORTS | Sensor | HassEntity | - |
| OBSERVES | Camera | Room | `coverage_area: String` |
| TRIGGERS | Event | Alert | `confidence: Float` |
| LINKS_TO | HassEntity | Device | - |
| GENERATED_BY | Event | Device | - |
| CURRENT_LOCATION | Person | Presence | - |
| AT_LOCATION | Presence | Room | - |
| HAS_COORDINATES | Presence | GeoPoint | - |

---

## Invariants

### Required Properties

| Node | Required Fields |
|------|----------------|
| Event | `id`, `event_type`, `timestamp_ms`, `source_id` |
| Alert | `id`, `severity`, `subject`, `source`, `created_at` |
| Device | `id`, `name`, `type`, `status` |
| Sensor | `id`, `name`, `type`, `unit` |
| Presence | `id`, `person_id`, `detected_at` |

### Constraints

1. **Event.timestamp_ms must be present and valid**
2. **Alert.severity must be one of: info, warning, critical**
3. **Device.status must be one of: online, offline, error**
4. **Presence.confidence must be between 0.0 and 1.0**
5. **GeoPoint.lat must be between -90 and 90**
6. **GeoPoint.lon must be between -180 and 180**

---

## Example Graph

```
(Person:Jota)-[:OWNS]->(Device:Phone)
                     |
                     v
              (Presence:Jota_now)
                     |
                     |[:AT_LOCATION]
                     v
              (Room:LivingRoom)
                     ^
                     |
    (Camera:FrontDoor)-[:OBSERVES]->(Room:LivingRoom)
                     |
                     v
            (Event:Motion_001)
                     |
                     |[:TRIGGERS]
                     v
            (Alert:UnusualActivity)
```

---

## Indexes

```cypher
CREATE INDEX device_id IF NOT EXISTS FOR (d:Device) ON (d.id);
CREATE INDEX device_hass_entity IF NOT EXISTS FOR (d:Device) ON (d.hass_entity_id);
CREATE INDEX event_timestamp IF NOT EXISTS FOR (e:Event) ON (e.timestamp_ms);
CREATE INDEX alert_severity IF NOT EXISTS FOR (a:Alert) ON (a.severity);
CREATE INDEX sensor_type IF NOT EXISTS FOR (s:Sensor) ON (s.type);
CREATE INDEX presence_person IF NOT EXISTS FOR (p:Presence) ON (p.person_id);
CREATE INDEX geopoint_coords IF NOT EXISTS FOR (g:GeoPoint) ON (g.lat, g.lon);
CREATE INDEX hass_entity_id IF NOT EXISTS FOR (h:HassEntity) ON (h.entity_id);
```

---

## Query Examples

### Get all devices in a room

```cypher
MATCH (r:Room {id: 'living_room'})<-[:LOCATED_IN]-(d:Device)
RETURN d.name, d.type, d.status
```

### Get recent events for a device

```cypher
MATCH (d:Device {id: 'front_door_cam'})<-[:GENERATED_BY]-(e:Event)
WHERE e.timestamp_ms > timestamp() - 3600000
RETURN e.event_type, e.timestamp_ms, e.payload
ORDER BY e.timestamp_ms DESC
```

### Get active alerts

```cypher
MATCH (a:Alert)
WHERE a.resolved_at IS NULL
RETURN a.severity, a.subject, a.message, a.created_at
ORDER BY 
  CASE a.severity
    WHEN 'critical' THEN 1
    WHEN 'warning' THEN 2
    ELSE 3
  END
```

### Get person current location

```cypher
MATCH (p:Person {id: 'jota'})-[:CURRENT_LOCATION]->(pres:Presence)
OPTIONAL MATCH (pres)-[:AT_LOCATION]->(r:Room)
OPTIONAL MATCH (pres)-[:HAS_COORDINATES]->(g:GeoPoint)
RETURN 
  CASE 
    WHEN r IS NOT NULL THEN r.name
    WHEN g IS NOT NULL THEN 'GPS: ' + g.lat + ',' + g.lon
    ELSE pres.location_type
  END as location
```

---

## Integration with Existing Schema

This IoT schema extends the existing Graph Schema v3:

- **Device** extends the concept of nodes
- **Person** connects to existing users
- **Event** connects to Decision traces
- **Alert** connects to Care system

Merge with existing nodes using:

```cypher
// Link existing Person to IoT Person
MATCH (p:Person {id: 'user_001'})
SET p:IoTPerson,
    p.home_location = point({latitude: 37.7749, longitude: -122.4194})
```
