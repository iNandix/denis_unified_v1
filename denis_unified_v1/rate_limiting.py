"""
Rate Limiting Module for Denis Unified V1.

Implements Redis-first rate limiting with atomic LUA scripts, with in-memory TTL fallback.
Supports fixed window rate limiting per client IP or user.

Metrics: denis_rate_limit_hits_total, denis_rate_limit_blocks_total, denis_rate_limit_latency_seconds

Spans: rate_limit_check
"""
import asyncio
import time
from typing import Dict, Optional
from collections import defaultdict
import redis.asyncio as redis
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from prometheus_client import Counter, Histogram

# Prometheus metrics
rate_limit_hits = Counter('denis_rate_limit_hits_total', 'Rate limit hits', ['client'])
rate_limit_blocks = Counter('denis_rate_limit_blocks_total', 'Rate limit blocks', ['client'])
rate_limit_latency = Histogram('denis_rate_limit_latency_seconds', 'Rate limit check latency', ['client'])

# OTel tracer
tracer = trace.get_tracer(__name__)

# LUA script for fixed window rate limiting
RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local current = redis.call('INCR', key)
if current == 1 then
    redis.call('EXPIRE', key, window)
end
if current > limit then
    return 0
else
    return 1
end
"""

class RateLimiter:
    def __init__(self, redis_url: str = "redis://localhost:6379", limit: int = 100, window: int = 60):
        self.redis_url = redis_url
        self.limit = limit
        self.window = window
        self.redis_client: Optional[redis.Redis] = None
        self.lua_script = None
        self.fallback_store: Dict[str, Dict[str, float]] = defaultdict(dict)  # client -> {timestamp: count}

    async def initialize(self):
        """Initialize Redis connection and load LUA script."""
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            await self.redis_client.ping()
            self.lua_script = await self.redis_client.script_load(RATE_LIMIT_SCRIPT)
        except Exception:
            self.redis_client = None  # Use fallback

    async def is_allowed(self, client: str) -> bool:
        """Check if client is within rate limit. Returns True if allowed, False if blocked."""
        with tracer.start_as_current_span("rate_limit_check", attributes={"client": client}) as span:
            start_time = time.time()
            try:
                if self.redis_client:
                    # Use Redis LUA script
                    result = await self.redis_client.evalsha(
                        self.lua_script,
                        keys=[f"rate_limit:{client}"],
                        args=[self.limit, self.window]
                    )
                    allowed = result == 1
                else:
                    # Fallback to in-memory with TTL
                    allowed = self._check_fallback(client)

                latency = time.time() - start_time
                rate_limit_latency.labels(client=client).observe(latency)

                if allowed:
                    rate_limit_hits.labels(client=client).inc()
                    span.set_attribute("rate_limit.allowed", True)
                else:
                    rate_limit_blocks.labels(client=client).inc()
                    span.set_attribute("rate_limit.allowed", False)
                    span.set_status(Status(StatusCode.ERROR, "Rate limit exceeded"))

                return allowed
            except Exception as e:
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                # On error, allow (fail-open)
                rate_limit_hits.labels(client=client).inc()
                return True

    def _check_fallback(self, client: str) -> bool:
        """In-memory fallback with TTL."""
        now = time.time()
        client_data = self.fallback_store[client]
        # Clean expired entries
        expired = [k for k, v in client_data.items() if now - v > self.window]
        for k in expired:
            del client_data[k]

        current_count = len(client_data)
        if current_count < self.limit:
            client_data[str(now)] = now
            return True
        return False

    async def close(self):
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()
