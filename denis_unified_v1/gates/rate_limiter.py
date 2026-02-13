"""
Rate Limiting Module - Redis-first con LUA atomic script + fallback in-memory.

Provides:
- Token bucket algorithm with Redis + LUA for atomic operations
- Fallback in-memory TTL-based rate limiter when Redis unavailable
- Per-user and per-class-key rate limiting
- Sliding window support
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple
from enum import Enum
import threading

from denis_unified_v1.observability.metrics import (
    denis_gate_rate_limited_total,
    denis_gate_rate_limit_redis_errors,
)
from denis_unified_v1.observability.tracing import get_tracer

tracer = get_tracer()


class RateLimitScope(Enum):
    USER = "user"
    CLASS_KEY = "class_key"
    IP = "ip"
    GLOBAL = "global"


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""

    requests_per_second: float = 10.0
    burst_size: int = 20
    window_seconds: float = 1.0
    scope: RateLimitScope = RateLimitScope.USER


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""

    allowed: bool
    remaining: int
    reset_time: float
    scope: str
    limit: int


class RedisRateLimiter:
    """
    Redis-first rate limiter using token bucket algorithm.
    Uses LUA script for atomic operations.
    """

    # LUA script for atomic token bucket
    LUA_SCRIPT = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local capacity = tonumber(ARGV[2])
    local refill_rate = tonumber(ARGV[3])
    local last_refill = tonumber(redis.call('GET', key .. ':last') or '0')
    local tokens = tonumber(redis.call('GET', key .. ':tokens') or capacity)
    
    -- Calculate tokens to add based on time passed
    local elapsed = now - last_refill
    local to_add = elapsed * refill_rate
    
    -- Refill tokens
    tokens = math.min(capacity, tokens + to_add)
    
    -- Check if we can consume
    local allowed = 0
    local remaining = 0
    
    if tokens >= 1 then
        allowed = 1
        tokens = tokens - 1
        remaining = math.floor(tokens)
    else
        remaining = 0
    end
    
    -- Save state atomically
    redis.call('SET', key .. ':tokens', tokens, 'EX', 3600)
    redis.call('SET', key .. ':last', now, 'EX', 3600)
    
    return {allowed, remaining, now + (1 / refill_rate)}
    """

    def __init__(
        self,
        redis_client: Any = None,
        config: RateLimitConfig = None,
    ):
        self.redis = redis_client
        self.config = config or RateLimitConfig()
        self._script_sha: Optional[str] = None
        self._lock = threading.Lock()

    def _get_redis(self) -> Any:
        """Get Redis client, lazily loaded."""
        if self.redis is None:
            try:
                import redis

                self.redis = redis.Redis.from_url(
                    "redis://localhost:6379/0", decode_responses=True
                )
            except Exception:
                return None
        return self.redis

    async def check_rate_limit(
        self,
        scope_key: str,
        scope: RateLimitScope = RateLimitScope.USER,
    ) -> RateLimitResult:
        """
        Check if request is allowed under rate limit.
        Returns (allowed, remaining, reset_time).
        """
        with tracer.start_as_current_span("rate_limiter.check") as span:
            span.set_attribute("scope_key", scope_key)
            span.set_attribute("scope", scope.value)

            redis_client = self._get_redis()

            if redis_client is not None:
                try:
                    return await self._check_redis(redis_client, scope_key, scope)
                except Exception as e:
                    span.record_exception(e)
                    denis_gate_rate_limit_redis_errors.inc()

            # Fallback to in-memory
            return self._check_in_memory(scope_key, scope)

    async def _check_redis(
        self,
        redis_client: Any,
        scope_key: str,
        scope: RateLimitScope,
    ) -> RateLimitResult:
        """Check rate limit using Redis with LUA script."""
        now = time.time()
        key = f"ratelimit:{scope.value}:{scope_key}"

        capacity = self.config.burst_size
        refill_rate = self.config.requests_per_second

        try:
            if self._script_sha is None:
                self._script_sha = redis_client.script_load(self.LUA_SCRIPT)

            result = redis_client.evalsha(
                self._script_sha,
                1,
                key,
                now,
                capacity,
                refill_rate,
            )

            allowed = bool(result[0])
            remaining = int(result[1])
            reset_time = float(result[2])

            if not allowed:
                denis_gate_rate_limited_total.labels(scope=scope.value).inc()

            return RateLimitResult(
                allowed=allowed,
                remaining=remaining,
                reset_time=reset_time,
                scope=scope_key,
                limit=capacity,
            )
        except Exception as e:
            raise

    def _check_in_memory(
        self,
        scope_key: str,
        scope: RateLimitScope,
    ) -> RateLimitResult:
        """Fallback in-memory rate limiter with TTL."""
        key = f"{scope.value}:{scope_key}"
        now = time.time()

        with self._lock:
            if not hasattr(self, "_memory_store"):
                self._memory_store: Dict[str, Dict[str, Any]] = {}

            if key not in self._memory_store:
                self._memory_store[key] = {
                    "tokens": float(self.config.burst_size),
                    "last_update": now,
                }

            state = self._memory_store[key]
            elapsed = now - state["last_update"]

            # Refill tokens
            tokens_to_add = elapsed * self.config.requests_per_second
            state["tokens"] = min(
                self.config.burst_size, state["tokens"] + tokens_to_add
            )
            state["last_update"] = now

            # Check if allowed
            if state["tokens"] >= 1:
                state["tokens"] -= 1
                allowed = True
                remaining = int(state["tokens"])
            else:
                allowed = False
                remaining = 0

            if not allowed:
                denis_gate_rate_limited_total.labels(scope=scope.value).inc()

            reset_time = (
                now + (1 / self.config.requests_per_second)
                if not allowed
                else now + (state["tokens"] / self.config.requests_per_second)
            )

            return RateLimitResult(
                allowed=allowed,
                remaining=remaining,
                reset_time=reset_time,
                scope=scope_key,
                limit=self.config.burst_size,
            )

    async def reset(
        self, scope_key: str, scope: RateLimitScope = RateLimitScope.USER
    ) -> None:
        """Reset rate limit for a specific key."""
        key = f"{scope.value}:{scope_key}"

        redis_client = self._get_redis()
        if redis_client:
            try:
                redis_client.delete(f"{key}:tokens", f"{key}:last")
            except Exception:
                pass

        if hasattr(self, "_memory_store"):
            with self._lock:
                self._memory_store.pop(key, None)


