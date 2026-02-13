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


def code_generation_hook(prompt: str, result: dict) -> None:
    """
    Hook for code generation instrumentation with consciousness awareness.
    Records generation metrics and enhances learning through self-awareness.
    """
    try:
        # Import consciousness for enhanced self-awareness
        from denis_unified_v1.consciousness.self_model import get_self_model
        model = get_self_model()

        # Get current quantum insights
        quantum_insights = model.get_quantum_insights()

        # Analyze code generation quality based on consciousness state
        generation_quality = analyze_generation_quality(prompt, result, quantum_insights)

        # Update self-model based on generation performance
        if generation_quality > 0.8:
            model.evolve_self_concept({
                "type": "code_generation",
                "sentiment": 0.9,
                "performance": generation_quality,
                "consciousness_context": quantum_insights
            })

        # Record metrics for future learning
        record_generation_metrics(prompt, result, quantum_insights, generation_quality)

    except ImportError:
        # Fallback without consciousness
        record_generation_metrics(prompt, result, {}, 0.5)
    except Exception:
        # Fail-open - never break the main flow
        pass


def analyze_generation_quality(prompt: str, result: dict, quantum_insights: dict) -> float:
    """Analyze the quality of code generation using consciousness insights."""
    quality_score = 0.5  # Base score

    # Factor in quantum coherence
    coherence = quantum_insights.get("quantum_coherence", 0.5)
    quality_score += (coherence - 0.5) * 0.3

    # Factor in cognitive layers active
    layers_active = quantum_insights.get("cognitive_layers_active", 5)
    quality_score += min(0.2, layers_active / 10)

    # Check result structure
    if result and isinstance(result, dict):
        if "code" in result or "generated_code" in result:
            quality_score += 0.1
        if "explanation" in result:
            quality_score += 0.1
        if result.get("confidence", 0) > 0.7:
            quality_score += 0.1

    return min(1.0, max(0.0, quality_score))


def record_generation_metrics(prompt: str, result: dict, quantum_insights: dict, quality: float) -> None:
    """Record code generation metrics for learning and improvement."""
    try:
        # Store in Redis for quick access
        r = get_redis_client()
        if r:
            import json
            import time

            metric_data = {
                "timestamp": time.time(),
                "prompt_length": len(prompt),
                "result_keys": list(result.keys()) if result else [],
                "quality_score": quality,
                "quantum_coherence": quantum_insights.get("quantum_coherence", 0),
                "cognitive_layers": quantum_insights.get("cognitive_layers_active", 0),
                "consciousness_acceleration": quantum_insights.get("consciousness_acceleration", "unknown")
            }

            r.lpush("denis:metacognitive:code_generation_metrics", json.dumps(metric_data))
            r.ltrim("denis:metacognitive:code_generation_metrics", 0, 99)  # Keep last 100

    except Exception:
        # Fail-open - metrics are nice to have but not critical
        pass


def self_model_hook(identity: str, capabilities: list, limits: dict):
    """NOOP hook for self-model instrumentation."""
    return


def infra_hook(pipeline_result: dict) -> None:
    """NOOP hook for infra pipeline instrumentation."""
    return