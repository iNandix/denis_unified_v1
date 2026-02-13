"""API Gateway with rate limiting and circuit breakers."""

import asyncio
import time
import hashlib
from collections import defaultdict, deque
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import os

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
import httpx


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    requests_per_minute: int = 60
    burst_limit: int = 10
    window_seconds: int = 60


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 5
    recovery_timeout: int = 60
    expected_exception: Tuple = (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError)


@dataclass
class ServiceConfig:
    """Backend service configuration."""
    name: str
    url: str
    timeout: float = 30.0
    rate_limit: RateLimitConfig = None
    circuit_breaker: CircuitBreakerConfig = None
    health_check_path: str = "/health"


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.tokens = config.requests_per_minute
        self.last_update = time.time()
        self.burst_tokens = config.burst_limit

    def allow_request(self) -> Tuple[bool, float]:
        """Check if request is allowed. Returns (allowed, wait_time)."""
        now = time.time()
        time_passed = now - self.last_update

        # Refill tokens
        tokens_to_add = time_passed * (self.config.requests_per_minute / self.config.window_seconds)
        self.tokens = min(self.config.requests_per_minute, self.tokens + tokens_to_add)

        self.last_update = now

        # Check burst limit first
        if self.burst_tokens > 0:
            self.burst_tokens -= 1
            return True, 0.0

        # Check regular tokens
        if self.tokens >= 1:
            self.tokens -= 1
            return True, 0.0

        # Calculate wait time
        wait_time = (1 - self.tokens) / (self.config.requests_per_minute / self.config.window_seconds)
        return False, wait_time


class CircuitBreaker:
    """Circuit breaker implementation."""

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "closed"  # closed, open, half-open

    def call(self, func):
        """Decorator to apply circuit breaker to function calls."""
        async def wrapper(*args, **kwargs):
            if self.state == "open":
                if time.time() - self.last_failure_time > self.config.recovery_timeout:
                    self.state = "half-open"
                else:
                    raise HTTPException(status_code=503, detail="Service temporarily unavailable")

            try:
                result = await func(*args, **kwargs)
                if self.state == "half-open":
                    self.state = "closed"
                    self.failure_count = 0
                return result
            except self.config.expected_exception as e:
                self.failure_count += 1
                self.last_failure_time = time.time()

                if self.failure_count >= self.config.failure_threshold:
                    self.state = "open"

                raise e

        return wrapper

    def get_state(self) -> Dict:
        """Get circuit breaker state information."""
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "last_failure_time": self.last_failure_time,
            "time_since_last_failure": time.time() - self.last_failure_time if self.last_failure_time else 0
        }


