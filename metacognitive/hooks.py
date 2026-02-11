"""
Metacognitive Hooks - Instrumentación base para DENIS.

Decorators y funciones para instrumentar todas las operaciones críticas
con eventos metacognitivos a Redis.

Contratos aplicados:
- L3.META.NEVER_BLOCK
- L3.META.SELF_REFLECTION_LATENCY
- L3.META.EVENT_SOURCING
- L3.META.QUALITY_GATE
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import wraps
import json
from typing import Any, Callable
import time

import redis


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_redis() -> redis.Redis:
    url = "redis://localhost:6379/0"
    try:
        import os

        url = os.getenv("REDIS_URL", url)
        return redis.Redis.from_url(url, decode_responses=True)
    except Exception:
        return redis.Redis.from_url(url, decode_responses=True)


def _emit_event(channel: str, data: dict[str, Any]) -> bool:
    try:
        r = _get_redis()
        payload = json.dumps(
            {
                **data,
                "timestamp_utc": _utc_now(),
            },
            sort_keys=True,
        )
        r.publish(channel, payload)
        r.lpush("denis:metacognitive:events", payload)
        r.ltrim("denis:metacognitive:events", 0, 999)
        return True
    except Exception:
        return False


def _record_metric(key: str, value: float) -> bool:
    try:
        r = _get_redis()
        r.incrbyfloat(f"denis:metacognitive:metrics:{key}", value)
        return True
    except Exception:
        return False


@dataclass
class MCEvent:
    """Evento metacognitivo."""

    event_type: str
    operation: str
    status: str
    latency_ms: float
    input_hash: str
    output_hash: str | None
    quality_score: float | None
    error: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


def _hash_data(data: Any) -> str:
    import hashlib

    try:
        content = json.dumps(data, sort_keys=True, default=str)
        return hashlib.md5(content.encode()).hexdigest()[:16]
    except Exception:
        return "unknown"


class MetacognitiveHooks:
    """Gestor de hooks metacognitivos."""

    def __init__(self):
        self._enabled = True
        self._latency_budget_ms = 100.0
        self._quality_threshold = 0.7
        self._events_emitted = 0
        self._events_failed = 0
        self._total_latency_ms = 0.0

    def is_enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    def set_latency_budget(self, ms: float) -> None:
        self._latency_budget_ms = ms

    def set_quality_threshold(self, threshold: float) -> None:
        self._quality_threshold = threshold

    def get_stats(self) -> dict[str, Any]:
        avg_latency = self._total_latency_ms / max(1, self._events_emitted)
        return {
            "enabled": self._enabled,
            "latency_budget_ms": self._latency_budget_ms,
            "quality_threshold": self._quality_threshold,
            "events_emitted": self._events_emitted,
            "events_failed": self._events_failed,
            "avg_latency_ms": round(avg_latency, 2),
        }

    def emit_operation_event(
        self,
        operation: str,
        status: str,
        latency_ms: float,
        input_data: Any,
        output_data: Any | None,
        quality_score: float | None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        if not self._enabled:
            return True

        event = MCEvent(
            event_type="operation",
            operation=operation,
            status=status,
            latency_ms=latency_ms,
            input_hash=_hash_data(input_data),
            output_hash=_hash_data(output_data) if output_data else None,
            quality_score=quality_score,
            error=error,
            metadata=metadata or {},
        )

        self._total_latency_ms += latency_ms
        self._events_emitted += 1

        return _emit_event(
            "denis:metacognitive:operation",
            {
                "event_type": event.event_type,
                "operation": event.operation,
                "status": event.status,
                "latency_ms": event.latency_ms,
                "input_hash": event.input_hash,
                "output_hash": event.output_hash,
                "quality_score": event.quality_score,
                "error": event.error,
                "metadata": event.metadata,
            },
        )

    def emit_decision_event(
        self,
        decision_type: str,
        decision: str,
        confidence: float,
        alternatives: list[str],
        context: dict[str, Any] | None = None,
    ) -> bool:
        if not self._enabled:
            return True

        quality = 1.0 if confidence >= self._quality_threshold else confidence

        return _emit_event(
            "denis:metacognitive:decision",
            {
                "event_type": "decision",
                "decision_type": decision_type,
                "decision": decision,
                "confidence": confidence,
                "quality_score": quality,
                "alternatives": alternatives,
                "context": context or {},
            },
        )

    def emit_reflection_event(
        self,
        reflection_type: str,
        target: str,
        finding: str,
        confidence: float,
        recommendation: str | None = None,
    ) -> bool:
        if not self._enabled:
            return True

        return _emit_event(
            "denis:metacognitive:reflection",
            {
                "event_type": "reflection",
                "reflection_type": reflection_type,
                "target": target,
                "finding": finding,
                "confidence": confidence,
                "recommendation": recommendation,
            },
        )

    def emit_error_event(
        self,
        error_type: str,
        operation: str,
        error_message: str,
        recoverable: bool,
        suggested_action: str | None = None,
    ) -> bool:
        if not self._enabled:
            return True

        return _emit_event(
            "denis:metacognitive:error",
            {
                "event_type": "error",
                "error_type": error_type,
                "operation": operation,
                "error_message": error_message,
                "recoverable": recoverable,
                "suggested_action": suggested_action,
            },
        )


_hooks = MetacognitiveHooks()


def metacognitive_trace(
    operation_name: str | None = None,
    record_input: bool = False,
    record_output: bool = False,
    quality_evaluator: Callable[[Any], float] | None = None,
) -> Callable:
    """
    Decorator para instrumentar operaciones con eventos metacognitivos.

    Usage:
        @metacognitive_trace("my_operation")
        async def my_function(input_data):
            ...

        @metacognitive_trace(quality_evaluator=lambda r: 1.0 if r.success else 0.0)
        async def my_function(input_data):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            operation = operation_name or func.__name__
            input_hash = _hash_data(args) if record_input else "masked"
            output_data = None
            error = None
            status = "success"

            try:
                result = await func(*args, **kwargs)
                output_data = result if record_output else None
                return result
            except Exception as e:
                error = str(e)
                status = "error"
                raise
            finally:
                latency_ms = (time.time() - start_time) * 1000

                quality = None
                if quality_evaluator and output_data:
                    try:
                        quality = quality_evaluator(output_data)
                    except Exception:
                        pass

                _hooks.emit_operation_event(
                    operation=operation,
                    status=status,
                    latency_ms=latency_ms,
                    input_data=args if record_input else {},
                    output_data=output_data,
                    quality_score=quality,
                    error=error,
                )

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            operation = operation_name or func.__name__
            input_hash = _hash_data(args) if record_input else "masked"
            output_data = None
            error = None
            status = "success"

            try:
                result = func(*args, **kwargs)
                output_data = result if record_output else None
                return result
            except Exception as e:
                error = str(e)
                status = "error"
                raise
            finally:
                latency_ms = (time.time() - start_time) * 1000

                quality = None
                if quality_evaluator and output_data:
                    try:
                        quality = quality_evaluator(output_data)
                    except Exception:
                        pass

                _hooks.emit_operation_event(
                    operation=operation,
                    status=status,
                    latency_ms=latency_ms,
                    input_data=args if record_input else {},
                    output_data=output_data,
                    quality_score=quality,
                    error=error,
                )

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def get_hooks() -> MetacognitiveHooks:
    """Obtiene la instancia global de hooks."""
    return _hooks


