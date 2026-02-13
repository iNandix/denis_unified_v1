"""
Budgets Module for Denis Unified V1.

Manages total budgets (e.g., tokens per user per period) and TTFT (Time to First Token) with real task cancellation for streaming and non-streaming requests.

Uses Redis for atomic budget tracking, with fallback to in-memory.

Metrics: denis_budget_ttft_cancellations_total, denis_budget_total_exceeded_total, denis_budget_checks_total

Spans: budget_check_total, budget_check_ttft
"""
import asyncio
import time
from typing import Optional, Dict
from collections import defaultdict
import redis.asyncio as redis
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from prometheus_client import Counter, Histogram

# Prometheus metrics
budget_ttft_cancellations = Counter('denis_budget_ttft_cancellations_total', 'TTFT cancellations', ['user'])
budget_total_exceeded = Counter('denis_budget_total_exceeded_total', 'Total budget exceeded', ['user'])
budget_checks = Counter('denis_budget_checks_total', 'Budget checks', ['type', 'user'])

# OTel tracer
tracer = trace.get_tracer(__name__)

class BudgetManager:
    def __init__(self, redis_url: str = "redis://localhost:6379", max_tokens_per_minute: int = 1000, ttft_timeout_seconds: float = 5.0):
        self.redis_url = redis_url
        self.max_tokens_per_minute = max_tokens_per_minute
        self.ttft_timeout_seconds = ttft_timeout_seconds
        self.redis_client: Optional[redis.Redis] = None
        self.fallback_store: Dict[str, Dict[str, float]] = defaultdict(dict)  # user -> {timestamp: tokens}

    async def initialize(self):
        """Initialize Redis connection."""
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            await self.redis_client.ping()
        except Exception:
            self.redis_client = None

    async def check_total_budget(self, user: str, tokens_requested: int) -> bool:
        """Check if user has budget for tokens. Returns True if allowed."""
        with tracer.start_as_current_span("budget_check_total", attributes={"user": user, "tokens_requested": tokens_requested}) as span:
            try:
                if self.redis_client:
                    # Use Redis atomic increment
                    current = await self.redis_client.incrby(f"budget:{user}:tokens", tokens_requested)
                    # Reset if expired (simple fixed window)
                    if current == tokens_requested:  # First request
                        await self.redis_client.expire(f"budget:{user}:tokens", 60)
                    allowed = current <= self.max_tokens_per_minute
                else:
                    # Fallback in-memory
                    allowed = self._check_total_fallback(user, tokens_requested)

                budget_checks.labels(type="total", user=user).inc()
                if not allowed:
                    budget_total_exceeded.labels(user=user).inc()
                    span.set_attribute("budget.allowed", False)
                    span.set_status(Status(StatusCode.ERROR, "Total budget exceeded"))
                else:
                    span.set_attribute("budget.allowed", True)
                return allowed
            except Exception as e:
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                return False  # Deny on error

    def _check_total_fallback(self, user: str, tokens_requested: int) -> bool:
        """In-memory fallback for total budget."""
        now = time.time()
        user_data = self.fallback_store[user]
        # Clean expired (last minute)
        expired = [k for k, v in user_data.items() if now - float(k) > 60]
        for k in expired:
            del user_data[k]

        current_tokens = sum(user_data.values())
        if current_tokens + tokens_requested <= self.max_tokens_per_minute:
            user_data[str(now)] = tokens_requested
            return True
        return False

    async def enforce_ttft(self, user: str, task: asyncio.Task, first_yield_event: asyncio.Event) -> None:
        """Enforce TTFT by cancelling task if first yield doesn't happen in time."""
        with tracer.start_as_current_span("budget_check_ttft", attributes={"user": user}) as span:
            try:
                await asyncio.wait_for(first_yield_event.wait(), timeout=self.ttft_timeout_seconds)
                # First yield happened in time
                span.set_attribute("ttft.ok", True)
            except asyncio.TimeoutError:
                # Timeout, cancel the task
                task.cancel()
                budget_ttft_cancellations.labels(user=user).inc()
                span.set_attribute("ttft.ok", False)
                span.set_status(Status(StatusCode.ERROR, "TTFT timeout"))
            except Exception as e:
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))

    async def close(self):
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()
