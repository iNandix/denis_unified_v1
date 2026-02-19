# Overlay / Atlas Graph Mapping

## Overview

This document maps the Overlay Filesystem and AtlasLite concepts to the Graph schema, clarifying what is a node, artifact, or snapshot.

## Conceptual Model

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           OVERLAY FILESYSTEM                             │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     Logical Namespace                            │   │
│  │  overlay://denis_repo/src/main.py                               │   │
│  │  overlay://artifacts/output.json                                │   │
│  │  overlay://config/settings.yaml                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼ resolve()                                 │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     Physical Mapping                              │   │
│  │  nodomac:/Users/jotah/projects/denis/src/main.py              │   │
│  │  nodomac:/home/jotah/denis/artifacts/output.json               │   │
│  │  nodo1:/etc/denis/settings.yaml                                │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                │
│  │   SCAN      │  │   INDEX     │  │   VERIFY    │                │
│  │  (discover) │─▶│  (metadata) │─▶│  (validate) │                │
│  └──────────────┘  └──────────────┘  └──────────────┘                │
│         │                 │                 │                           │
│         ▼                 ▼                 ▼                           │
│  ┌──────────────────────────────────────────────────────────────┐     │
│  │                     MANIFEST (snapshot)                       │     │
│  │  {files: [{rel_path, size, mtime, sha256}], stats}          │     │
│  └──────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────┘
```

## What is What

| Concept | Type | Storage | Graph Node? |
|---------|------|---------|--------------|
| **Node** (nodomac, nodo1, nodo2) | Physical host | - | ✅ Yes |
| **Component** (overlay, atlaslite) | Service | - | ✅ Yes |
| **OverlayRoot** | Logical namespace | SQLite | ✅ Yes |
| **Manifest** | File index snapshot | SQLite + JSON | ✅ Yes |
| **Artifact** | Actual file content | filesystem | ❌ No (reference only) |
| **Run** | Step execution | SQLite | ❌ No (reference only) |

## Graph vs Artifact Storage

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              GRAPH                                       │
│  (Metadata, relationships, state)                                      │
│                                                                         │
│  Node ──HOSTS──▶ Component ──DEFINES_ROOT──▶ OverlayRoot             │
│                                              │                         │
│                                              ▼                         │
│                                        OverlayRoot ──HAS_MANIFEST──▶ Manifest
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ references
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           ARTIFACTS                                      │
│  (Actual file content - NOT in graph)                                  │
│                                                                         │
│  /home/jotah/nodomac/overlay/artifacts/                                │
│    ├── snapshot_20260217.json       (manifest payload)                │
│    ├── manifest_files.json          (full file list)                  │
│    └── probes_report.json           (scan results)                    │
│                                                                         │
│  /media/jotah/SSD_denis/home_jotah/nodomac/var/                      │
│    └── snapshots/                                                       │
│        └── last_good_snapshot.json  (control room snapshot)          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Manifest Representation in Graph

```cypher
// Overlay Root definition
MERGE (r:OverlayRoot {id: 'denis_repo'})
SET r.logical_prefix = 'overlay://denis_repo',
    r.description = 'Main DENIS repository'

// Component defines root
MATCH (c:Component {id: 'overlay'})
MATCH (r:OverlayRoot {id: 'denis_repo'})
MERGE (c)-[:DEFINES_ROOT]->(r)

// Manifest for root
MERGE (m:Manifest {id: 'manifest_denis_repo_001'})
SET m.root_id = 'denis_repo',
    m.generated_at = '2026-02-17T00:00:00Z',
    m.status = 'current',
    m.total_files = 1234,
    m.total_bytes = 56789012,
    m.payload_ref = 'overlay/artifacts/snapshot_20260217.json'

MERGE (r)-[:HAS_MANIFEST]->(m)
```

## Flow: Scan → Index → Verify → Snapshot

```
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 1: SCAN (overlay_scan)                                            │
│                                                                         │
│ Input:  Physical paths on node                                         │
│ Output: File list with metadata (size, mtime)                          │
│ Storage: /home/jotah/nodomac/overlay/artifacts/probes_report.json      │
│ Graph:   No update (just local artifact)                                │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 2: INDEX (overlay_index)                                          │
│                                                                         │
│ Input:  probes_report.json                                             │
│ Output: overlay_entries in SQLite                                      │
│ Storage: /home/jotah/nodomac/nodomac.db (overlay_entries table)       │
│ Graph:   CREATE (e:OverlayEntry {path, size, mtime, sha256})         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 3: VERIFY (overlay_verify)                                        │
│                                                                         │
│ Input:  overlay_entries, expected metadata                              │
│ Output: Diff report                                                    │
│ Storage: /home/jotah/nodomac/overlay/artifacts/diff_report.json      │
│ Graph:   CREATE (d:DiffReport {added, removed, modified})             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 4: SNAPSHOT (manifest push)                                       │
│                                                                         │
│ Input:  Current overlay_entries                                         │
│ Output: Manifest JSON (current file index)                              │
│ Storage: /home/jotah/nodomac/overlay/artifacts/snapshot_{timestamp}.json│
│ Graph:   CREATE (m:Manifest) - see above                              │
└─────────────────────────────────────────────────────────────────────────┘
```

## AtlasLite Alignment

AtlasLite provides graph projection capabilities. It maps runtime data to the graph:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           ATLASLITE                                      │
│                                                                         │
│  Input Sources:                                                        │
│    - Overlay manifest (from overlay component)                         │
│    - Control room runs (from control_room component)                   │
│    - Chat CP traces (from chat_cp, if enabled)                        │
│                                                                         │
│  Graph Projections:                                                    │
│    - OverlayRoot entities                                              │
│    - Manifest nodes with stats                                         │
│    - File relationship to nodes                                        │
│    - Run/Step execution history                                        │
└─────────────────────────────────────────────────────────────────────────┘
```

## Key Distinctions

| Concept | In Graph | In SQLite | In Filesystem |
|---------|----------|-----------|---------------|
| Node definition | ✅ | - | - |
| Component definition | ✅ | - | - |
| Overlay root | ✅ | ✅ | - |
| Manifest metadata | ✅ | ✅ | - |
| File entries | - | ✅ | - |
| Actual file content | - | - | ✅ |
| Run history | - | ✅ | - |
| Snapshots | - | ✅ | ✅ |

## Query Examples

### Get all manifests for a root

```cypher
MATCH (r:OverlayRoot {id: 'denis_repo'})-[:HAS_MANIFEST]->(m:Manifest)
RETURN m.id, m.generated_at, m.status, m.total_files
ORDER BY m.generated_at DESC
LIMIT 10
```

### Get files for a manifest

```cypher
// Note: File entries are in SQLite, not graph
// This is a reference query
MATCH (m:Manifest {id: 'manifest_denis_repo_001'})
RETURN m.payload_ref AS artifact_path
// Then read from filesystem
```

### Get overlay roots

```cypher
MATCH (c:Component {id: 'overlay'})-[:DEFINES_ROOT]->(r:OverlayRoot)
RETURN r.id, r.logical_prefix
```

## Summary

- **Graph**: Stores definitions (nodes, components, roots, manifests as references)
- **SQLite**: Stores operational data (entries, runs, snapshots)
- **Filesystem**: Stores actual content (artifacts, snapshots)

This separation keeps the graph lightweight for queries while SQLite handles heavy indexing.
