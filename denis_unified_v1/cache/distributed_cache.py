"""Advanced distributed caching with Redis Cluster support."""

import asyncio
import json
import hashlib
import time
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
import os

try:
    import redis
    from redis.cluster import RedisCluster
    import redis.asyncio as aioredis
    from redis.asyncio.cluster import RedisCluster as AsyncRedisCluster
except ImportError:
    redis = None
    RedisCluster = None
    aioredis = None
    AsyncRedisCluster = None


@dataclass
class CacheConfig:
    """Configuration for distributed cache."""
    enabled: bool = True
    cluster_mode: bool = False
    startup_nodes: List[Dict[str, Union[str, int]]] = None
    redis_url: str = "redis://localhost:6379/0"
    key_prefix: str = "denis:cache:"
    default_ttl_seconds: int = 3600  # 1 hour
    max_memory_mb: int = 512
    eviction_policy: str = "allkeys-lru"
    compression_threshold: int = 1024  # Compress values > 1KB


class DistributedCache:
    """Advanced distributed cache with Redis Cluster support."""

    def __init__(self, config: CacheConfig):
        self.config = config
        self._sync_client = None
        self._async_client = None
        self._cache_stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "errors": 0
        }

    async def initialize(self):
        """Initialize cache connections."""
        if not self.config.enabled or not redis:
            return

        try:
            if self.config.cluster_mode and RedisCluster:
                # Redis Cluster mode
                if self.config.startup_nodes:
                    self._sync_client = RedisCluster(
                        startup_nodes=self.config.startup_nodes,
                        decode_responses=True,
                        max_connections=20
                    )
                    self._async_client = AsyncRedisCluster(
                        startup_nodes=self.config.startup_nodes,
                        decode_responses=True,
                        max_connections=20
                    )
                else:
                    # Fallback to single node cluster
                    self._sync_client = RedisCluster.from_url(
                        self.config.redis_url,
                        decode_responses=True,
                        max_connections=20
                    )
                    self._async_client = AsyncRedisCluster.from_url(
                        self.config.redis_url,
                        decode_responses=True,
                        max_connections=20
                    )
            else:
                # Single Redis instance with connection pool
                pool = redis.ConnectionPool.from_url(
                    self.config.redis_url,
                    decode_responses=True,
                    max_connections=20
                )
                self._sync_client = redis.Redis(connection_pool=pool)

                async_pool = aioredis.ConnectionPool.from_url(
                    self.config.redis_url,
                    decode_responses=True,
                    max_connections=20
                )
                self._async_client = aioredis.Redis(connection_pool=async_pool)

        except Exception as e:
            print(f"Failed to initialize cache: {e}")
            self._sync_client = None
            self._async_client = None

    def _make_key(self, key: str) -> str:
        """Create prefixed cache key."""
        return f"{self.config.key_prefix}{key}"

    def _should_compress(self, value: str) -> bool:
        """Check if value should be compressed."""
        return len(value.encode('utf-8')) > self.config.compression_threshold

    def _compress_value(self, value: Any) -> str:
        """Compress cache value if needed."""
        json_str = json.dumps(value, sort_keys=True, default=str)
        if self._should_compress(json_str):
            # Simple compression placeholder - in production use lz4, zstd, etc.
            return f"compressed:{json_str}"
        return json_str

    def _decompress_value(self, value: str) -> Any:
        """Decompress cache value if needed."""
        if value.startswith("compressed:"):
            value = value[11:]  # Remove "compressed:" prefix
        return json.loads(value)

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if not self._async_client:
            return None

        cache_key = self._make_key(key)
        try:
            value = await self._async_client.get(cache_key)
            if value is None:
                self._cache_stats["misses"] += 1
                return None

            result = self._decompress_value(value)
            self._cache_stats["hits"] += 1
            return result

        except Exception as e:
            self._cache_stats["errors"] += 1
            print(f"Cache get error: {e}")
            return None

    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> bool:
        """Set value in cache."""
        if not self._async_client:
            return False

        cache_key = self._make_key(key)
        ttl = ttl_seconds or self.config.default_ttl_seconds

        try:
            compressed_value = self._compress_value(value)
            success = await self._async_client.setex(cache_key, ttl, compressed_value)
            if success:
                self._cache_stats["sets"] += 1
            return bool(success)

        except Exception as e:
            self._cache_stats["errors"] += 1
            print(f"Cache set error: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete value from cache."""
        if not self._async_client:
            return False

        cache_key = self._make_key(key)
        try:
            result = await self._async_client.delete(cache_key)
            if result:
                self._cache_stats["deletes"] += 1
            return bool(result)

        except Exception as e:
            self._cache_stats["errors"] += 1
            print(f"Cache delete error: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        if not self._async_client:
            return False

        cache_key = self._make_key(key)
        try:
            return bool(await self._async_client.exists(cache_key))
        except Exception:
            return False

    async def get_or_set(self, key: str, getter_func, ttl_seconds: Optional[int] = None):
        """Get from cache or compute and set."""
        # Try cache first
        cached_value = await self.get(key)
        if cached_value is not None:
            return cached_value

        # Compute value
        try:
            value = await getter_func()
            if value is not None:
                await self.set(key, value, ttl_seconds)
            return value
        except Exception as e:
            print(f"Error computing cache value: {e}")
            return None

    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching pattern."""
        if not self._async_client:
            return 0

        try:
            pattern_key = f"{self.config.key_prefix}{pattern}"
            keys = await self._async_client.keys(pattern_key)
            if keys:
                result = await self._async_client.delete(*keys)
                self._cache_stats["deletes"] += len(keys)
                return result
            return 0

        except Exception as e:
            self._cache_stats["errors"] += 1
            print(f"Cache invalidate pattern error: {e}")
            return 0

    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        if not self._async_client:
            return {"status": "disabled"}

        try:
            info = await self._async_client.info()
            return {
                "status": "connected",
                "config": {
                    "cluster_mode": self.config.cluster_mode,
                    "default_ttl": self.config.default_ttl_seconds,
                    "compression_threshold": self.config.compression_threshold
                },
                "stats": self._cache_stats.copy(),
                "redis_info": {
                    "connected_clients": info.get("connected_clients", 0),
                    "used_memory_human": info.get("used_memory_human", "unknown"),
                    "total_connections_received": info.get("total_connections_received", 0)
                }
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "stats": self._cache_stats.copy()
            }

    async def health_check(self) -> Dict[str, Any]:
        """Perform cache health check."""
        if not self._async_client:
            return {"healthy": False, "reason": "cache_disabled"}

        try:
            # Test basic operations
            test_key = f"health_check_{int(time.time())}"
            await self.set(test_key, {"test": "value"}, ttl_seconds=60)
            retrieved = await self.get(test_key)
            await self.delete(test_key)

            if retrieved and retrieved.get("test") == "value":
                return {
                    "healthy": True,
                    "response_time_ms": 0,  # Could measure this
                    "cluster_mode": self.config.cluster_mode
                }
            else:
                return {"healthy": False, "reason": "cache_inconsistent"}

        except Exception as e:
            return {"healthy": False, "reason": str(e)}


# Global cache instance
_cache_instance = None

async def get_distributed_cache() -> DistributedCache:
    """Get global distributed cache instance."""
    global _cache_instance
    if _cache_instance is None:
        # Configure cache based on environment
        config = CacheConfig(
            enabled=os.getenv("CACHE_ENABLED", "true").lower() == "true",
            cluster_mode=os.getenv("REDIS_CLUSTER_MODE", "false").lower() == "true",
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            key_prefix=os.getenv("CACHE_KEY_PREFIX", "denis:cache:"),
            default_ttl_seconds=int(os.getenv("CACHE_DEFAULT_TTL", "3600")),
            max_memory_mb=int(os.getenv("CACHE_MAX_MEMORY_MB", "512")),
            compression_threshold=int(os.getenv("CACHE_COMPRESSION_THRESHOLD", "1024"))
        )

        _cache_instance = DistributedCache(config)
        await _cache_instance.initialize()

    return _cache_instance


# Legacy compatibility functions
async def cache_get(key: str) -> Optional[Any]:
    """Legacy cache get function."""
    cache = await get_distributed_cache()
    return await cache.get(key)

async def cache_set(key: str, value: Any, ttl_seconds: Optional[int] = None) -> bool:
    """Legacy cache set function."""
    cache = await get_distributed_cache()
    return await cache.set(key, value, ttl_seconds)

async def cache_delete(key: str) -> bool:
    """Legacy cache delete function."""
    cache = await get_distributed_cache()
    return await cache.delete(key)
