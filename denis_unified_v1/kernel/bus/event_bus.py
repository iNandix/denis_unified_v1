"""
Denis Kernel - Event Bus
=========================
Async event bus with backpressure, cancellation, and priority support.
"""

from __future__ import annotations

import asyncio
import uuid
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class CommitLevel(Enum):
    TENTATIVE = "tentative"
    PROVISIONAL = "provisional"
    FINAL = "final"


class BackpressurePolicy(Enum):
    DROP_OLD = "DROP_OLD_INPUT_CHUNKS"
    COALESCE = "COALESCE_INPUT"


@dataclass
class Event:
    """Standard event envelope for Denis Kernel."""

    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    trace_id: str = ""
    session_id: str = ""
    turn_id: str = ""
    seq: int = 0
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = ""
    type: str = ""
    priority: int = 0
    ttl_ms: int = 5000
    cancel_key: str = ""
    commit_level: CommitLevel = CommitLevel.TENTATIVE
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "seq": self.seq,
            "ts": self.ts,
            "source": self.source,
            "type": self.type,
            "priority": self.priority,
            "ttl_ms": self.ttl_ms,
            "cancel_key": self.cancel_key,
            "commit_level": self.commit_level.value,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        commit_level = CommitLevel(data.get("commit_level", "tentative"))
        if isinstance(commit_level, str):
            commit_level = CommitLevel(commit_level)
        return cls(
            event_id=data.get("event_id", uuid.uuid4().hex),
            trace_id=data.get("trace_id", ""),
            session_id=data.get("session_id", ""),
            turn_id=data.get("turn_id", ""),
            seq=data.get("seq", 0),
            ts=data.get("ts", datetime.now(timezone.utc).isoformat()),
            source=data.get("source", ""),
            type=data.get("type", ""),
            priority=data.get("priority", 0),
            ttl_ms=data.get("ttl_ms", 5000),
            cancel_key=data.get("cancel_key", ""),
            commit_level=commit_level,
            payload=data.get("payload", {}),
        )


EventHandler = Callable[[Event], asyncio.coroutines]


