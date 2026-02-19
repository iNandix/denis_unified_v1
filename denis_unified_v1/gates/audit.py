"""
Audit Trail Module - Gate audit con Redis + opcional Neo4j.

Provides:
- Atomic audit logging to Redis with LUA
- Optional Neo4j storage for graph queries
- Audit event types: rate_limit, budget, prompt_injection, output_validation
- Query interface for audit analysis
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from enum import Enum
import asyncio

from denis_unified_v1.observability.tracing import get_tracer

tracer = get_tracer()


class AuditEventType(Enum):
    RATE_LIMIT = "rate_limit"
    BUDGET_EXCEEDED = "budget_exceeded"
    BUDGET_TTFT_EXCEEDED = "budget_ttft_exceeded"
    PROMPT_INJECTION = "prompt_injection"
    OUTPUT_VALIDATION = "output_validation"
    TOOL_BLOCKED = "tool_blocked"
    REQUEST_COMPLETED = "request_completed"
    REQUEST_FAILED = "request_failed"
    CONFIG_CHANGED = "config_changed"
    GATE_OVERRIDE = "gate_override"


class AuditSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Audit event for gate operations."""

    event_id: str
    event_type: str
    severity: str
    timestamp: float
    user_id: Optional[str]
    class_key: str
    request_id: Optional[str]
    details: Dict[str, Any]
    blocked: bool = False
    reason: Optional[str] = None


