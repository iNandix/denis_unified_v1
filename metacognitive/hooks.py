"""
Metacognitive Hooks (Fase 0).
Instrumenta operaciones críticas con eventos a Redis.
"""
import functools
import time
import uuid
import json
import os
import asyncio
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
    SIEMPRE devuelve un decorador funcional (noop si falla).
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # NOOP si Redis no está disponible o tracing está deshabilitado
            if redis is None or os.getenv("METACOGNITIVE_TRACING_DISABLED", "false").lower() == "true":
                return func(*args, **kwargs)

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
                result = func(*args, **kwargs)
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

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # NOOP si Redis no está disponible o tracing está deshabilitado
            if redis is None or os.getenv("METACOGNITIVE_TRACING_DISABLED", "false").lower() == "true":
                return await func(*args, **kwargs)

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

        # Return appropriate wrapper based on whether func is async
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def voice_hook(text: str, modulation: dict, resonance: float):
    """
    Hook for voice metacognitive instrumentation.
    Emits voice analysis events to Redis.
    """
    redis_client = get_redis_client()
    if redis_client:
        try:
            redis_client.publish("denis:metacognitive:events", json.dumps({
                "type": "voice_analysis",
                "text_snippet": text[:50],
                "emotion": modulation.get("emotion"),
                "resonance": resonance,
                "timestamp": time.time(),
            }))
        except:
            pass  # Fail-open


def inference_hook(task: str, model: str, uncertainty: float, ethical: bool, latency_ms: float):
    """
    Hook for inference metacognitive instrumentation.
    Emits inference routing events to Redis.
    """
    redis_client = get_redis_client()
    if redis_client:
        try:
            redis_client.publish("denis:metacognitive:events", json.dumps({
                "type": "inference_routing",
                "task": task[:100],  # Truncate long tasks
                "model": model,
                "uncertainty": uncertainty,
                "ethical": ethical,
                "latency_ms": latency_ms,
                "timestamp": time.time(),
            }))
        except:
            pass  # Fail-open


def memory_hook(scores: dict, decayed: bool, consolidated: bool, narrative: str):
    """
    Hook for memory metacognitive instrumentation.
    Emits memory processing events to Redis.
    """
    redis_client = get_redis_client()
    if redis_client:
        try:
            redis_client.publish("denis:metacognitive:events", json.dumps({
                "type": "memory_processing",
                "scores": scores,
                "decayed": decayed,
                "consolidated": consolidated,
                "narrative": narrative[:200],  # Truncate long narratives
                "timestamp": time.time(),
            }))
        except:
            pass  # Fail-open


def self_model_hook(identity: str, capabilities: list, limits: dict):
    """
    Hook for self-model metacognitive instrumentation.
    Emits self-awareness events to Redis.
    """
    redis_client = get_redis_client()
    if redis_client:
        try:
            redis_client.publish("denis:metacognitive:events", json.dumps({
                "type": "self_awareness",
                "identity": identity,
                "capabilities": capabilities,
                "limits": limits,
                "timestamp": time.time(),
            }))
        except:
            pass  # Fail-open