class SlidingWindowRateLimiter:
    """
    Sliding window rate limiter for more precise rate limiting.
    Uses Redis sorted sets for accurate window tracking.
    """

    LUA_SLIDING_WINDOW = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local window = tonumber(ARGV[2])
    local limit = tonumber(ARGV[3])
    
    -- Remove old entries
    redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
    
    -- Count current requests
    local count = redis.call('ZCARD', key)
    
    if count < limit then
        -- Add new request
        redis.call('ZADD', key, now, now .. '-' .. math.random())
        redis.call('EXPIRE', key, window + 1)
        return {1, limit - count - 1, now + window}
    else
        -- Rate limited
        return {0, 0, now + (redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')[2] or now) - now + window}
    end
    """

    def __init__(
        self,
        redis_client: Any = None,
        window_seconds: float = 60.0,
        max_requests: int = 100,
    ):
        self.redis = redis_client
        self.window_seconds = window_seconds
        self.max_requests = max_requests
        self._script_sha: Optional[str] = None

    async def check(
        self,
        identifier: str,
        window: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> RateLimitResult:
        """Check sliding window rate limit."""
        window = window or self.window_seconds
        limit = limit or self.max_requests

        try:
            import redis

            if self.redis is None:
                self.redis = redis.Redis.from_url(
                    "redis://localhost:6379/0", decode_responses=True
                )

            now = time.time()
            key = f"sliding_ratelimit:{identifier}"

            if self._script_sha is None:
                self._script_sha = self.redis.script_load(self.LUA_SLIDING_WINDOW)

            result = self.redis.evalsha(
                self._script_sha,
                1,
                key,
                now,
                window,
                limit,
            )

            allowed = bool(result[0])
            remaining = int(result[1])
            reset_time = float(result[2])

            if not allowed:
                denis_gate_rate_limited_total.labels(scope="sliding").inc()

            return RateLimitResult(
                allowed=allowed,
                remaining=remaining,
                reset_time=reset_time,
                scope=identifier,
                limit=limit,
            )
        except Exception:
            # Fallback - allow
            return RateLimitResult(
                allowed=True,
                remaining=limit - 1,
                reset_time=time.time() + window,
                scope=identifier,
                limit=limit,
            )


class RateLimiterManager:
    """
    Central manager for all rate limiters.
    Supports multiple scopes and configurations.
    """

    def __init__(self, redis_client: Any = None):
        self.redis = redis_client
        self._limiters: Dict[RateLimitScope, RedisRateLimiter] = {}
        self._sliding_limiter: Optional[SlidingWindowRateLimiter] = None

        # Default configurations per scope
        self._configs: Dict[RateLimitScope, RateLimitConfig] = {
            RateLimitScope.USER: RateLimitConfig(
                requests_per_second=10.0,
                burst_size=20,
                scope=RateLimitScope.USER,
            ),
            RateLimitScope.CLASS_KEY: RateLimitConfig(
                requests_per_second=50.0,
                burst_size=100,
                scope=RateLimitScope.CLASS_KEY,
            ),
            RateLimitScope.IP: RateLimitConfig(
                requests_per_second=5.0,
                burst_size=10,
                scope=RateLimitScope.IP,
            ),
            RateLimitScope.GLOBAL: RateLimitConfig(
                requests_per_second=100.0,
                burst_size=200,
                scope=RateLimitScope.GLOBAL,
            ),
        }

    def get_limiter(self, scope: RateLimitScope) -> RedisRateLimiter:
        """Get or create rate limiter for scope."""
        if scope not in self._limiters:
            config = self._configs.get(scope, RateLimitConfig())
            self._limiters[scope] = RedisRateLimiter(
                redis_client=self.redis,
                config=config,
            )
        return self._limiters[scope]

    def get_sliding_limiter(self) -> SlidingWindowRateLimiter:
        """Get sliding window rate limiter."""
        if self._sliding_limiter is None:
            self._sliding_limiter = SlidingWindowRateLimiter(
                redis_client=self.redis,
                window_seconds=60.0,
                max_requests=100,
            )
        return self._sliding_limiter

    def configure_scope(
        self,
        scope: RateLimitScope,
        rps: float,
        burst: int,
    ) -> None:
        """Configure rate limit for a specific scope."""
        self._configs[scope] = RateLimitConfig(
            requests_per_second=rps,
            burst_size=burst,
            scope=scope,
        )
        # Reset limiter to apply new config
        self._limiters.pop(scope, None)

    async def check_all(
        self,
        user_id: Optional[str] = None,
        class_key: Optional[str] = None,
        ip: Optional[str] = None,
    ) -> Tuple[bool, Dict[str, RateLimitResult]]:
        """
        Check rate limits across all scopes.
        Returns (overall_allowed, details).
        """
        results = {}
        overall_allowed = True

        if user_id:
            result = await self.get_limiter(RateLimitScope.USER).check_rate_limit(
                user_id, RateLimitScope.USER
            )
            results["user"] = result
            if not result.allowed:
                overall_allowed = False

        if class_key:
            result = await self.get_limiter(RateLimitScope.CLASS_KEY).check_rate_limit(
                class_key, RateLimitScope.CLASS_KEY
            )
            results["class_key"] = result
            if not result.allowed:
                overall_allowed = False

        if ip:
            result = await self.get_limiter(RateLimitScope.IP).check_rate_limit(
                ip, RateLimitScope.IP
            )
            results["ip"] = result
            if not result.allowed:
                overall_allowed = False

        # Global check
        result = await self.get_limiter(RateLimitScope.GLOBAL).check_rate_limit(
            "global", RateLimitScope.GLOBAL
        )
        results["global"] = result
        if not result.allowed:
            overall_allowed = False

        return overall_allowed, results


# Singleton instance
_rate_limiter_manager: Optional[RateLimiterManager] = None


def get_rate_limiter_manager(redis_client: Any = None) -> RateLimiterManager:
    """Get singleton rate limiter manager."""
    global _rate_limiter_manager
    if _rate_limiter_manager is None:
        _rate_limiter_manager = RateLimiterManager(redis_client)
    return _rate_limiter_manager