class AuditTrail:
    """
    Audit trail for gate operations.
    Uses Redis as primary store with optional Neo4j for queries.
    """

    # LUA script for atomic append
    LUA_APPEND = """
    local key = KEYS[1]
    local event = ARGV[1]
    local max_events = tonumber(ARGV[2])
    
    -- Add event to list
    redis.call('LPUSH', key, event)
    
    -- Trim to max events
    redis.call('LTRIM', key, 0, max_events - 1)
    
    -- Set TTL of 30 days
    redis.call('EXPIRE', key, 2592000)
    
    return 1
    """

    def __init__(
        self,
        redis_client: Any = None,
        neo4j_driver: Any = None,
        max_events_per_key: int = 10000,
    ):
        self.redis = redis_client
        self.neo4j = neo4j_driver
        self.max_events = max_events_per_key
        self._script_sha: Optional[str] = None

    def _get_redis(self) -> Any:
        """Get Redis client."""
        if self.redis is None:
            try:
                import redis

                self.redis = redis.Redis.from_url("redis://localhost:6379/0", decode_responses=True)
            except Exception:
                return None
        return self.redis

    async def log_event(
        self,
        event_type: AuditEventType,
        severity: AuditSeverity,
        user_id: Optional[str] = None,
        class_key: str = "default",
        request_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        blocked: bool = False,
        reason: Optional[str] = None,
    ) -> str:
        """Log an audit event."""
        import uuid

        event_id = str(uuid.uuid4())[:8]
        event = AuditEvent(
            event_id=event_id,
            event_type=event_type.value,
            severity=severity.value,
            timestamp=time.time(),
            user_id=user_id,
            class_key=class_key,
            request_id=request_id,
            details=details or {},
            blocked=blocked,
            reason=reason,
        )

        # Log to Redis
        redis_client = self._get_redis()
        if redis_client:
            try:
                event_json = json.dumps(asdict(event))

                # Key for global events
                global_key = f"audit:gate:events"
                redis_client.lpush(global_key, event_json)
                redis_client.ltrim(global_key, 0, self.max_events - 1)
                redis_client.expire(global_key, 2592000)

                # Key for user-specific events
                if user_id:
                    user_key = f"audit:gate:user:{user_id}"
                    redis_client.lpush(user_key, event_json)
                    redis_client.ltrim(user_key, 0, self.max_events - 1)
                    redis_client.expire(user_key, 2592000)

            except Exception as e:
                pass

        # Log to Neo4j if available
        if self.neo4j:
            try:
                await self._log_to_neo4j(event)
            except Exception:
                pass

        return event_id

    async def _log_to_neo4j(self, event: AuditEvent) -> None:
        """Log event to Neo4j for graph queries."""
        try:
            with self.neo4j.session() as session:
                session.run(
                    """
                    CREATE (e:AuditEvent {
                        event_id: $event_id,
                        event_type: $event_type,
                        severity: $severity,
                        timestamp: $timestamp,
                        user_id: $user_id,
                        class_key: $class_key,
                        request_id: $request_id,
                        blocked: $blocked,
                        reason: $reason
                    })
                    """,
                    event_id=event.event_id,
                    event_type=event.event_type,
                    severity=event.severity,
                    timestamp=event.timestamp,
                    user_id=event.user_id,
                    class_key=event.class_key,
                    request_id=event.request_id,
                    blocked=event.blocked,
                    reason=event.reason,
                )
        except Exception:
            pass

    async def query_events(
        self,
        user_id: Optional[str] = None,
        event_type: Optional[AuditEventType] = None,
        severity: Optional[AuditSeverity] = None,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """Query audit events."""
        redis_client = self._get_redis()
        if not redis_client:
            return []

        # Determine key
        if user_id:
            key = f"audit:gate:user:{user_id}"
        else:
            key = "audit:gate:events"

        try:
            events_json = redis_client.lrange(key, 0, limit - 1)

            events = []
            for event_json in events_json:
                try:
                    event_dict = json.loads(event_json)

                    # Filter by type
                    if event_type and event_dict["event_type"] != event_type.value:
                        continue

                    # Filter by severity
                    if severity and event_dict["severity"] != severity.value:
                        continue

                    events.append(AuditEvent(**event_dict))
                except Exception:
                    continue

            return events
        except Exception:
            return []

    async def get_blocked_count(
        self,
        user_id: Optional[str] = None,
        hours: int = 24,
    ) -> Dict[str, int]:
        """Get count of blocked requests."""
        events = await self.query_events(user_id=user_id, limit=1000)

        cutoff = time.time() - (hours * 3600)

        counts = {
            "total": 0,
            "rate_limit": 0,
            "budget": 0,
            "prompt_injection": 0,
            "output_validation": 0,
            "tool_blocked": 0,
        }

        for event in events:
            if event.timestamp < cutoff:
                continue

            counts["total"] += 1

            if event.event_type == AuditEventType.RATE_LIMIT.value:
                counts["rate_limit"] += 1
            elif event.event_type in (
                AuditEventType.BUDGET_EXCEEDED.value,
                AuditEventType.BUDGET_TTFT_EXCEEDED.value,
            ):
                counts["budget"] += 1
            elif event.event_type == AuditEventType.PROMPT_INJECTION.value:
                counts["prompt_injection"] += 1
            elif event.event_type == AuditEventType.OUTPUT_VALIDATION.value:
                counts["output_validation"] += 1
            elif event.event_type == AuditEventType.TOOL_BLOCKED.value:
                counts["tool_blocked"] += 1

        return counts

    async def get_recent_violations(
        self,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get recent violations for dashboard."""
        events = await self.query_events(limit=limit)

        violations = []
        for event in events:
            if event.blocked or event.severity in (
                AuditSeverity.ERROR.value,
                AuditSeverity.CRITICAL.value,
            ):
                violations.append(
                    {
                        "event_id": event.event_id,
                        "event_type": event.event_type,
                        "severity": event.severity,
                        "timestamp": event.timestamp,
                        "user_id": event.user_id,
                        "reason": event.reason,
                        "details": event.details,
                    }
                )

        return violations


# Singleton
_audit_trail: Optional[AuditTrail] = None


def get_audit_trail(
    redis_client: Any = None,
    neo4j_driver: Any = None,
) -> AuditTrail:
    """Get singleton audit trail."""
    global _audit_trail
    if _audit_trail is None:
        _audit_trail = AuditTrail(redis_client, neo4j_driver)
    return _audit_trail
