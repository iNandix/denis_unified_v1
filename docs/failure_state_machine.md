# Failure & Degraded Mode State Machine

## Overview

This document defines the standard states, transitions, and triggers for failure handling across the DENIS control plane.

## State Definitions

| State | Description | Service Impact |
|-------|-------------|----------------|
| **OK** | Full functionality | All operations normal |
| **DEGRADED** | Reduced functionality | Some features unavailable, fallback active |
| **STALE** | No recent updates | May be outdated, needs verification |
| **DOWN** | Not responding | No operations possible |
| **BLOCKED** | Waiting on external factor | Operations queued, not executing |

## State Diagram

```
                                    ┌─────────────────────────────────────┐
                                    │                                     │
                                    │     ┌─────────────────────────┐   │
                                    │     │                         │   │
                                    │     │                         ▼   │
      ┌──────────────┐              │     │  ┌──────────────┐          │
      │              │◀─────────────│─────│──│              │          │
      │     OK      │              │     │  │    DOWN      │          │
      │              │─────────────▶│─────│──│              │          │
      └──────────────┘              │     │  └──────────────┘          │
            │                       │     │        │                     │
            │ timeout              │     │        │ restart             │
            ▼                       │     │        ▼                     │
      ┌──────────────┐              │     │  ┌──────────────┐          │
      │              │◀─────────────│─────│──│              │          │
      │   DEGRADED   │              │     │  │   BLOCKED   │          │
      │              │─────────────▶│─────│──│              │          │
      └──────────────┘              │     │  └──────────────┘          │
            │                       │     │        │                     │
            │ recovery             │     │        │ unblock             │
            ▼                       │     │        ▼                     │
      ┌──────────────┐              │     │  ┌──────────────┐          │
      │              │◀─────────────│─────│──│              │          │
      │    STALE     │              │     │  │   RECOVERING │          │
      │              │─────────────▶│─────│──│              │          │
      └──────────────┘              │     │  └──────────────┘          │
                                    │     │                         │   │
                                    │     └─────────────────────────┘   │
                                    │                                     │
                                    └─────────────────────────────────────┘
```

## Triggers and Transitions

### OK → DEGRADED

| Trigger | Condition | Action |
|---------|-----------|--------|
| `provider_error` | Provider returns retryable error | Fallback to next provider |
| `timeout` | Request exceeds timeout | Fallback to next provider |
| `high_latency` | Latency > threshold (5s) | Mark provider degraded |
| `missing_secret` | Keyring returns None | Mark provider unavailable |
| `quota_exceeded` | API quota hit | Mark provider unavailable |

**Example:**
```
Provider: openai_chat
Trigger: quota_exceeded
Action: Set status='unavailable', select next provider in chain
```

### OK → STALE

| Trigger | Condition | Action |
|---------|-----------|--------|
| `heartbeat_timeout` | No heartbeat > 15s | Set status='stale' |
| `manifest_expired` | Manifest > 24h old | Set status='stale' |
| `step_timeout` | Step running > 10x timeout | Set status='stale' |

### OK → DOWN

| Trigger | Condition | Action |
|---------|-----------|--------|
| `connection_failed` | TCP connection refused | Mark node/component down |
| `process_exit` | Process exited unexpectedly | Mark component down |
| `disk_full` | Disk space < 1% | Mark node down |
| `oom` | Out of memory | Mark component down |

### DEGRADED → OK

| Trigger | Condition | Action |
|---------|-----------|--------|
| `recovery` | Provider responds successfully | Restore provider status |
| `heartbeat` | Fresh heartbeat received | Clear degraded flag |

### DEGRADED → STALE

| Trigger | Condition | Action |
|---------|-----------|--------|
| `no_recovery` | Degraded for > 5min | Escalate to stale |

### STALE → OK

| Trigger | Condition | Action |
|---------|-----------|--------|
| `heartbeat` | Fresh heartbeat received | Restore to alive |
| `reindex` | New manifest generated | Restore to current |

### STALE → DOWN

| Trigger | Condition | Action |
|---------|-----------|--------|
| `no_heartbeat` | No heartbeat > 60s | Mark as down |

### DOWN → RECOVERING

| Trigger | Condition | Action |
|---------|-----------|--------|
| `restart` | Process restarted | Begin health checks |
| `reconnect` | Connection restored | Verify functionality |

### RECOVERING → OK

| Trigger | Condition | Action |
|---------|-----------|--------|
| `health_ok` | 3 consecutive health checks pass | Restore to alive |

### RECOVERING → DOWN

| Trigger | Condition | Action |
|---------|-----------|--------|
| `health_fail` | Health check fails | Return to down |

### DEGRADED → BLOCKED

