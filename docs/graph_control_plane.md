# Graph as Control Plane

## Overview

This document refines the role of Neo4j graph in the DENIS architecture. It clarifies what decisions should live in the graph, what is just telemetry, and what is authoritative versus derived.

---

## Core Principles

### 1. Authoritative Data
Data that defines system behavior and must be consulted for decisions.

- Provider chains and routing order
- Feature flag values
- Node topology and capabilities
- Component definitions
- Health states

### 2. Derived Data
Data that records system behavior for analysis and debugging.

- Decision traces (routing decisions)
- Event history (audit logs)
- Performance metrics
- Error logs

### 3. Telemetry
Data that monitors system health but does not drive decisions.

- Usage statistics
- Latency percentiles
- Request counts

---

## Data Classification

### Authoritative (Must Read)

| Data Type | Read By | When | Cache TTL |
|-----------|---------|------|-----------|
| Provider Chain | Chat CP | Every request | 60s |
| Feature Flags | All services | Startup + change | 30s |
| Node Topology | Control Room | Step execution | 60s |
| Health Status | All services | Periodic | 10s |

### Derived (Should Write)

| Data Type | Written By | When | Retention |
|-----------|------------|------|-----------|
| Routing Decisions | Chat CP | Every request | 30 days |
| Step Executions | Control Room | Every step | 90 days |
| State Changes | Health Manager | On change | 90 days |

### Telemetry (May Write)

| Data Type | Written By | When | Retention |
|-----------|------------|------|-----------|
| Usage Stats | API middleware | Periodic | 7 days |
| Latency Metrics | All services | Periodic | 7 days |

---

## Decision Authority Matrix

| Decision | Authority Source | Fallback |
|----------|------------------|----------|
| Which provider to use | Graph: Provider chain | Local config |
| Is feature enabled? | Graph: FeatureFlag | Environment |
| Is node healthy? | Graph: HealthState | Assume dead |
| What routes exist? | Graph: Topology | Static config |
| What policies apply? | Graph: Policy nodes | Default policy |

---

## Caching Strategy

### Cache Hierarchy

Applications cache graph data to reduce latency:

- Provider chain: 60s TTL
- Feature flags: 30s TTL
- Node topology: 60s TTL
- Health status: 10s TTL

### Invalidation Rules

| Data Type | Invalidation Trigger |
|-----------|---------------------|
| Provider chain | Provider status change |
| Feature flag | Flag value change |
| Node topology | Node add/remove |
| Health status | Health check update |

---

## Failure Handling

### Graph Unavailable

If graph is unavailable:
- Use cached values (may be stale)
- Log warning
- Continue operation

### Stale Data

If cached data older than 5 minutes:
- Log warning
- Use stale data
- Trigger background refresh

### Conflicting Data

If graph and cache conflict:
- Use graph (authoritative)
- Log info
- Update cache

---

## What is NOT in the Graph

### Keep Local/Operational

| Data | Reason | Storage |
|------|--------|---------|
| Actual file content | Too large | Filesystem |
| SQLite operational data | Too volatile | SQLite |
| Request bodies | Privacy | Logs |
| User credentials | Security | Keyring |

### Keep as Telemetry

| Data | Reason | Storage |
|------|--------|---------|
| Latency percentiles | Not actionable | Statsd/Metrics |
| Request counts | Not driving decisions | Metrics |
| Error rates | Monitored elsewhere | Logs |

---

## Governance

### Who Can Write

| Data Type | Who Writes | Approval Required |
|-----------|------------|-------------------|
| Node/Component registration | Deployment | Yes (code review) |
| Provider status | Health checker | No (automated) |
| Feature flags | Admin | Yes (config) |
| Decisions | Chat CP | No (automated) |

### Who Can Read

| Data Type | Who Reads | Authentication |
|-----------|-----------|----------------|
| All data | Internal services | Token-based |
| Decisions | Analytics | Read-only |

---

## Summary

The graph serves as:

1. **Authoritative source** for routing, topology, and configuration
2. **Audit trail** for decisions and state changes
3. **Not a** telemetry store or file storage

Query pattern: Read authoritative data frequently, write derived data occasionally.
