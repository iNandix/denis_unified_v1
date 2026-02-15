"""
Denis Kernel - Infrastructure Module
====================================
Provides Redis, Celery, and Service Directory integration.

Roles:
- Porthos (Redis): State, sessions, skill registry, locks, cache
- Athos (Celery): Job execution
- D'Artagnan (Tailscale): Service discovery
"""

from __future__ import annotations

import json
import os
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# PORTHOS - Redis Integration
# ============================================================================


class RedisKeys:
    """Redis key patterns."""

    SESSION = "denis:session:{session_id}"
    SESSION_HISTORY = "denis:session:{session_id}:history"
    SESSION_CONTEXT = "denis:session:{session_id}:context"
    SKILL = "denis:skill:{skill_id}"
    LOCK = "denis:lock:{resource}"
    CACHE = "denis:cache:{key}"
    JOB_STATE = "denis:job:{job_id}"
    METRICS = "denis:metrics:{key}"
    IDE_STATE = "denis:ide:{session_id}:state"


class SkillState(Enum):
    """Skill autonomy states."""

    LEARNING = "learning"  # Needs approval always
    SANDBOX = "sandbox"  # Needs confirmation
    MASTERED = "mastered"  # Can act autonomously
    RESTRICTED = "restricted"  # Blocked


@dataclass
class SkillRegistryEntry:
    """Entry in the skill registry."""

    skill_id: str
    state: SkillState = SkillState.LEARNING
    success_count: int = 0
    failure_count: int = 0
    last_success_ts: Optional[str] = None
    risk_scope: str = "default"
    requires_approval: bool = True