class EventBus:
    """
    Async event bus with backpressure and cancellation.

    Features:
    - Priority-based event processing
    - Backpressure with configurable policy
    - Cancellation support via cancel_key
    - TTL for event expiry
    - Subscription by event type pattern
    """

    def __init__(
        self,
        max_queue_size: int = 1000,
        backpressure_policy: BackpressurePolicy = BackpressurePolicy.DROP_OLD,
        default_ttl_ms: int = 5000,
    ):
        self.max_queue_size = max_queue_size
        self.backpressure_policy = backpressure_policy
        self.default_ttl_ms = default_ttl_ms

        self._subscribers: Dict[str, List[EventHandler]] = {}
        self._event_queue: asyncio.PriorityQueue = asyncio.PriorityQueue(
            maxsize=max_queue_size
        )
        self._running = False
        self._processor_task: Optional[asyncio.Task] = None

        self._active_cancel_keys: Set[str] = set()
        self._event_count = 0
        self._dropped_count = 0

        logger.info(
            f"EventBus initialized: max_queue={max_queue_size}, policy={backpressure_policy.value}"
        )

    async def start(self):
        """Start the event processor."""
        if self._running:
            return
        self._running = True
        self._processor_task = asyncio.create_task(self._process_events())
        logger.info("EventBus started")

    async def stop(self):
        """Stop the event processor."""
        self._running = False
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        logger.info(
            f"EventBus stopped. Events: {self._event_count}, Dropped: {self._dropped_count}"
        )

    def subscribe(self, event_type_pattern: str, handler: EventHandler):
        """
        Subscribe to events matching the pattern.
        Supports wildcards: "nlu.*" matches "nlu.intent.hypothesis"
        """
        if event_type_pattern not in self._subscribers:
            self._subscribers[event_type_pattern] = []
        self._subscribers[event_type_pattern].append(handler)
        logger.debug(f"Subscribed to {event_type_pattern}")

    def unsubscribe(self, event_type_pattern: str, handler: EventHandler):
        """Unsubscribe a handler."""
        if event_type_pattern in self._subscribers:
            self._subscribers[event_type_pattern] = [
                h for h in self._subscribers[event_type_pattern] if h != handler
            ]

    async def emit(self, event: Event) -> bool:
        """
        Emit an event to the bus.
        Returns True if emitted, False if dropped due to backpressure.
        """
        self._event_count += 1

        try:
            if self.backpressure_policy == BackpressurePolicy.DROP_OLD:
                try:
                    # Use (priority, seq, time, event) for proper sorting
                    self._event_queue.put_nowait(
                        (event.priority, event.seq, time.time(), event)
                    )
                except asyncio.QueueFull:
                    try:
                        self._event_queue.get_nowait()
                        self._event_queue.put_nowait(
                            (event.priority, event.seq, time.time(), event)
                        )
                        self._dropped_count += 1
                    except asyncio.QueueEmpty:
                        pass
            else:
                await asyncio.wait_for(
                    self._event_queue.put(
                        (event.priority, event.seq, time.time(), event)
                    ),
                    timeout=event.ttl_ms / 1000,
                )
            return True

        except asyncio.TimeoutError:
            self._dropped_count += 1
            logger.warning(f"Event {event.type} dropped due to backpressure")
            return False
        except Exception as e:
            logger.error(f"Error emitting event: {e}")
            self._dropped_count += 1
            return False

    def emit_sync(self, event: Event) -> bool:
        """Synchronous emit for non-async contexts."""
        try:
            self._event_queue.put_nowait((event.priority, event))
            return True
        except asyncio.QueueFull:
            self._dropped_count += 1
            return False

    async def cancel(self, cancel_key: str):
        """Cancel all events with matching cancel_key."""
        self._active_cancel_keys.add(cancel_key)
        logger.debug(f"Cancelled events with key: {cancel_key}")

    async def uncancel(self, cancel_key: str):
        """Remove cancel key to allow new events."""
        self._active_cancel_keys.discard(cancel_key)

    def is_cancelled(self, cancel_key: str) -> bool:
        """Check if a cancel_key is active."""
        return cancel_key in self._active_cancel_keys

    def get_stats(self) -> Dict[str, Any]:
        """Get bus statistics."""
        return {
            "queue_size": self._event_queue.qsize(),
            "max_queue_size": self._event_queue.maxsize,
            "events_processed": self._event_count,
            "events_dropped": self._dropped_count,
            "backpressure_policy": self.backpressure_policy.value,
            "subscribers": len(self._subscribers),
            "active_cancel_keys": len(self._active_cancel_keys),
        }

    async def _process_events(self):
        """Main event processing loop."""
        while self._running:
            try:
                priority, seq, timestamp, event = await asyncio.wait_for(
                    self._event_queue.get(), timeout=1.0
                )

                if event.cancel_key and event.cancel_key in self._active_cancel_keys:
                    logger.debug(f"Skipping cancelled event: {event.event_id}")
                    continue

                if not self._check_ttl(event):
                    logger.debug(f"Event TTL expired: {event.event_id}")
                    continue

                await self._dispatch(event)

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing event: {e}")

    async def _dispatch(self, event: Event):
        """Dispatch event to matching subscribers."""
        matched = False

        for pattern, handlers in self._subscribers.items():
            if self._matches_pattern(event.type, pattern):
                matched = True
                for handler in handlers:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(event)
                        else:
                            handler(event)
                    except Exception as e:
                        logger.error(f"Error in handler for {event.type}: {e}")

        if not matched:
            logger.debug(f"No subscribers for event type: {event.type}")

    def _matches_pattern(self, event_type: str, pattern: str) -> bool:
        """Check if event_type matches pattern (supports wildcards)."""
        if pattern == "*":
            return True
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            return event_type.startswith(prefix)
        if pattern.startswith("*"):
            suffix = pattern[1:]
            return event_type.endswith(suffix)
        return event_type == pattern

    def _check_ttl(self, event: Event) -> bool:
        """Check if event has expired based on TTL."""
        try:
            event_time = datetime.fromisoformat(event.ts.replace("Z", "+00:00"))
            age_ms = (datetime.now(timezone.utc) - event_time).total_seconds() * 1000
            return age_ms < event.ttl_ms
        except Exception:
            return True


# Global event bus instance
_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get the global event bus instance."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def create_event_bus(
    max_queue_size: int = 1000,
    backpressure_policy: str = "DROP_OLD",
) -> EventBus:
    """Factory function to create a new EventBus."""
    policy = BackpressurePolicy(backpressure_policy)
    return EventBus(
        max_queue_size=max_queue_size,
        backpressure_policy=policy,
    )
