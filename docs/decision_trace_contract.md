# Decision Trace Contract

## Overview

This document defines the minimal DecisionTrace schema for auditing and debugging routing decisions in the DENIS system.

## Purpose

- **Auditability**: Track all routing decisions for compliance
- **Debugging**: Understand why a particular provider was selected
- **Optimization**: Analyze latency, success rates, and fallback patterns
- **Observability**: Correlate decisions with outcomes

## DecisionTrace Schema

### Core Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `trace_id` | UUID | Yes | Unique trace identifier |
| `timestamp` | ISO8601 | Yes | Decision timestamp |
| `decision_type` | Enum | Yes | Type of decision (routing, policy, action) |
| `inputs` | Object | Yes | Decision inputs |
| `policy` | String | Yes | Policy name used |
| `selected` | String | Yes | Selected option |
| `fallback_chain` | Array | Yes | Options in fallback order |
| `outcome` | Enum | Yes | success, failure, fallback |
| `latency_ms` | Integer | Yes | Decision latency |
| `error` | Object | No | Error details if outcome = failure |

### Decision Types

| Type | Description |
|------|-------------|
| `routing` | Provider selection in Chat CP |
| `policy` | Policy enforcement decision |
| `action` | Action selection |
| `orchestration` | Step selection in Control Room |

### Input Schemas

#### Routing Decision Inputs

```json
{
  "request_id": "req_abc123",
  "user_id": "user_001",
  "intent": "chat_completion",
  "model_preference": "gpt-4o-mini",
  "requires_vision": false,
  "max_latency_ms": 5000,
  "fallback_allowed": true
}
```

#### Policy Decision Inputs

```json
{
  "request_id": "req_abc123",
  "action": "execute_tool",
  "tool_name": "infra.perceive.nodomac",
  "risk_level": "low",
  "requires_approval": false
}
```

## Example DecisionTraces

### Example 1: Successful Routing Decision

```json
{
  "trace_id": "trace_001",
  "timestamp": "2026-02-17T10:30:00Z",
  "decision_type": "routing",
  "inputs": {
    "request_id": "req_abc123",
    "intent": "chat_completion",
    "model_preference": "gpt-4o-mini"
  },
  "policy": "default_chain",
  "selected": "anthropic_chat",
  "fallback_chain": ["anthropic_chat", "openai_chat", "local_chat"],
  "outcome": "success",
  "latency_ms": 450,
  "details": {
    "model": "claude-3-5-haiku-latest",
    "provider_latency_ms": 420,
    "tokens_used": 18
  }
}
```

### Example 2: Fallback Routing Decision

```json
{
  "trace_id": "trace_002",
  "timestamp": "2026-02-17T10:31:00Z",
  "decision_type": "routing",
  "inputs": {
    "request_id": "req_def456",
    "intent": "chat_completion"
  },
  "policy": "default_chain",
  "selected": "openai_chat",
  "fallback_chain": ["anthropic_chat", "openai_chat", "local_chat"],
  "outcome": "fallback",
  "latency_ms": 1250,
  "error": {
    "code": "quota_exceeded",
    "provider": "anthropic_chat",
    "message": "Anthropic quota exceeded"
  },
  "details": {
    "fallback_reason": "provider_unavailable",
    "attempts": 1
  }
}
```

### Example 3: Failed Decision with Local Fallback

```json
{
  "trace_id": "trace_003",
  "timestamp": "2026-02-17T10:32:00Z",
  "decision_type": "routing",
  "inputs": {
    "request_id": "req_ghi789",
    "intent": "chat_completion"
  },
  "policy": "default_chain",
  "selected": "local_chat",
  "fallback_chain": ["anthropic_chat", "openai_chat", "local_chat"],
  "outcome": "success",
  "latency_ms": 5,
  "details": {
    "mode": "degraded",
    "reason": "All external providers failed"
  }
}
```

### Example 4: Orchestration Step Decision

```json
{
  "trace_id": "trace_004",
  "timestamp": "2026-02-17T10:33:00Z",
  "decision_type": "orchestration",
  "inputs": {
    "run_id": "run_001",
    "goal": "index_overlay"
  },
  "policy": "overlay_pipeline",
  "selected": "overlay_scan",
  "fallback_chain": ["overlay_scan", "overlay_manifest_push"],
  "outcome": "success",
  "latency_ms": 12500,
  "details": {
    "step": "overlay_scan",
    "files_found": 1234,
    "duration_ms": 12000
  }
}
```

## Graph Storage

DecisionTraces are stored in Neo4j as Decision nodes:

```cypher
CREATE (d:Decision {
    id: 'trace_001',
    trace_id: 'trace_001',
    timestamp: datetime('2026-02-17T10:30:00Z'),
    decision_type: 'routing',
    inputs: {
        request_id: 'req_abc123',
        intent: 'chat_completion'
    },
    policy: 'default_chain',
    selected: 'anthropic_chat',
    fallback_chain: ['anthropic_chat', 'openai_chat', 'local_chat'],
    outcome: 'success',
    latency_ms: 450
})
```

## Queries

### Get recent routing decisions

```cypher
MATCH (d:Decision {decision_type: 'routing'})
WHERE d.timestamp > datetime() - duration({hours: 1})
RETURN d.trace_id, d.selected, d.outcome, d.latency_ms
ORDER BY d.timestamp DESC
LIMIT 100
```

### Get fallback rate

```cypher
MATCH (d:Decision {decision_type: 'routing'})
WHERE d.timestamp > datetime() - duration({days: 7})
RETURN d.outcome, count(*) AS count
ORDER BY count DESC
```

### Get average latency by provider

```cypher
MATCH (d:Decision {decision_type: 'routing'})
WHERE d.timestamp > datetime() - duration({days: 1})
RETURN d.selected, avg(d.latency_ms) AS avg_latency, count(*) AS requests
ORDER BY avg_latency
```

## Implementation

### Python Interface

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import uuid4

@dataclass
class DecisionTrace:
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    decision_type: str
    inputs: dict
    policy: str
    selected: str
    fallback_chain: list[str]
    outcome: str  # success, failure, fallback
    latency_ms: int
    error: Optional[dict] = None
    details: dict = field(default_factory=dict)

    def to_graph_node(self) -> dict:
        return {
            "id": self.trace_id,
            "trace_id": self.trace_id,
            "timestamp": self.timestamp.isoformat(),
            "decision_type": self.decision_type,
            "inputs": self.inputs,
            "policy": self.policy,
            "selected": self.selected,
            "fallback_chain": self.fallback_chain,
            "outcome": self.outcome,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "details": self.details
        }
```

### Writing to Graph

```python
def write_decision_trace(trace: DecisionTrace):
    query = """
    CREATE (d:Decision $props)
    """
    neo4j.execute(query, props=trace.to_graph_node())
```

## Retention Policy

| Decision Type | Retention | Reason |
|--------------|-----------|--------|
| routing | 30 days | High volume, analytics |
| policy | 90 days | Audit trail |
| action | 30 days | Debugging |
| orchestration | 90 days | Audit trail |

## Feature Flag

Writing decision traces is controlled by `DENIS_CHAT_CP_GRAPH_WRITE`:

- `DENIS_CHAT_CP_GRAPH_WRITE=1` - Enable writing
- `DENIS_CHAT_CP_GRAPH_WRITE=0` - Disable (default)

## Summary

DecisionTrace provides a complete audit trail of all routing and policy decisions in the DENIS system, enabling:
- Debugging of failures
- Analysis of provider performance
- Optimization of routing policies
- Compliance and audit requirements
