"""
Metacognitive Hooks (Fase 0).
Instrumenta operaciones críticas con eventos a Redis.
"""
import functools
import time
import uuid
import json
import os
from typing import Any, Callable

try:
    import redis
except ImportError:
    redis = None


def get_redis_client():
    """Lazy init Redis client."""
    if redis is None:
        return None
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return redis.Redis.from_url(redis_url, decode_responses=True)


def metacognitive_trace(operation: str):
    """
    Decorator que instrumenta operaciones críticas.
    Emite eventos a Redis: denis:metacognitive:events
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            trace_id = str(uuid.uuid4())
            start = time.time()
            redis_client = get_redis_client()
            
            # Emit entry event
            if redis_client:
                try:
                    redis_client.publish("denis:metacognitive:events", json.dumps({
                        "type": "entry",
                        "operation": operation,
                        "trace_id": trace_id,
                        "timestamp": start,
                    }))
                except:
                    pass  # No bloquear si Redis falla
            
            try:
                result = await func(*args, **kwargs)
                latency = time.time() - start
                
                # Emit exit event
                if redis_client:
                    try:
                        redis_client.publish("denis:metacognitive:events", json.dumps({
                            "type": "exit",
                            "operation": operation,
                            "trace_id": trace_id,
                            "latency_ms": int(latency * 1000),
                            "success": True,
                        }))
                    except:
                        pass
                
                # Store metric in Redis (for learning)
                if redis_client:
                    try:
                        key = f"metrics:{operation}:latency"
                        redis_client.lpush(key, int(latency * 1000))
                        redis_client.ltrim(key, 0, 99)  # Keep last 100
                    except:
                        pass
                
                return result
            
            except Exception as e:
                # Emit error event
                if redis_client:
                    try:
                        redis_client.publish("denis:metacognitive:events", json.dumps({
                            "type": "error",
                            "operation": operation,
                            "trace_id": trace_id,
                            "error": str(e),
                        }))
                    except:
                        pass
                raise
        
        return wrapper
    return decorator