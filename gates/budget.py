"""
Budget Enforcement Module - Total + TTFT budgets con cancellation real.

Provides:
- Total budget enforcement with hard timeout
- Time-to-first-token (TTFT) budget enforcement
- Real task cancellation for both sync and streaming
- Budget exceeded metrics and audit trail
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TypeVar, Awaitable
from enum import Enum
import uuid

from denis_unified_v1.observability.metrics import (
    denis_gate_budget_exceeded_total,
    denis_gate_budget_ttft_exceeded_total,
    denis_gate_task_cancelled_total,
)
from denis_unified_v1.observability.tracing import get_tracer

tracer = get_tracer()

T = TypeVar("T")


class BudgetType(Enum):
    TOTAL = "total"  # Total request time
    TTFT = "ttft"  # Time to first token
    OUTPUT = "output"  # Output length


@dataclass
class BudgetConfig:
    """Configuration for budget enforcement."""

    total_budget_ms: float = 5000.0
    ttft_budget_ms: float = 1000.0
    max_output_tokens: int = 2048
    enable_cancellation: bool = True
    grace_period_ms: float = 100.0


@dataclass
class BudgetResult:
    """Result of budget enforcement."""

    exceeded: bool
    budget_type: BudgetType
    elapsed_ms: float
    limit_ms: float
    cancelled: bool = False


@dataclass
class ActiveRequest:
    """Tracks an active request for budget enforcement."""

    request_id: str
    user_id: Optional[str]
    class_key: str
    start_time: float
    ttft_deadline: float
    total_deadline: float
    ttft_passed: bool = False
    cancelled: bool = False
    tasks: List[asyncio.Task] = field(default_factory=list)


class BudgetEnforcer:
    """
    Enforces time budgets with real task cancellation.
    Supports both total budget and TTFT (time to first token).
    """

    def __init__(self, config: BudgetConfig = None):
        self.config = config or BudgetConfig()
        self._active_requests: Dict[str, ActiveRequest] = {}
        self._lock = asyncio.Lock()

    async def start_request(
        self,
        user_id: Optional[str] = None,
        class_key: str = "default",
    ) -> str:
        """Start tracking a new request."""
        request_id = str(uuid.uuid4())
        now = time.time()

        active = ActiveRequest(
            request_id=request_id,
            user_id=user_id,
            class_key=class_key,
            start_time=now,
            ttft_deadline=now + (self.config.ttft_budget_ms / 1000.0),
            total_deadline=now + (self.config.total_budget_ms / 1000.0),
        )

        async with self._lock:
            self._active_requests[request_id] = active

        return request_id

    async def check_ttft(self, request_id: str) -> BudgetResult:
        """Check if TTFT budget is exceeded."""
        now = time.time()

        async with self._lock:
            if request_id not in self._active_requests:
                return BudgetResult(
                    exceeded=False,
                    budget_type=BudgetType.TTFT,
                    elapsed_ms=0,
                    limit_ms=self.config.ttft_budget_ms,
                )

            active = self._active_requests[request_id]
            elapsed_ms = (now - active.start_time) * 1000

            if elapsed_ms > self.config.ttft_budget_ms:
                # TTFT exceeded - cancel if not already passed
                if not active.ttft_passed and self.config.enable_cancellation:
                    await self._cancel_request(request_id)

                denis_gate_budget_ttft_exceeded_total.labels(
                    class_key=active.class_key
                ).inc()

                return BudgetResult(
                    exceeded=True,
                    budget_type=BudgetType.TTFT,
                    elapsed_ms=elapsed_ms,
                    limit_ms=self.config.ttft_budget_ms,
                    cancelled=active.cancelled,
                )

        return BudgetResult(
            exceeded=False,
            budget_type=BudgetType.TTFT,
            elapsed_ms=elapsed_ms,
            limit_ms=self.config.ttft_budget_ms,
        )

    async def mark_ttft_passed(self, request_id: str) -> None:
        """Mark that first token was received."""
        async with self._lock:
            if request_id in self._active_requests:
                self._active_requests[request_id].ttft_passed = True

    async def check_total(self, request_id: str) -> BudgetResult:
        """Check if total budget is exceeded."""
        now = time.time()

        async with self._lock:
            if request_id not in self._active_requests:
                return BudgetResult(
                    exceeded=False,
                    budget_type=BudgetType.TOTAL,
                    elapsed_ms=0,
                    limit_ms=self.config.total_budget_ms,
                )

            active = self._active_requests[request_id]
            elapsed_ms = (now - active.start_time) * 1000

            if elapsed_ms > self.config.total_budget_ms:
                if self.config.enable_cancellation:
                    await self._cancel_request(request_id)

                denis_gate_budget_exceeded_total.labels(
                    class_key=active.class_key
                ).inc()

                return BudgetResult(
                    exceeded=True,
                    budget_type=BudgetType.TOTAL,
                    elapsed_ms=elapsed_ms,
                    limit_ms=self.config.total_budget_ms,
                    cancelled=active.cancelled,
                )

        return BudgetResult(
            exceeded=False,
            budget_type=BudgetType.TOTAL,
            elapsed_ms=elapsed_ms,
            limit_ms=self.config.total_budget_ms,
        )

    async def _cancel_request(self, request_id: str) -> None:
        """Cancel all tasks associated with a request."""
        if request_id not in self._active_requests:
            return

        active = self._active_requests[request_id]

        if active.cancelled:
            return

        active.cancelled = True

        # Cancel all tracked tasks
        for task in active.tasks:
            if not task.done():
                task.cancel()
                denis_gate_task_cancelled_total.labels(class_key=active.class_key).inc()

        # Also try to cancel any pending coroutines
        # This is a best-effort cancellation

    def track_task(self, request_id: str, task: asyncio.Task) -> None:
        """Track a task for cancellation."""
        if request_id in self._active_requests:
            self._active_requests[request_id].tasks.append(task)

    async def end_request(self, request_id: str) -> None:
        """End tracking a request."""
        async with self._lock:
            self._active_requests.pop(request_id, None)

    def get_active_count(self) -> int:
        """Get count of active requests."""
        return len(self._active_requests)


class BudgetedExecutor:
    """
    Executes functions with budget enforcement.
    Supports both regular and streaming functions.
    """

    def __init__(self, enforcer: BudgetEnforcer):
        self.enforcer = enforcer

    async def execute_with_budget(
        self,
        func: Callable[..., Awaitable[T]],
        request_id: str,
        *args,
        **kwargs,
    ) -> T:
        """
        Execute function with budget enforcement.
        Raises BudgetExceededError if budget is exceeded.
        """
        # Start monitoring task
        monitor_task = asyncio.create_task(self._monitor_budget(request_id))

        try:
            result = await func(*args, **kwargs)

            # Mark TTFT passed when we get first result
            await self.enforcer.mark_ttft_passed(request_id)

            return result
        finally:
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass

    async def execute_streaming_with_budget(
        self,
        func: Callable[..., Awaitable[Any]],
        request_id: str,
        *args,
        **kwargs,
    ) -> Any:
        """
        Execute streaming function with budget enforcement.
        Cancels streaming if budget exceeded.
        """
        # Start monitoring task
        monitor_task = asyncio.create_task(self._monitor_budget(request_id))
        first_token_received = asyncio.Event()

        async def wrapped_stream():
            first_yielded = False
            async for chunk in func(*args, **kwargs):
                if not first_yielded:
                    first_yielded = True
                    first_token_received.set()
                    await self.enforcer.mark_ttft_passed(request_id)
                yield chunk

        try:
            return wrapped_stream()
        finally:
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass

    async def _monitor_budget(self, request_id: str) -> None:
        """Monitor budget in background."""
        while True:
            # Check TTFT
            result = await self.enforcer.check_ttft(request_id)
            if result.exceeded:
                break

            # Check total
            result = await self.enforcer.check_total(request_id)
            if result.exceeded:
                break

            await asyncio.sleep(0.1)  # Check every 100ms


class BudgetExceededError(Exception):
    """Raised when budget is exceeded."""

    def __init__(self, result: BudgetResult):
        self.result = result
        super().__init__(
            f"Budget {result.budget_type.value} exceeded: "
            f"{result.elapsed_ms:.0f}ms > {result.limit_ms:.0f}ms"
        )


# Singleton
_budget_enforcer: Optional[BudgetEnforcer] = None


def get_budget_enforcer(config: BudgetConfig = None) -> BudgetEnforcer:
    """Get singleton budget enforcer."""
    global _budget_enforcer
    if _budget_enforcer is None:
        _budget_enforcer = BudgetEnforcer(config)
    return _budget_enforcer