def is_metacognitive_enabled() -> bool:
    """Check si metacognición está habilitada."""
    return _hooks.is_enabled()


def emit_decision(
    decision_type: str,
    decision: str,
    confidence: float,
    alternatives: list[str],
    context: dict[str, Any] | None = None,
) -> bool:
    """Emite un evento de decisión."""
    return _hooks.emit_decision_event(
        decision_type=decision_type,
        decision=decision,
        confidence=confidence,
        alternatives=alternatives,
        context=context,
    )


def emit_reflection(
    reflection_type: str,
    target: str,
    finding: str,
    confidence: float,
    recommendation: str | None = None,
) -> bool:
    """Emite un evento de reflexión."""
    return _hooks.emit_reflection_event(
        reflection_type=reflection_type,
        target=target,
        finding=finding,
        confidence=confidence,
        recommendation=recommendation,
    )


def emit_error(
    error_type: str,
    operation: str,
    error_message: str,
    recoverable: bool,
    suggested_action: str | None = None,
) -> bool:
    """Emite un evento de error."""
    return _hooks.emit_error_event(
        error_type=error_type,
        operation=operation,
        error_message=error_message,
        recoverable=recoverable,
        suggested_action=suggested_action,
    )


if __name__ == "__main__":
    import json

    print("=== METACOGNITIVE HOOKS ===")
    print(json.dumps(_hooks.get_stats(), indent=2))

    @metacognitive_trace("test_operation", quality_evaluator=lambda x: 1.0)
    def test_func(x):
        return {"result": x * 2}

    print("\n=== RUNNING INSTRUMENTED FUNCTION ===")
    result = test_func(21)
    print(f"Result: {result}")

    print("\n=== STATS AFTER ===")
    print(json.dumps(_hooks.get_stats(), indent=2))

    print("\n=== EMITTING DECISION ===")
    emit_decision(
        decision_type="tool_selection",
        decision="code_interpreter",
        confidence=0.85,
        alternatives=["search", "memory"],
        context={"task": "write code"},
    )

    print("\n=== EMITTING REFLECTION ===")
    emit_reflection(
        reflection_type="gap_detection",
        target="new-capability",
        finding="Missing data aggregation capability",
        confidence=0.75,
        recommendation="Consider implementing data-aggregator tool",
    )