class APIGateway:
    """API Gateway with rate limiting and circuit breakers."""

    def __init__(self):
        self.services: Dict[str, ServiceConfig] = {}
        self.rate_limiters: Dict[str, Dict[str, RateLimiter]] = defaultdict(dict)
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.client = httpx.AsyncClient(timeout=30.0)

        # Load service configurations
        self._load_service_configs()

    def _load_service_configs(self):
        """Load service configurations from environment."""
        # Default services
        default_services = {
            "api": ServiceConfig(
                name="api",
                url=os.getenv("API_SERVICE_URL", "http://localhost:8084"),
                rate_limit=RateLimitConfig(requests_per_minute=100),
                circuit_breaker=CircuitBreakerConfig()
            ),
            "orchestrator": ServiceConfig(
                name="orchestrator",
                url=os.getenv("ORCHESTRATOR_SERVICE_URL", "http://localhost:8085"),
                rate_limit=RateLimitConfig(requests_per_minute=50),
                circuit_breaker=CircuitBreakerConfig()
            )
        }

        for name, config in default_services.items():
            self.services[name] = config
            if config.circuit_breaker:
                self.circuit_breakers[name] = CircuitBreaker(config.circuit_breaker)

    def get_rate_limiter(self, service_name: str, client_key: str) -> RateLimiter:
        """Get or create rate limiter for service and client."""
        if service_name not in self.rate_limiters:
            self.rate_limiters[service_name] = {}

        if client_key not in self.rate_limiters[service_name]:
            service_config = self.services.get(service_name)
            if service_config and service_config.rate_limit:
                self.rate_limiters[service_name][client_key] = RateLimiter(service_config.rate_limit)
            else:
                # Default rate limiter
                self.rate_limiters[service_name][client_key] = RateLimiter(RateLimitConfig())

        return self.rate_limiters[service_name][client_key]

    def get_client_key(self, request: Request) -> str:
        """Generate client key from request (IP + user agent)."""
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        key_data = f"{client_ip}:{user_agent}"
        return hashlib.md5(key_data.encode()).hexdigest()[:16]

    async def proxy_request(self, service_name: str, path: str, request: Request) -> Response:
        """Proxy request to backend service."""
        if service_name not in self.services:
            raise HTTPException(status_code=404, detail="Service not found")

        service_config = self.services[service_name]
        client_key = self.get_client_key(request)

        # Check rate limit
        rate_limiter = self.get_rate_limiter(service_name, client_key)
        allowed, wait_time = rate_limiter.allow_request()

        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Try again in {wait_time:.1f} seconds"
            )

        # Build target URL
        target_url = f"{service_config.url}{path}"
        if request.url.query:
            target_url += f"?{request.url.query}"

        # Prepare request data
        request_data = {
            "method": request.method,
            "url": target_url,
            "headers": dict(request.headers),
            "content": await request.body()
        }

        # Remove hop-by-hop headers
        hop_headers = [
            "connection", "keep-alive", "proxy-authenticate",
            "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade"
        ]
        for header in hop_headers:
            request_data["headers"].pop(header, None)

        # Apply circuit breaker
        circuit_breaker = self.circuit_breakers.get(service_name)
        if circuit_breaker:
            proxy_func = circuit_breaker.call(self._execute_request)
        else:
            proxy_func = self._execute_request

        try:
            response = await proxy_func(request_data)
            return response
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Service unavailable: {str(e)}")

    async def _execute_request(self, request_data: Dict) -> Response:
        """Execute HTTP request to backend service."""
        try:
            async with self.client.stream(**request_data) as response:
                content = await response.aread()
                return Response(
                    content=content,
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Gateway timeout")
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Service unavailable")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Gateway error: {str(e)}")

    async def get_service_health(self, service_name: str) -> Dict:
        """Get health status of a service."""
        if service_name not in self.services:
            return {"healthy": False, "reason": "service_not_configured"}

        service_config = self.services[service_name]
        circuit_breaker = self.circuit_breakers.get(service_name)

        health_info = {
            "service": service_name,
            "url": service_config.url,
            "circuit_breaker": circuit_breaker.get_state() if circuit_breaker else None,
            "rate_limiters_active": len(self.rate_limiters.get(service_name, {}))
        }

        # Try health check
        try:
            health_url = f"{service_config.url}{service_config.health_check_path}"
            async with self.client.stream("GET", health_url, timeout=5.0) as response:
                if response.status_code == 200:
                    health_info["healthy"] = True
                    health_info["response_time_ms"] = response.elapsed.total_seconds() * 1000
                else:
                    health_info["healthy"] = False
                    health_info["reason"] = f"bad_status_{response.status_code}"
        except Exception as e:
            health_info["healthy"] = False
            health_info["reason"] = str(e)

        return health_info

    async def get_gateway_stats(self) -> Dict:
        """Get gateway statistics."""
        stats = {
            "services_configured": len(self.services),
            "active_rate_limiters": sum(len(limiters) for limiters in self.rate_limiters.values()),
            "circuit_breakers": {
                name: cb.get_state() for name, cb in self.circuit_breakers.items()
            },
            "timestamp": time.time()
        }

        # Get service health
        service_health = {}
        for service_name in self.services.keys():
            service_health[service_name] = await self.get_service_health(service_name)

        stats["service_health"] = service_health
        return stats


# Global gateway instance
_gateway_instance = None

def get_api_gateway() -> APIGateway:
    """Get global API gateway instance."""
    global _gateway_instance
    if _gateway_instance is None:
        _gateway_instance = APIGateway()
    return _gateway_instance


# FastAPI app for the gateway
app = FastAPI(title="Denis API Gateway", version="1.0.0")

@app.middleware("http")
async def gateway_middleware(request: Request, call_next):
    """Gateway middleware for request processing."""
    gateway = get_api_gateway()

    # Health check endpoint
    if request.url.path == "/health":
        return JSONResponse({"status": "healthy", "gateway": "active"})

    # Gateway stats endpoint
    if request.url.path == "/gateway/stats":
        stats = await gateway.get_gateway_stats()
        return JSONResponse(stats)

    # Route to services based on path prefix
    path_parts = request.url.path.strip("/").split("/")
    if len(path_parts) >= 2:
        service_name = path_parts[0]
        if service_name in gateway.services:
            remaining_path = "/" + "/".join(path_parts[1:])
            return await gateway.proxy_request(service_name, remaining_path, request)

    # Default response for unmatched routes
    return JSONResponse(
        {"error": "Service not found", "available_services": list(gateway.services.keys())},
        status_code=404
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