class Porthos:
    """
    Redis-backed state manager.

    Provides:
    - Session management
    - Skill registry + autonomy tracking
    - Distributed locks
    - Cache
    - Job state
    """

    def __init__(self, redis_client=None):
        self.redis = redis_client

    # Session methods
    async def get_session_context(self, session_id: str) -> Dict[str, Any]:
        """Get session context."""
        if not self.redis:
            return {}
        key = RedisKeys.SESSION_CONTEXT.format(session_id=session_id)
        data = await self.redis.get(key)
        return json.loads(data) if data else {}

    async def set_session_context(
        self, session_id: str, context: Dict[str, Any], ttl: int = 3600
    ):
        """Set session context."""
        if not self.redis:
            return
        key = RedisKeys.SESSION_CONTEXT.format(session_id=session_id)
        await self.redis.setex(key, ttl, json.dumps(context))

    async def append_to_history(
        self, session_id: str, turn: Dict[str, Any], limit: int = 20
    ):
        """Append turn to session history."""
        if not self.redis:
            return
        key = RedisKeys.SESSION_HISTORY.format(session_id=session_id)
        await self.redis.lpush(key, json.dumps(turn))
        await self.redis.ltrim(key, 0, limit - 1)

    # Skill registry methods
    async def get_skill(self, skill_id: str) -> Optional[SkillRegistryEntry]:
        """Get skill entry."""
        if not self.redis:
            return None
        key = RedisKeys.SKILL.format(skill_id=skill_id)
        data = await self.redis.get(key)
        if not data:
            return None
        d = json.loads(data)
        return SkillRegistryEntry(
            skill_id=d["skill_id"],
            state=SkillState(d["state"]),
            success_count=d.get("success_count", 0),
            failure_count=d.get("failure_count", 0),
            last_success_ts=d.get("last_success_ts"),
            risk_scope=d.get("risk_scope", "default"),
            requires_approval=d.get("requires_approval", True),
        )

    async def set_skill(self, entry: SkillRegistryEntry, ttl: int = 86400 * 30):
        """Set skill entry."""
        if not self.redis:
            return
        key = RedisKeys.SKILL.format(skill_id=entry.skill_id)
        data = {
            "skill_id": entry.skill_id,
            "state": entry.state.value,
            "success_count": entry.success_count,
            "failure_count": entry.failure_count,
            "last_success_ts": entry.last_success_ts,
            "risk_scope": entry.risk_scope,
            "requires_approval": entry.requires_approval,
        }
        await self.redis.setex(key, ttl, json.dumps(data))

    async def record_skill_success(self, skill_id: str):
        """Record successful skill execution."""
        entry = await self.get_skill(skill_id) or SkillRegistryEntry(skill_id=skill_id)
        entry.success_count += 1
        entry.last_success_ts = datetime.now(timezone.utc).isoformat()

        # Auto-promote to mastered after 10 successes
        if entry.state == SkillState.LEARNING and entry.success_count >= 5:
            entry.state = SkillState.SANDBOX
        elif entry.state == SkillState.SANDBOX and entry.success_count >= 10:
            entry.state = SkillState.MASTERED
            entry.requires_approval = False

        await self.set_skill(entry)

    async def record_skill_failure(self, skill_id: str):
        """Record failed skill execution."""
        entry = await self.get_skill(skill_id) or SkillRegistryEntry(skill_id=skill_id)
        entry.failure_count += 1

        # Demote on failure
        if entry.state == SkillState.MASTERED:
            entry.state = SkillState.SANDBOX
            entry.requires_approval = True
        elif entry.state == SkillState.SANDBOX:
            entry.state = SkillState.LEARNING

        await self.set_skill(entry)

    # Lock methods
    async def acquire_lock(self, resource: str, owner: str, ttl: int = 30) -> bool:
        """Acquire distributed lock."""
        if not self.redis:
            return True  # No Redis = no locking
        key = RedisKeys.LOCK.format(resource=resource)
        # SET NX with expiry
        result = await self.redis.set(key, owner, nx=True, ex=ttl)
        return bool(result)

    async def release_lock(self, resource: str, owner: str) -> bool:
        """Release distributed lock."""
        if not self.redis:
            return True
        key = RedisKeys.LOCK.format(resource=resource)
        # Lua script for atomic check-and-delete
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        result = await self.redis.eval(script, 1, key, owner)
        return bool(result)

    # Job state methods
    async def set_job_state(self, job_id: str, state: Dict[str, Any], ttl: int = 3600):
        """Set job state."""
        if not self.redis:
            return
        key = RedisKeys.JOB_STATE.format(job_id=job_id)
        await self.redis.setex(key, ttl, json.dumps(state))

    async def get_job_state(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job state."""
        if not self.redis:
            return None
        key = RedisKeys.JOB_STATE.format(job_id=job_id)
        data = await self.redis.get(key)
        return json.loads(data) if data else None

    # Cache methods
    async def cache_get(self, key: str) -> Optional[Any]:
        """Get cached value."""
        if not self.redis:
            return None
        cache_key = RedisKeys.CACHE.format(key=key)
        data = await self.redis.get(cache_key)
        return json.loads(data) if data else None

    async def cache_set(self, key: str, value: Any, ttl: int = 300):
        """Set cached value."""
        if not self.redis:
            return
        cache_key = RedisKeys.CACHE.format(key=key)
        await self.redis.setex(cache_key, ttl, json.dumps(value))


# ============================================================================
# D'ARTAGNAN - Service Directory (Tailscale)
# ============================================================================
# D'ARTAGNAN - Service Directory (Tailscale)
# ============================================================================


class NetworkType(Enum):
    """Network type for endpoint priority."""

    DIRECT = "direct"  # 10.10.xx - low latency Node1↔Node2
    LAN = "lan"  # 192.168.xx - local network
    TAILSCALE = "tail"  # Tailscale - secure cross-node
    CLOUD = "cloud"  # Public internet


@dataclass
class ServiceEndpoint:
    """Service endpoint definition."""

    name: str
    host: str
    port: int
    protocol: str = "http"
    network: NetworkType = NetworkType.LAN
    priority: int = 10  # Lower = higher priority
    tags: List[str] = field(default_factory=list)
    healthy: bool = True
    last_check: Optional[str] = None

    @property
    def url(self) -> str:
        return f"{self.protocol}://{self.host}:{self.port}"


@dataclass
class ServiceDefinition:
    """Service with multiple endpoints."""

    service_id: str
    endpoints: List[ServiceEndpoint] = field(default_factory=list)
    default_protocol: str = "http"

    def get_best_endpoint(
        self, available_networks: Optional[List[NetworkType]] = None
    ) -> Optional[ServiceEndpoint]:
        """Get best available endpoint based on priority and network."""
        if not self.endpoints:
            return None

        # Filter by available networks if specified
        candidates = self.endpoints
        if available_networks:
            candidates = [e for e in candidates if e.network in available_networks]

        # Filter healthy endpoints
        candidates = [e for e in candidates if e.healthy]

        if not candidates:
            # Fallback to any endpoint if none healthy
            candidates = self.endpoints

        # Return lowest priority (highest preference)
        return min(candidates, key=lambda e: e.priority)


class ServiceDirectory:
    """
    Tailscale-backed service discovery with multi-endpoint + priority.

    Network priority rules:
    - A/V streaming (Whisper/Piper): direct > lan > tail
    - Control/APIs (HASS, Atlas, Nextcloud): lan > tail > cloud
    - Redis/Celery (broker): one canonical (lan or tail)
    """

    # Priority by network type for each traffic class
    NETWORK_PRIORITY = {
        "av_streaming": [NetworkType.DIRECT, NetworkType.LAN, NetworkType.TAILSCALE],
        "control": [NetworkType.LAN, NetworkType.TAILSCALE, NetworkType.CLOUD],
        "broker": [NetworkType.LAN, NetworkType.TAILSCALE],  # Redis/Celery
    }

    def __init__(self):
        self._services: Dict[str, ServiceDefinition] = {}
        self._setup_defaults()

    def _setup_defaults(self):
        """Setup default service endpoints."""
        defaults = [
            # Redis - canonical por LAN (estabilidad para broker/locks)
            ServiceEndpoint(
                "redis",
                "192.168.1.10",
                6379,
                "redis",
                NetworkType.LAN,
                priority=10,
                tags=["broker"],
            ),
            # Neo4j
            ServiceEndpoint(
                "neo4j", "192.168.1.10", 7687, "bolt", NetworkType.LAN, priority=10
            ),
            ServiceEndpoint(
                "neo4j", "denis-neo4j", 7687, "bolt", NetworkType.TAILSCALE, priority=20
            ),
            # HASS - LAN primero, Tailscale fallback
            ServiceEndpoint(
                "hass", "192.168.1.20", 8123, "http", NetworkType.LAN, priority=10
            ),
            ServiceEndpoint(
                "hass",
                "homeassistant.local",
                8123,
                "http",
                NetworkType.TAILSCALE,
                priority=30,
            ),
            # Theia IDE - 10.10 directo para Node1↔Node2, LAN fallback
            ServiceEndpoint(
                "theia",
                "10.10.10.2",
                8080,
                "http",
                NetworkType.DIRECT,
                priority=10,
                tags=["ide", "av_streaming"],
            ),
            ServiceEndpoint(
                "theia",
                "192.168.1.30",
                8080,
                "http",
                NetworkType.LAN,
                priority=20,
                tags=["ide"],
            ),
            ServiceEndpoint(
                "theia",
                "denis-theia",
                8080,
                "http",
                NetworkType.TAILSCALE,
                priority=30,
                tags=["ide"],
            ),
            # Whisper ASR - Node1 (10.10 directo)
            ServiceEndpoint(
                "whisper",
                "10.10.10.1",
                9001,
                "http",
                NetworkType.DIRECT,
                priority=10,
                tags=["av_streaming", "asr"],
            ),
            ServiceEndpoint(
                "whisper",
                "192.168.1.40",
                9001,
                "http",
                NetworkType.LAN,
                priority=20,
                tags=["av_streaming", "asr"],
            ),
            # Piper TTS - Node2 (10.10 directo para low latency)
            ServiceEndpoint(
                "piper",
                "10.10.10.2",
                9002,
                "http",
                NetworkType.DIRECT,
                priority=10,
                tags=["av_streaming", "tts"],
            ),
            ServiceEndpoint(
                "piper",
                "192.168.1.40",
                9002,
                "http",
                NetworkType.LAN,
                priority=20,
                tags=["av_streaming", "tts"],
            ),
            # Atlas (MongoDB)
            ServiceEndpoint(
                "atlas", "192.168.1.50", 27017, "mongodb", NetworkType.LAN, priority=10
            ),
            ServiceEndpoint(
                "atlas",
                "denis-atlas",
                27017,
                "mongodb",
                NetworkType.TAILSCALE,
                priority=30,
            ),
            # Nextcloud
            ServiceEndpoint(
                "nextcloud", "192.168.1.60", 443, "https", NetworkType.LAN, priority=10
            ),
            ServiceEndpoint(
                "nextcloud",
                "nextcloud.example.com",
                443,
                "https",
                NetworkType.CLOUD,
                priority=30,
            ),
        ]

        for ep in defaults:
            self.register_endpoint(ep)

    def register_endpoint(self, endpoint: ServiceEndpoint):
        """Register a service endpoint."""
        if endpoint.name not in self._services:
            self._services[endpoint.name] = ServiceDefinition(service_id=endpoint.name)
        self._services[endpoint.name].endpoints.append(endpoint)
        logger.info(
            f"Registered {endpoint.name} at {endpoint.url} ({endpoint.network.value}, priority={endpoint.priority})"
        )

    def register(self, service_id: str, endpoint: ServiceEndpoint):
        """Register endpoint to service."""
        endpoint.name = service_id
        self.register_endpoint(endpoint)

    def resolve(
        self,
        service_id: str,
        traffic_class: str = "control",
        networks_available: Optional[List[NetworkType]] = None,
    ) -> Optional[str]:
        """
        Resolve service to best URL.

        Args:
            service_id: Service name
            traffic_class: "av_streaming", "control", or "broker"
            networks_available: List of networks to consider (default: all)
        """
        service = self._services.get(service_id)
        if not service:
            return None

        # Get priority order for traffic class
        if networks_available is None:
            networks_available = self.NETWORK_PRIORITY.get(
                traffic_class, self.NETWORK_PRIORITY["control"]
            )

        # Try each network type in priority order
        for network in networks_available:
            ep = service.get_best_endpoint([network])
            if ep and ep.healthy:
                return ep.url

        # Fallback: any healthy endpoint
        ep = service.get_best_endpoint()
        return ep.url if ep else None

    def resolve_or_raise(self, service_id: str, traffic_class: str = "control") -> str:
        """Resolve service or raise error."""
        url = self.resolve(service_id, traffic_class)
        if not url:
            raise RuntimeError(f"Service not found or unavailable: {service_id}")
        return url

    def resolve_all(self, service_id: str) -> List[ServiceEndpoint]:
        """Get all endpoints for a service."""
        service = self._services.get(service_id)
        return service.endpoints if service else []

    def get_all_services(self) -> Dict[str, ServiceDefinition]:
        """Get all services."""
        return dict(self._services)

    def get_by_tag(self, tag: str) -> List[ServiceEndpoint]:
        """Get services by tag."""
        result = []
        for svc in self._services.values():
            result.extend([e for e in svc.endpoints if tag in e.tags])
        return result

    async def healthcheck(
        self, endpoint: ServiceEndpoint, timeout: float = 0.3
    ) -> bool:
        """Simple healthcheck for endpoint."""
        import socket

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            port = endpoint.port if endpoint.protocol != "https" else endpoint.port
            result = sock.connect_ex((endpoint.host, port))
            sock.close()
            return result == 0
        except Exception:
            return False

    async def refresh_health(self):
        """Refresh health status for all endpoints."""
        for svc in self._services.values():
            for ep in svc.endpoints:
                ep.healthy = await self.healthcheck(ep)
                ep.last_check = datetime.now(timezone.utc).isoformat()


# ============================================================================
# Enhanced Service Directory with Cache, Circuit Breaker, Metrics
# ============================================================================

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import Lock
import time


@dataclass
class EndpointMetrics:
    """Metrics for an endpoint."""

    total_requests: int = 0
    successes: int = 0
    failures: int = 0
    total_latency_ms: float = 0.0
    last_success: Optional[str] = None
    last_failure: Optional[str] = None

    @property
    def avg_latency_ms(self) -> float:
        return (
            self.total_latency_ms / self.total_requests
            if self.total_requests > 0
            else 0.0
        )

    @property
    def error_rate(self) -> float:
        return self.failures / self.total_requests if self.total_requests > 0 else 0.0


@dataclass
class CircuitBreakerState:
    """Circuit breaker state for an endpoint."""

    failures: int = 0
    last_failure_time: Optional[float] = None
    is_open: bool = False
    cooldown_seconds: float = 30.0
    failure_threshold: int = 3

    def record_success(self):
        """Record successful request."""
        self.failures = 0
        self.is_open = False

    def record_failure(self):
        """Record failed request."""
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.failure_threshold:
            self.is_open = True

    def should_try(self) -> bool:
        """Check if should try (not open or cooldown passed)."""
        if not self.is_open:
            return True
        if (
            self.last_failure_time
            and (time.time() - self.last_failure_time) > self.cooldown_seconds
        ):
            self.is_open = False
            self.failures = 0
            return True
        return False


class ResolvedCache:
    """Cache for service resolutions."""

    def __init__(self, ttl_seconds: float = 5.0):
        self._cache: Dict[str, tuple[str, float]] = {}
        self._ttl = ttl_seconds
        self._lock = Lock()

    def get(self, key: str) -> Optional[str]:
        """Get cached resolution."""
        with self._lock:
            if key in self._cache:
                url, cached_at = self._cache[key]
                if time.time() - cached_at < self._ttl:
                    return url
                del self._cache[key]
        return None

    def set(self, key: str, url: str):
        """Cache a resolution."""
        with self._lock:
            self._cache[key] = (url, time.time())

    def invalidate(self, key: Optional[str] = None):
        """Invalidate cache."""
        with self._lock:
            if key:
                self._cache.pop(key, None)
            else:
                self._cache.clear()


class EnhancedServiceDirectory(ServiceDirectory):
    """
    Enhanced Service Directory with:
    - Resolution caching (TTL)
    - Circuit breaker
    - Metrics
    """

    def __init__(self, cache_ttl_seconds: float = 5.0):
        super().__init__()
        self._cache = ResolvedCache(ttl_seconds=cache_ttl_seconds)
        self._metrics: Dict[str, EndpointMetrics] = {}
        self._circuit_breakers: Dict[str, CircuitBreakerState] = {}
        self._lock = Lock()

    def _get_metrics_key(self, service_id: str, endpoint: ServiceEndpoint) -> str:
        return f"{service_id}:{endpoint.host}:{endpoint.port}"

    def _get_circuit_key(self, service_id: str, endpoint: ServiceEndpoint) -> str:
        return f"{service_id}:{endpoint.url}"

    def _get_circuit(
        self, service_id: str, endpoint: ServiceEndpoint
    ) -> CircuitBreakerState:
        key = self._get_circuit_key(service_id, endpoint)
        with self._lock:
            if key not in self._circuit_breakers:
                self._circuit_breakers[key] = CircuitBreakerState()
            return self._circuit_breakers[key]

    def _get_metrics(
        self, service_id: str, endpoint: ServiceEndpoint
    ) -> EndpointMetrics:
        key = self._get_metrics_key(service_id, endpoint)
        with self._lock:
            if key not in self._metrics:
                self._metrics[key] = EndpointMetrics()
            return self._metrics[key]

    def record_request(
        self,
        service_id: str,
        endpoint: ServiceEndpoint,
        success: bool,
        latency_ms: float = 0.0,
    ):
        """Record request outcome for metrics."""
        metrics = self._get_metrics(service_id, endpoint)
        metrics.total_requests += 1
        if success:
            metrics.successes += 1
            metrics.last_success = datetime.now(timezone.utc).isoformat()
        else:
            metrics.failures += 1
            metrics.last_failure = datetime.now(timezone.utc).isoformat()
        metrics.total_latency_ms += latency_ms

        # Update circuit breaker
        circuit = self._get_circuit(service_id, endpoint)
        if success:
            circuit.record_success()
        else:
            circuit.record_failure()

    def resolve(
        self,
        service_id: str,
        traffic_class: str = "control",
        networks_available: Optional[List[NetworkType]] = None,
    ) -> Optional[str]:
        """Resolve with caching."""
        cache_key = f"{service_id}:{traffic_class}"
        cached = self._cache.get(cache_key)
        if cached:
            return cached

        result = super().resolve(service_id, traffic_class, networks_available)
        if result:
            self._cache.set(cache_key, result)
        return result

    def resolve_with_metrics(
        self,
        service_id: str,
        traffic_class: str = "control",
        networks_available: Optional[List[NetworkType]] = None,
    ) -> tuple[Optional[str], EndpointMetrics]:
        """Resolve and return metrics for the chosen endpoint."""
        service = self._services.get(service_id)
        if not service:
            return None, EndpointMetrics()

        url = self.resolve(service_id, traffic_class, networks_available)

        # Find endpoint and return its metrics
        for ep in service.endpoints:
            if ep.url == url:
                metrics = self._get_metrics(service_id, ep)
                return url, metrics

        return url, EndpointMetrics()

    def invalidate_cache(self, service_id: Optional[str] = None):
        """Invalidate resolution cache."""
        if service_id:
            for tc in ["av_streaming", "control", "broker"]:
                self._cache.invalidate(f"{service_id}:{tc}")
        else:
            self._cache.invalidate()

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get metrics summary."""
        summary = {}
        for key, metrics in self._metrics.items():
            service_id = key.split(":")[0]
            if service_id not in summary:
                summary[service_id] = {
                    "requests": 0,
                    "successes": 0,
                    "failures": 0,
                    "avg_latency_ms": 0.0,
                    "error_rate": 0.0,
                }
            s = summary[service_id]
            s["requests"] += metrics.total_requests
            s["successes"] += metrics.successes
            s["failures"] += metrics.failures
            s["avg_latency_ms"] = metrics.avg_latency_ms
            s["error_rate"] = metrics.error_rate
        return summary

    def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """Get circuit breaker status."""
        status = {}
        for key, cb in self._circuit_breakers.items():
            status[key] = {
                "failures": cb.failures,
                "is_open": cb.is_open,
                "last_failure": cb.last_failure_time,
            }
        return status


# ============================================================================
# ATHOS - Celery Bridge (stub for integration)
# ============================================================================


class Athos:
    """
    Celery job bridge.

    Provides:
    - Job creation
    - Progress tracking
    - Result aggregation
    """

    def __init__(self, celery_app_name: str = "denis_crew_tasks"):
        self.celery_app = celery_app_name
        self._available = False

    def is_available(self) -> bool:
        """Check if Celery is available."""
        return self._available

    async def create_job(
        self, task_name: str, payload: Dict[str, Any], trace_id: str
    ) -> str:
        """
        Create a Celery task.

        Returns job_id.
        """
        if not self._available:
            raise RuntimeError("Celery not available")

        # This would call celery.send_task in real implementation
        job_id = f"job_{trace_id}_{task_name}"
        logger.info(f"Created job: {job_id} for task: {task_name}")
        return job_id

    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get job status."""
        # This would query Celery state
        return {"status": "pending", "job_id": job_id}

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a job."""
        if not self._available:
            return False
        # This would call celery.control.revoke
        logger.info(f"Cancelled job: {job_id}")
        return True


# ============================================================================
# Global instances
# ============================================================================

_porthos: Optional[Porthos] = None
_service_directory: Optional[ServiceDirectory] = None
_athos: Optional[Athos] = None


def get_porthos(redis_client=None) -> Porthos:
    """Get Porthos instance."""
    global _porthos
    if _porthos is None:
        _porthos = Porthos(redis_client)
    return _porthos


def get_service_directory() -> ServiceDirectory:
    """Get Service Directory instance."""
    global _service_directory
    if _service_directory is None:
        _service_directory = ServiceDirectory()
    return _service_directory


def get_athos() -> Athos:
    """Get Athos instance."""
    global _athos
    if _athos is None:
        _athos = Athos()
    return _athos