| Trigger | Condition | Action |
|---------|-----------|--------|
| `wait_for_secret` | Keyring locked | Queue operations |
| `wait_for_network` | Network partition | Queue operations |
| `wait_for_lease` | Cannot acquire lease | Queue operations |

### BLOCKED → DEGRADED

| Trigger | Condition | Action |
|---------|-----------|--------|
| `secret_available` | Keyring unlocked | Resume with degraded |
| `network_available` | Network restored | Resume with degraded |
| `lease_acquired` | Lease obtained | Resume operations |

## Provider-Specific Handling

### Chat CP Providers

```
Provider: openai_chat
├── OK ─[quota_exceeded]──▶ DEGRADED ─[fallback]──▶ (try anthropic_chat)
├── OK ─[auth_error]──────▶ DOWN ─[manual]────────▶ RECOVERING
├── OK ─[timeout]─────────▶ DEGRADED ─[retry]──────▶ OK (if success)
└── OK ─[rate_limit]───────▶ DEGRADED ─[backoff]────▶ OK (after backoff)
```

### Node Health

```
Node: nodomac
├── OK ─[heartbeat_timeout]──▶ STALE ─[no_recovery]──▶ DOWN
├── OK ─[cpu_high]───────────▶ DEGRADED ─[auto_recover]──▶ OK
└── OK ─[network_split]──────▶ BLOCKED ─[network_restore]──▶ OK
```

## Error Codes

| Code | Category | Retryable | Action |
|------|----------|-----------|--------|
| `auth_error` | Credentials | No | Disable provider |
| `quota_exceeded` | Rate limit | No | Disable provider |
| `rate_limited` | Rate limit | Yes | Backoff + retry |
| `timeout` | Network | Yes | Retry with backoff |
| `network_error` | Network | Yes | Retry + fallback |
| `missing_secret` | Config | No | Block until resolved |
| `disk_full` | Resource | No | Block operations |
| `oom` | Resource | No | Restart component |

## Implementation Example

```python
class StateMachine:
    def transition(self, entity: str, trigger: str, data: dict) -> str:
        current = self.get_state(entity)
        
        transitions = {
            ('OK', 'provider_error'): 'DEGRADED',
            ('OK', 'heartbeat_timeout'): 'STALE',
            ('OK', 'connection_failed'): 'DOWN',
            ('DEGRADED', 'recovery'): 'OK',
            ('DEGRADED', 'no_recovery'): 'STALE',
            ('STALE', 'heartbeat'): 'OK',
            ('STALE', 'no_heartbeat'): 'DOWN',
            ('DOWN', 'restart'): 'RECOVERING',
            ('RECOVERING', 'health_ok'): 'OK',
            ('RECOVERING', 'health_fail'): 'DOWN',
            ('DEGRADED', 'wait_for_secret'): 'BLOCKED',
            ('BLOCKED', 'secret_available'): 'DEGRADED',
        }
        
        new_state = transitions.get((current, trigger), current)
        self.set_state(entity, new_state)
        self.log_transition(entity, current, new_state, trigger, data)
        return new_state
```

## Monitoring Queries

### Get all degraded components

```cypher
MATCH (n:Node)-[:HAS_HEALTH]->(h:HealthState)
WHERE h.status IN ['degraded', 'stale', 'down', 'blocked']
RETURN n.id, h.status, h.checked_at
ORDER BY h.checked_at
```

### Get provider availability

```cypher
MATCH (c:Component {id: 'chat_cp'})-[:HAS_PROVIDER]->(p:Provider)
RETURN p.id, p.status
```

### Get recent state transitions

```cypher
MATCH (e:StateEvent)
WHERE e.timestamp > datetime() - duration({hours: 1})
RETURN e.entity, e.from_state, e.to_state, e.trigger, e.timestamp
ORDER BY e.timestamp DESC
```

## Summary Table

| From | Trigger | To | Action |
|------|---------|-----|--------|
| OK | provider_error | DEGRADED | Fallback |
| OK | timeout | DEGRADED | Retry |
| OK | heartbeat_timeout | STALE | Alert |
| OK | connection_failed | DOWN | Alert |
| DEGRADED | recovery | OK | Restore |
| DEGRADED | no_recovery | STALE | Escalate |
| DEGRADED | wait_for_secret | BLOCKED | Queue |
| STALE | heartbeat | OK | Restore |
| STALE | no_heartbeat | DOWN | Remove |
| DOWN | restart | RECOVERING | Monitor |
| RECOVERING | health_ok | OK | Confirm |
| RECOVERING | health_fail | DOWN | Retry |
| BLOCKED | secret_available | DEGRADED | Resume |
